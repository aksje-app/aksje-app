"""Cached exposure controls. Scenario arithmetic, never political predictions."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import re

EVENT = {'id':'BR_ELECTION_2026', 'name':'Brasil · andre valgomgang',
         'date':'2026-10-25', 'review_from':'2026-10-19', 'review_to':'2026-10-23',
         'source':'https://www.tre-sp.jus.br/comunicacao/noticias/2026/Maio/eleicoes-2026-outubro-tem-datas-do-1o-e-do-2o-turnos-definidas-pela-constituicao'}


def stamp(value):
    dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Tidssone mangler')
    return dt.astimezone(timezone.utc)


def active(now):
    return '2026-10-11' <= now.astimezone(ZoneInfo('America/Fortaleza')).date().isoformat() <= EVENT['date']


def brazil_weight(row):
    """Conservative upper bound; broad/unknown regions aren't invented country data."""
    regions=row.get('detail',{}).get('regions',row.get('regions',[])) or []
    known=0.0
    for x in regions:
        label=str(x.get('exposureType') or x.get('name') or '').upper()
        if label in ('BRAZIL','BRASIL','BR'):
            try: w=float(x.get('weight'))
            except (TypeError,ValueError): return 1.0,'Brasil; vekt ukjent, øvre grense'
            if not math.isfinite(w) or not 0<=w<=100:return 1.0,'Brasil; vekt ugyldig, øvre grense'
            known+=w/100
    if known:
        try: total=sum(float(x.get('weight') or 0) for x in regions)
        except (TypeError,ValueError):total=0
        if not math.isfinite(total):total=0
        unknown=max(0,1-min(100,total)/100)
        for x in regions:
            label=str(x.get('exposureType') or x.get('name') or '').upper()
            if label in ('LATIN_AMERICA','LATIN AMERICA','LATIN-AMERIKA','GLOBAL','EMERGING_MARKETS'):
                try:w=float(x.get('weight') or 0)/100
                except (TypeError,ValueError):w=1
                unknown+=w if math.isfinite(w) and 0<=w<=1 else 1
        return min(1.0,known+unknown),'Kildens Brasil-vekt' if unknown<.0001 else 'Brasil-vekt + ukjent rest; øvre grense'
    area=str(row.get('investment_area') or '').upper()
    name=str(row.get('name') or '')
    if re.search(r'\b(?:MSCI|FTSE)\s+Brazil\b',name,re.I) or area in ('BRAZIL','BRASIL','BR'):
        return 1.0,'Brasil-etikett; konservativ øvre grense'
    if any(str(x.get('exposureType') or x.get('name') or '').upper() in ('LATIN_AMERICA','LATIN AMERICA','LATIN-AMERIKA','GLOBAL','EMERGING_MARKETS') for x in regions) or not regions:
        return 1.0,'Landfordeling ukjent; konservativ øvre grense'
    # A partial top-region list cannot prove zero Brazilian exposure.
    try:total=sum(float(x.get('weight') or 0) for x in regions)
    except (TypeError,ValueError):total=0
    if not math.isfinite(total) or total<0:total=0
    return max(0.0,1-min(100,total)/100),'Rest av landfordeling ukjent' if total<99.99 else 'Kildens landfordeling'


def holdings(row):
    return row.get('detail',{}).get('holdings',row.get('holdings',[])) or []


def intersection(a,b):
    aa={str(x.get('isin') or x.get('name') or '').strip().casefold():float(x.get('weight') or 0) for x in holdings(a)}
    bb={str(x.get('isin') or x.get('name') or '').strip().casefold():float(x.get('weight') or 0) for x in holdings(b)}
    return sum(min(w,bb.get(n,0)) for n,w in aa.items() if n)


def related(a,b):
    return a.get('isin')==b.get('isin') or (brazil_weight(a)[0]>0 and brazil_weight(b)[0]>0) or intersection(a,b)>=40


def exposure_used(positions,orders,lookup):
    return sum(x['quantity']*x['last_nok']*brazil_weight(x)[0] for x in positions.values())+sum(o.get('allocation',0)*brazil_weight(lookup.get(o['id'],o))[0] for o in orders if o['side']=='BUY')


def event_allocation(row,positions,orders,lookup,equity,allocation,p,now):
    if not active(now):return allocation
    w,_=brazil_weight(row)
    if w<=0:return allocation
    return min(allocation,max(0,(equity*p['brazil_cap_pct']/100-exposure_used(positions,orders,lookup))/w))


def register_exit(state,pos,now,p):
    from copy import deepcopy
    end=max(now+timedelta(days=max(p['event_cooldown_days'],p['cooldown_days'])),stamp('2026-10-26T00:00:00-03:00'))
    ledger=state.setdefault('event_exits',{})
    ledger[pos['isin']]={'sold_at':now.isoformat(),'until':end.isoformat(),'exposure':deepcopy(pos),'confirmations':{}}
    # Bound storage without removing a live quarantine.
    for key in list(ledger):
        if stamp(ledger[key]['until']) < now-timedelta(days=90):ledger.pop(key)


