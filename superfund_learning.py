"""Paired forward evidence and bounded chronological historical experiments."""
from ui_library.work_progress import tracked_job, report_progress
from copy import deepcopy
import base64
import gzip
import hashlib
import json
from itertools import islice
from superfund_engine import initial,cycle,at,DEFAULTS,eligibility


def equity(state):
    return state.get('cash',0)+sum(p['quantity']*p['last_nok'] for p in state.get('positions',{}).values())


def forward_evidence(previous,model,shadows,items,now,p):
    old=deepcopy(previous.get('learning',{}))
    dates=set(old.get('observed_dates',[]))
    # Count NAV/quote dates, not cron wakeups or repeated publications.
    latest=max((i.get('price_at','')[:10] for i in items if not eligibility(i,at(now),p,buy=False)),default='')
    if latest:dates.add(latest)
    old['observed_dates']=sorted(dates)[-1000:]
    reference=old.get('reference_id')
    if not reference:
        candidates=[i for i in items if i.get('name','').lower()=='nordnet global indeks' and i.get('currency')=='NOK' and not eligibility(i,at(now),p)]
        if candidates:
            reference=candidates[0]['id'];old['reference_id']=reference
            b=initial(p);b['orders']=[{'id':reference,'side':'BUY','allocation':p['capital_nok']*(1-p['reserve_pct']/100),
                'requested_at':now,'next_at':candidates[0]['detail']['trading'].get('nextBuyAt'),'reason':'Fryst global kjøp-og-behold-referanse'}]
            old['baseline']=b;old['baseline_started_at']=now
    if reference:
        baseline_p={**p,'enabled':False,'max_position_pct':100}
        # Reference uses explicit one-fund allocation; not production sizing policy.
        baseline_p['max_position_pct']=25
        old['baseline'],_=cycle(old.get('baseline'),[i for i in items if i['id']==reference],now,baseline_p,buy_hold=True)
        base_value=equity(old['baseline'])
        old['baseline_value']=base_value
        if old['baseline'].get('positions') and not old.get('paired_start'):
            old['paired_start']={'at':now,'reference':base_value,**{name:equity(book) for name,book in {'main':model,**shadows}.items()}}
        old['comparisons']={name:{'value':equity(book),'excess_nok':equity(book)-base_value,
            'max_drawdown_pct':book.get('max_drawdown_pct',0),
            'paired_excess_pct':((equity(book)/old['paired_start'][name]-base_value/old['paired_start']['reference'])*100 if old.get('paired_start') else None)} for name,book in {'main':model,**shadows}.items()}
    old['status']='COLLECTING' if reference else 'WAITING_FOR_VERIFIED_REFERENCE'
    old['minimum_dates']=80
    old['message']='60 kursdatoer for kandidatvalg + 20 senere datoer for kontroll. Ingen automatisk regelendring.'
    # Candidate chosen once after sufficient forward data; only later evidence validates it.
    paired_dates={d for d in dates if old.get('paired_start') and d>=old['paired_start']['at'][:10]}
    old['paired_dates']=len(paired_dates)
    if reference and len(paired_dates)>=60 and not old.get('validation') and not old.get('proposal'):
        best=max(shadows,key=lambda n:equity(shadows[n]),default=None)
        if best:
            old['validation']={'candidate':best,'started_dates':len(paired_dates),'at':now,
                'candidate_value':equity(shadows[best]),'reference_value':equity(old['baseline']),
                'main_value':equity(model),'candidate_trades':len(shadows[best].get('trades',[])),
                'rules':deepcopy(previous.get('shadow_rules',{}).get(best,{}))}
    v=old.get('validation')
    if v and len(paired_dates)-v['started_dates']>=20 and not old.get('proposal'):
        name=v['candidate'];candidate=equity(shadows[name]);baseline=equity(old['baseline'])
        candidate_gain=candidate/v['candidate_value']-1;reference_gain=baseline/v['reference_value']-1
        main_gain=equity(model)/v.get('main_value',equity(model))-1
        new_trades=len(shadows[name].get('trades',[]))-v.get('candidate_trades',0)
        if (candidate_gain>max(reference_gain,main_gain) and new_trades>=10 and v['rules']
            and v['rules']['min_week_pct']!=p['min_week_pct']
            and shadows[name].get('max_drawdown_pct',0)<=model.get('max_drawdown_pct',0)):
            old['proposal']={'id':hashlib.sha256((v['at']+name).encode()).hexdigest()[:20],
                'state':'WAITING_APPROVAL','at':now,'parameter':'min_week_pct',
                'current':p['min_week_pct'],'proposed':v['rules']['min_week_pct'],
                'source':f"20 senere kursdatoer: meravkastning {(candidate_gain-reference_gain)*100:.2f} pp; modellkostnader inkludert",
                'rules':v['rules']}
            old['status']='WAITING_APPROVAL'
        else:old['status']='NO_VALIDATED_IMPROVEMENT'
    from superfund_runtime import read
    proposal=old.get('proposal',{})
    decision=read('parameter_audit.json',{}).get('decisions',{}).get(proposal.get('id'))
    if decision:
        proposal.update(decision);old['status']=proposal['state']
        # Rejection means "not now". Reconsider only after 20 new paired dates
        # and a fresh 20-date validation; retain the previous decision history.
        decided_dates=old.setdefault('decision_dates',len(paired_dates))
        if len(paired_dates)-decided_dates>=20:
            old['proposal_history']=(old.get('proposal_history',[])+[deepcopy(proposal)])[-100:]
            old.pop('proposal',None);old.pop('validation',None);old.pop('decision_dates',None)
            old['status']='COLLECTING_NEW_EVIDENCE'
    return old


