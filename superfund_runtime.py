"""Checkpointed catalogue batches and atomic model/shadow publication.

Only superfund/* keys are writable. Page-sized documents avoid rewriting the
whole universe. First coverage pass must finish before model selection starts.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import time
from superfund_data import catalog_page, normalize, details, fx_history, nok_rate
from superfund_engine import DEFAULTS, initial, cycle, at, valid_parameters
from resource_coordinator import coordinated, optional_capacity

PREFIX = 'superfund/'
MAX_PAGE = 60
MAX_ITEM_HISTORY = 60
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_DETAIL_ITEMS = 512
MAX_CATALOG_BYTES = 64 * 1024 * 1024
MAX_DETAIL_BYTES = 16 * 1024 * 1024


def storage():
    from services.storage_service import get_storage_service
    return get_storage_service()


def read(name, default=None):
    return storage().read_json(PREFIX+name, default)


def write(name, value):
    from resource_coordinator import verify_lane
    verify_lane()
    data = json.dumps(value, ensure_ascii=False, default=str).encode()
    if len(data) > MAX_STATE_BYTES: raise ValueError('Superfond dokumentbudsjett overskredet')
    return storage().write_json(PREFIX+name, value)


def now_iso(): return datetime.now(timezone.utc).isoformat()


def request_scan():
    def request(current):
        current = dict(current or {})
        if current.get('state') in ('QUEUED', 'RUNNING', 'PARTIAL'):
            return current
        return {'state': 'QUEUED', 'requested_at': now_iso(), 'message': 'Oppdatering lagt i kø; samme forespørsel brukes ved gjentatte trykk.'}
    return storage().mutate_json(PREFIX+'request.json', request, {})


def save_parameters(updates, actor='UI'):
    def commit(current):
        current = dict(current or {})
        old = {**DEFAULTS, **current.get('parameters', {})}
        new = valid_parameters({**old, **updates})
        history = list(current.get('history', []))
        if old != new:
            history.append({'at': now_iso(), 'actor': actor, 'before': old, 'after': new})
        return {**current, 'parameters': new, 'history': history[-100:]}
    state = storage().mutate_json(PREFIX+'parameter_audit.json', commit, {})
    # Authoritative config is the same atomic audit document; no second truth.
    return state


def config():
    return {**DEFAULTS, **read('parameter_audit.json', {}).get('parameters', {})}


def rollback(actor='UI'):
    audit = read('parameter_audit.json', {})
    if not audit.get('history'): return audit
    return save_parameters(audit['history'][-1]['before'], actor+' rollback')


def all_items(index=None):
    index = index or read('catalog_index.json', {})
    result = []
    for key in sorted(index.get('pages', {})):
        page = read('catalog/'+key+'.json', {})
        for item in page.get('items', []):
            detail = read('details/'+item['id']+'.json', {}) if item['id'] in index.get('details',{}) else {}
            result.append({**item, 'detail': detail})
    return result


def snapshot(): return read('snapshot.json', {})


def _update_page(block, index, now, fx):
    key = block['kind']+'-'+str(block['page'])
    previous = read('catalog/'+key+'.json', {})
    prior = {i['id']: i for i in previous.get('items', [])}
    items = []
    for row in block['rows']:
        try:
            item = normalize(row, block['kind'], now)
        except ValueError:
            continue
        old = prior.get(item['id'], {})
        observations = list(old.get('observations', []))
        # Bounded observed daily series, not historic data backfilled from returns.
        rate=nok_rate(item['currency'],item['price_at'],fx)
        if item['price_at'] and item['price']:
            point={'price_at':item['price_at'],'observed_at':now,'price':item['price'],'nok_price':item['price']*rate if rate else None}
            daily={o['price_at'][:10]:o for o in observations}
            daily[item['price_at'][:10]]=point
            observations=[daily[d] for d in sorted(daily)][-MAX_ITEM_HISTORY:]
        item['observations'] = observations
        short={}
        for n in (1,3,5,10,20):
            if len(observations)>n and observations[-1].get('nok_price') and observations[-n-1].get('nok_price'):
                first,last=observations[-n-1],observations[-1]
                short[str(n)]={'return_pct':(last['nok_price']/first['nok_price']-1)*100,'from':first['price_at'],'to':last['price_at']}
        item['observed_returns_nok']=short
        item['has_detail'] = old.get('has_detail', False)
        item['nok_rate'] = rate
        items.append(item)
    if block['rows'] and not items: raise ValueError('Ingen gyldige instrumenter i siden')
    page_value={'items':items,'updated_at':now,'source':block['url']}
    page_bytes=len(json.dumps(page_value).encode())
    total_bytes=sum(v.get('bytes',0) for k,v in index.get('pages',{}).items() if k!=key)+page_bytes
    if total_bytes>MAX_CATALOG_BYTES:raise ValueError('Katalogens totale 64 MiB lagringsbudsjett nådd')
    write('catalog/'+key+'.json', page_value)
    index.setdefault('pages', {})[key] = {'count': len(items), 'updated_at': now,'bytes':page_bytes}
    index.setdefault('totals', {})[block['kind']] = block['total']
    return index


def _enrich(items, index, budget=2):
    # Held positions first, then strongest screening signals; no fixed sector exclusion.
    held = set(snapshot().get('model', {}).get('positions', {}))
    queue = sorted(items, key=lambda x:(x['id'] not in held, x.get('name','').lower()!='nordnet global indeks', -(x.get('returns', {}).get('yield_1w') or -1000)))
    updated_ids = set()
    protected = held | {i['id'] for i in items if i.get('name','').lower()=='nordnet global indeks'}
    registry=index.setdefault('details',{})
    sizes=index.setdefault('detail_bytes',{})
    for item in queue:
        if len(updated_ids) >= budget: break
        old = item.get('detail', {})
        if old.get('verified_at') and (at(now_iso())-at(old['verified_at'])).days < 7: continue
        try:
            value = details(item)
            size=len(json.dumps(value,ensure_ascii=False).encode())
            if size>MAX_STATE_BYTES:raise ValueError('Produktdetalj overskrider dokumentbudsjett')
            # Rotate non-held cached details, rather than permanently excluding
            # every new candidate after the first 512 verified products.
            while ((item['id'] not in registry and len(registry)>=MAX_DETAIL_ITEMS)
                   or sum(sizes.values())-sizes.get(item['id'],0)+size>MAX_DETAIL_BYTES):
                victims=[k for k in registry if k not in protected and k!=item['id']]
                if not victims:raise ValueError('Detaljbudsjett brukt av beholdte produkter')
                victim=min(victims,key=lambda k:registry[k])
                storage().delete_json(PREFIX+'details/'+victim+'.json')
                registry.pop(victim);sizes.pop(victim,None)
                for cached in items:
                    if cached['id']==victim:cached['detail']={};cached['has_detail']=False
            write('details/'+item['id']+'.json', value)
            item['detail'] = value; item['has_detail'] = True; updated_ids.add(item['id'])
            registry[item['id']]=value['verified_at'];sizes[item['id']]=size
        except Exception as exc:
            item['detail_error'] = str(exc)[:180]
    for key in index.get('pages', {}):
        page = read('catalog/'+key+'.json', {})
        changed = False
        for item in page.get('items', []):
            if item['id'] in updated_ids: item['has_detail'] = True; changed = True
        if changed: write('catalog/'+key+'.json', page)
    if updated_ids:write('catalog_index.json',index)
    return items


def _coverage(index, items, now):
    expected_pages = {k: min(MAX_PAGE, (int(v)+99)//100) for k,v in index.get('totals', {}).items()}
    complete = len(expected_pages)==2 and all(all(k+'-'+str(n) in index.get('pages', {}) for n in range(1,v+1)) for k,v in expected_pages.items())
    # De-duplicate exact listing IDs; ISIN de-duplication happens before buying.
    fresh = sum(bool(i.get('price_at')) and (at(now)-at(i['price_at'])).days <= DEFAULTS['max_quote_age_days'] for i in items)
    return {'state': 'COMPLETE_CATALOG' if complete else 'PARTIAL_CATALOG', 'complete': complete,
            'source_totals': index.get('totals', {}), 'listings':len(items),
            'unique_isins': len({i['isin'] for i in items}), 'fresh_prices':fresh,
            'details':sum(bool(i.get('detail')) for i in items),
            'history': 'Kun observerte kurspunkter; publiserte periodeavkastninger er ikke daglig historikk',
            'news': 'E24 RSS og offentlige produktpubliseringer; full bransje-/forvalterdekning ikke garantert',
            'cost_accounting': 'Handelsfriksjon estimert; plattformavgift/refusjon ikke avstemt',
            'history_points_cap_per_listing':MAX_ITEM_HISTORY}


@coordinated('superfund')
def run_batch(page_budget=3, detail_budget=2, *, page_provider=catalog_page, fx_provider=fx_history, enrich=True):
    started = time.monotonic(); now = now_iso()
    capacity = optional_capacity()
    if not capacity['ready']:
        deferred={'state':'DEFERRED_CAPACITY', **capacity,
            'message':'Superfond utsatt: for lite minne eller høy CPU-belastning. Prøves igjen i neste cron.'}
        write('job.json',deferred)
        return deferred
    request = read('request.json', {})
    last = read('job.json', {})
    if request.get('state') not in ('QUEUED','RUNNING','PARTIAL') and last.get('completed_at') and (at(now)-at(last['completed_at'])).total_seconds()<1800:
        return {'state':'NOT_DUE'}
    write('request.json', {**request, 'state':'RUNNING', 'heartbeat_at':now})
    index = read('catalog_index.json', {'pages':{}, 'totals':{}, 'cursor':{'kind':'fond','page':1}})
    errors = []; processed = 0
    fx = read('fx.json', {'days':{}})
    try:
        if not fx.get('updated_at') or (at(now)-at(fx['updated_at'])).total_seconds()>86400:
            fx = {**fx_provider(), 'updated_at':now}; write('fx.json',fx)
        for _ in range(min(6, max(1,page_budget))):
            cursor = index['cursor']; kind, page = cursor['kind'],cursor['page']
            block = page_provider(kind,page)
            if block['total'] > MAX_PAGE*100: raise ValueError('Katalog overskrider sidebudsjett; dekning blokkert')
            index = _update_page(block,index,now,fx)
            count = max(1,(block['total']+99)//100)
            index['cursor'] = {'kind':kind,'page':page+1} if page<count else {'kind':'etf' if kind=='fond' else 'fond','page':1}
            write('catalog_index.json',index); processed+=1
            # Checkpoint each page; wall budget avoids monopolising the cron lane.
            if time.monotonic()-started > 40: break
        items = all_items(index)
        # Refresh FX on cached items too; don't trade on a rate newer than quote day.
        for item in items: item['nok_rate']=nok_rate(item['currency'],item['price_at'],fx)
        if enrich and time.monotonic()-started < 40: items=_enrich(items,index, min(4,detail_budget))
        if enrich and time.monotonic()-started < 40:
            try:refresh_news([i for i in items if i.get('detail')])
            except Exception as exc:errors.append('Nyheter: '+str(exc)[:150])
        # Duplicate pages can occur during source reordering; last observed listing wins.
        items = list({i['id']:i for i in items}.values())
        coverage = _coverage(index,items,now)
        if not coverage['complete']:
            write('job.json', {'state':'PARTIAL','coverage':coverage,'completed_at':now,
                              'seconds':round(time.monotonic()-started,2),'errors':errors})
            write('request.json',{'state':'PARTIAL','heartbeat_at':now})
            return read('job.json',{})
        p=config(); previous=snapshot()
        model, result=cycle(previous.get('model'),items,now,p)
        shadows={}; shadow_rules=previous.get('shadow_rules') or {'fast':{**p,'min_week_pct':0.5},'patient':{**p,'min_week_pct':2.0}}
        for name, rules in shadow_rules.items():
            shadows[name],_=cycle(previous.get('shadows',{}).get(name),items,now,rules)
        from superfund_learning import forward_evidence
        learning=forward_evidence(previous,model,shadows,items,now,p)
        from superfund_learning import archive_frame
        try:
            archive_status=archive_frame(items,now,p)
        except Exception as exc:
            archive_status={'state':'FAILED','error':str(exc)[:200]}
        # One commit publishes model, trade ledger, paired shadows and analysis.
        from app_version import APP_VERSION
        payload={'at':now,'version':APP_VERSION,'model':model,'shadows':shadows,'shadow_rules':shadow_rules,'learning':learning,'archive_status':archive_status,
                 'parameters':p,'coverage':coverage,'frame':model.get('last_frame'),
                 'report':previous.get('report',{}),
                 'candidates':[{k:v for k,v in r.items() if k not in ('observations','detail')} for r in result['rows'][:100]],
                 'blocked_counts':{},'report_pending':previous.get('report_pending',False) or result['state']!='UNCHANGED','notification_pending':[],'attention_history':previous.get('attention_history',{})}
        for row in result['rows']:
            for reason in row['blocks']:payload['blocked_counts'][reason]=payload['blocked_counts'].get(reason,0)+1
        for row in result['rows']:
            week=row.get('returns',{}).get('yield_1w')
            prior_attention=payload['attention_history'].get(row['id'])
            if week is not None and week>=3 and not row['blocks'] and (not prior_attention or (at(now)-at(prior_attention)).total_seconds()>172800):
                payload['attention_history'][row['id']]=now
                result['changes'].append({'side':'TIDLIG VARSEL','id':row['id'],'name':row['name'],
                    'reason':f"Ukesoppgang {week:.2f}%. Kandidat, ikke en reell kjøpsordre. Kursdato {row['price_at'][:10]}"})
        payload['attention_history']=dict(list(payload['attention_history'].items())[-500:])
        old_pending=previous.get('notification_pending',[])
        payload['notification_pending']=old_pending+result['changes']
        proposal=learning.get('proposal',{})
        if proposal.get('state')=='WAITING_APPROVAL' and proposal.get('id')!=previous.get('learning',{}).get('proposal',{}).get('id'):
            payload['notification_pending'].append({'side':'FORSLAG','id':proposal['id'],'reason':proposal['source']})
        if len(payload['notification_pending'])>1000:
            raise ValueError('Varslingskø full; publisering utsatt, ingen handelsvarsler slettes')
        write('snapshot.json',payload)
        write('request.json',{'state':'COMPLETED','completed_at':now})
        job={'state':'COMPLETED','completed_at':now,'coverage':coverage,'pages_processed':processed,
             'seconds':round(time.monotonic()-started,2),'errors':errors,'capacity':capacity}
        write('job.json',job)
        # Side effects are retryable after atomic portfolio commit; failures cannot repeat trades.
        try:
            deliver_pending()
        except Exception as exc:
            job['delivery_error']=str(exc)[:300];write('job.json',job)
        return job
    except Exception as exc:
        job={'state':'FAILED','completed_at':now,'error':f'{type(exc).__name__}: {str(exc)[:350]}',
             'pages_processed':processed,'seconds':round(time.monotonic()-started,2),
             'message':'Siste komplette portefølje/rapport beholdes. Sidecheckpoint brukes ved neste kjøring.'}
        write('job.json',job);write('request.json',{'state':'PARTIAL','heartbeat_at':now})
        return job


def refresh_news(items):
    cached=read('news.json',{})
    if cached.get('at') and (at(now_iso())-at(cached['at'])).total_seconds()<21600:
        return cached
    from news_source_registry import SOURCE_REGISTRY,fetch_rss_source
    spec=next(s for s in SOURCE_REGISTRY['Norge'] if s['id']=='e24')
    tokens=['fond','ETF','rente','inflasjon','valuta','indeks']
    for item in items:
        for h in item.get('detail',{}).get('holdings',[])[:3]:
            if h.get('name'):tokens.append(h['name'])
    rows,health=fetch_rss_source(spec,tokens[:40])
    value={'at':now_iso(),'items':rows[:20],'health':health,
           'scope':'E24 RSS og produktpubliseringer; relevans er søketreff, ikke kjøpssignal'}
    write('news.json',value)
    return value


def deliver_pending():
    s=snapshot()
    if not s: return
    if s.get('report_pending'):
        from superfund_reports import publish
        s['report']=publish(s);s['report_pending']=False;write('snapshot.json',s)
    if s.get('notification_pending') and config()['notifications']:
        from notifier import send_pushover_alert, normalize_notification_result
        changes=s['notification_pending'][:5]
        text='SUPERFOND · MODELLHANDEL\n'+'\n'.join(f"{x['side']} · {x.get('name',x['id'])} · {x.get('reason','')}" for x in changes[:5])
        # Standard notifier handles quiet periods; no live broker execution.
        ok, detail=normalize_notification_result(send_pushover_alert(text,title='Superfondportefølje',
            url=s.get('report',{}).get('url') or None,url_title='Åpne rapport',priority=0))
        s['delivery']={'at':now_iso(),'sent':ok,'detail':str(detail)[:200]}
        if ok:s['notification_pending']=s['notification_pending'][len(changes):]
        write('snapshot.json',s)