def reentry_blocks(state,row,now):
    blocks=[]
    for exit in state.get('event_exits',{}).values():
        if not related(row,exit['exposure']):continue
        if now<stamp(exit['until']):blocks.append('HENDELSESKARANTENE');continue
        # Distinct fresh quote dates AFTER quarantine, per instrument; scans don't count.
        registry=exit.setdefault('confirmations',{})
        confirmations=registry.get(row['isin'],[])
        if not row.get('blocks') and row.get('price_at') and stamp(row['price_at'])>=stamp(exit['until']) and stamp(row['observed_at'])>=stamp(exit['until']):
            d=row['price_at'][:10]
            if d not in confirmations:confirmations.append(d);confirmations[:]=sorted(confirmations)[-2:]
            if row['isin'] not in registry and len(registry)>=512:registry.pop(next(iter(registry)))
            registry[row['isin']]=confirmations
        if len(confirmations)<2:blocks.append('KREVER_TO_NYE_POSITIVE_KURSDATOER')
    return sorted(set(blocks))


def risk_view(state,items,now,p):
    lookup={x['id']:x for x in items};positions=state.get('positions',{})
    equity=state.get('cash',0)+sum(x['quantity']*x['last_nok'] for x in positions.values())
    exposure=sum(x['quantity']*x['last_nok']*brazil_weight(x)[0] for x in positions.values())
    known=sum(x['quantity']*x['last_nok'] for x in positions.values() if 'ukjent' not in brazil_weight(x)[1] and 'øvre grense' not in brazil_weight(x)[1])
    rows=[];proposals=[];remaining=max(0,exposure-equity*p['brazil_cap_pct']/100)
    for key,pos in sorted(positions.items(),key=lambda kv:-(kv[1]['quantity']*kv[1]['last_nok']*brazil_weight(kv[1])[0])):
        value=pos['quantity']*pos['last_nok'];w,source=brazil_weight(pos)
        drop=(1-pos['last_nok']/pos['peak_nok'])*100
        rows.append({'id':key,'name':pos['name'],'brazil_upper_pct':w*100,'source':source,'drop_from_peak_pct':drop,
                     'stop_status':'STOPP' if pos['last_nok']<=pos.get('floor_nok',0) else 'NÆR STOPP' if drop>=2.25 else 'ADVARSEL' if drop>=1.5 else 'NORMAL'})
        if active(now) and remaining>0 and w>0 and not any(o['id']==key for o in state.get('orders',[])):
            fraction=min(1,remaining/(value*w));remaining-=value*w*fraction
            evidence={'event':EVENT['id'],'id':key,'quantity':pos['quantity'],'last_nok':pos['last_nok'],'fraction':fraction,
                      'exposure':exposure,'equity':equity,'cap':p['brazil_cap_pct'],'price_at':lookup.get(key,{}).get('price_at')}
            pid=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()[:20]
            proposals.append({'id':pid,'position_id':key,'name':pos['name'],'fraction':fraction,'estimated_nok':value*fraction,
                              'quantity':pos['quantity'],'state':'WAITING_APPROVAL','reason':'Reduser konservativ Brasil-eksponering til 10 %; senere modellkurs'})
    overlap=[]
    keys=list(positions)
    for n,a in enumerate(keys):
        for b in keys[n+1:]:
            shared=intersection(lookup.get(a,positions[a]),lookup.get(b,positions[b]))
            if shared:overlap.append({'a':positions[a]['name'],'b':positions[b]['name'],'known_shared_pct':shared})
    pct=100*exposure/equity if equity else 0
    # Explicit rule indicator, not a fitted probability or investment forecast.
    score=min(100,round(min(50,pct/p['brazil_cap_pct']*25)+min(25,state.get('max_drawdown_pct',0)*5)+(25 if active(now) and exposure else 0)))
    return {'event':{**EVENT,'active':active(now),'review_due':EVENT['review_from']<=now.astimezone(ZoneInfo('America/Fortaleza')).date().isoformat()<=EVENT['review_to']},
            'brazil_upper_nok':exposure,'brazil_upper_pct':pct,'cap_pct':p['brazil_cap_pct'],'country_data_coverage_pct':100*known/equity if equity else 0,
            'risk_indicator':score,'indicator_method':'0–50 konsentrasjon + 0–25 historisk fall + 25 aktiv hendelse. Regelindikator, ikke prognose.',
            'stress':{'asset_drop_pct':10,'currency_drop_pct':10,'combined_drop_pct':19,'portfolio_loss_upper_nok':exposure*.19},
            'positions':rows,'known_overlap':overlap,'proposals':proposals,
            'quarantines':[{'isin':key,'until':e['until']} for key,e in state.get('event_exits',{}).items()],
            'currency_note':'Handelsvaluta er ikke underliggende valutaeksponering. Historisk BRL-effekt kan ikke skilles ut uten fondets valutadata.'}