def decide_proposal(proposal_id,approve,actor='UI'):
    from superfund_runtime import storage,PREFIX,snapshot,now_iso
    proposal=snapshot().get('learning',{}).get('proposal',{})
    if proposal.get('id')!=proposal_id:raise ValueError('Forslaget er erstattet')
    def update(current):
        audit=deepcopy(current or {});decisions=audit.setdefault('decisions',{})
        if proposal_id in decisions:return audit
        old={**DEFAULTS,**audit.get('parameters',{})}
        if old[proposal['parameter']]!=proposal['current']:raise ValueError('Nåværende parameter er endret; forslaget må vurderes på nytt')
        if approve:
            new={**old,proposal['parameter']:proposal['proposed']}
            from superfund_engine import valid_parameters
            valid_parameters(new)
            audit['parameters']=new
            audit['history']=(audit.get('history',[])+[{'at':now_iso(),'actor':actor,'before':old,'after':new,'proposal_id':proposal_id}])[-100:]
        decisions[proposal_id]={'state':'IMPLEMENTED' if approve else 'REJECTED','at':now_iso(),'actor':actor}
        audit['decisions']=dict(list(decisions.items())[-100:])
        return audit
    audit=storage().mutate_json(PREFIX+'parameter_audit.json',update,{})
    return audit['decisions'][proposal_id]


def archive_frame(items,now,p):
    from superfund_runtime import storage,PREFIX,read
    day=now[:10];index=read('learning_index.json',{'frames':[],'bytes':0})
    if any(f['day']==day for f in index['frames']):return
    frozen=[{k:v for k,v in i.items() if k!='observations'} for i in items]
    raw=json.dumps({'at':now,'items':frozen,'parameters':p},sort_keys=True).encode()
    packed=gzip.compress(raw,mtime=0);digest=hashlib.sha256(packed).hexdigest()
    if len(index['frames'])>=180 or index['bytes']+len(packed)>64*1024*1024:
        return {'state':'ARCHIVE_BUDGET_REACHED'}
    if len(raw)>12*1024*1024:raise ValueError('Historikkramme overstiger 12 MiB')
    key=PREFIX+'history/'+day+'.json'
    value={'sha256':digest,'gzip_base64':base64.b64encode(packed).decode()}
    saved=storage().write_json_immutable(key,value)
    stored_bytes=len(base64.b64decode(saved['gzip_base64']))
    def add(current):
        current=deepcopy(current or {'frames':[],'bytes':0})
        if not any(f['day']==day for f in current['frames']):
            current['frames'].append({'day':day,'key':key,'sha256':saved['sha256'],'bytes':stored_bytes})
            current['bytes']+=stored_bytes
        return current
    storage().mutate_json(PREFIX+'learning_index.json',add,{'frames':[],'bytes':0})
    return {'state':'ARCHIVED','day':day}


@tracked_job('Superfond · historisk test')
def historical_experiment(frames,trial_weeks=(0.5,1,2),min_days=80):
    """Chronological selection: first 60% train, next 20% validate, last 20% holdout.

    Frozen recorded universe only. No data is invented when history is too short.
    """
    if len(trial_weeks)>20:raise ValueError('Maks 20 forhåndsdefinerte forsøk')
    dates=[f['at'] for f in frames]
    if dates!=sorted(set(dates)):raise ValueError('Historikk må være unik og kronologisk')
    unique_days=len({s[:10] for s in dates})
    if unique_days<min_days:return {'state':'INSUFFICIENT_HISTORY','days':unique_days,'required':min_days}
    for f in frames:
        if not f.get('items'):raise ValueError('Tom historikkramme')
        for item in f['items']:
            if at(item['observed_at'])>at(f['at']) or at(item['price_at'])>at(f['at']):raise ValueError('Fremtidslekkasje')
            if item.get('detail',{}).get('verified_at') and at(item['detail']['verified_at'])>at(f['at']):raise ValueError('Fremtidslekkasje i produktdetaljer')
    a,b=int(len(frames)*0.6),int(len(frames)*0.8)
    results=[]
    for trial_index,week in enumerate(trial_weeks):
        report_progress(trial_index,len(trial_weeks),"Historisk test · trenings-/valideringsforsøk")
        p={**DEFAULTS,'min_week_pct':week,'notifications':False};book=initial(p);marks=[]
        for i,f in enumerate(islice(iter(frames),b)):
            book,_=cycle(book,f['items'],f['at'],p)
            if i in (a-1,b-1):marks.append(equity(book))
        validation=marks[1]/marks[0]-1
        results.append({'week':week,'validation_return':validation,'book':book})
    winner=max(results,key=lambda r:r['validation_return'])
    # Holdout is evaluated only for the chosen strategy; never used for selection.
    report_progress(len(trial_weeks),len(trial_weeks),'Historisk test · uavhengig sluttperiode')
    book=winner['book'];start=equity(book)
    for f in islice(iter(frames),b,None):book,_=cycle(book,f['items'],f['at'],{**DEFAULTS,'min_week_pct':winner['week'],'notifications':False})
    return {'state':'COMPLETED','selected_week':winner['week'],'holdout_return':equity(book)/start-1,
            'validation_return':winner['validation_return'],'max_drawdown_pct':book.get('max_drawdown_pct',0),
            'trials':len(results),'days':unique_days,'production_changed':False,
            'limitation':'Observerte univers og modellkurser; ikke historisk Nordnet-kontoavkastning'}
