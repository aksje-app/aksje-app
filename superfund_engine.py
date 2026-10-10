"""Pure fund model: delayed fills, frozen rules, no broker transactions."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math

DEFAULTS = {'capital_nok': 1000000.0, 'max_positions': 8, 'max_position_pct': 12.5,
            'category_cap_pct': 30.0, 'sector_cap_pct': 35.0, 'region_cap_pct': 60.0, 'reserve_pct': 10.0, 'min_week_pct': 1.0,
            'max_risk': 5, 'max_cost_pct': 2.0, 'max_spread_pct': 0.5,
            'stop_pct': 6.0, 'protect_from_pct': 2.0, 'retain_gain_pct': 55.0,
            'cooldown_days': 7, 'fee_bps': 10.0, 'fx_bps': 25.0,
            'max_quote_age_days': 5, 'enabled': True, 'notifications': True}


def at(s):
    value = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Tidspunkt må ha tidssone')
    return value.astimezone(timezone.utc)


def initial(parameters=None):
    p = {**DEFAULTS, **(parameters or {})}
    return {'cash': p['capital_nok'], 'positions': {}, 'orders': [], 'trades': [],
            'cooldowns': {}, 'history': [], 'initial_capital': p['capital_nok'], 'last_frame': ''}


def valid_parameters(p):
    for k in DEFAULTS:
        if k not in p:
            raise ValueError('Mangler parameter ' + k)
        if isinstance(DEFAULTS[k], bool):
            if not isinstance(p[k], bool): raise ValueError(k)
        elif not math.isfinite(float(p[k])):
            raise ValueError(k)
    if not (1 <= p['max_positions'] <= 20 and 0 < p['max_position_pct'] <= 25
            and 0 <= p['reserve_pct'] <= 80 and 0 < p['stop_pct'] <= 20
            and 0 <= p['retain_gain_pct'] <= 100 and 0 <= p['cooldown_days'] <= 90
            and 0 <= p['fee_bps'] <= 100 and 0 <= p['fx_bps'] <= 200):
        raise ValueError('Parameter utenfor tillatte grenser')
    if not (1<=p['max_risk']<=7 and 0<=p['max_cost_pct']<=10 and 0<=p['max_spread_pct']<=5 and 0<=p['min_week_pct']<=20 and 1<=p['max_quote_age_days']<=10 and 1<=p['category_cap_pct']<=100 and 1<=p['sector_cap_pct']<=100 and 1<=p['region_cap_pct']<=100 and p['capital_nok']>0):
        raise ValueError('Ugyldig risikoparameter')
    return p


def eligibility(item, now, p, *, buy=True):
    problems = []
    try:
        price_time, observed = at(item['price_at']), at(item['observed_at'])
        if price_time > now or observed > now: problems.append('FREMTIDIGE_DATA')
        if (now - price_time).total_seconds() > p['max_quote_age_days'] * 86400: problems.append('GAMMEL_KURS')
    except (ValueError, KeyError, TypeError):
        problems.append('MANGLER_KURSDATO')
    if not item.get('price') or item.get('price', 0) <= 0 or not item.get('nok_rate') or item.get('nok_rate', 0) <= 0:
        problems.append('MANGLER_KURS_ELLER_VALUTA')
    if buy:
        if not item.get('tradable'): problems.append('IKKE_HANDLINGSBAR')
        if item.get('complex'): problems.append('KOMPLEKST_PRODUKT')
        if item.get('category') in (None, '', 'UKJENT'): problems.append('UKJENT_KATEGORI')
        if item.get('asset') != 'Aksje': problems.append('SEPARAT_RENTEKATEGORI')
        if item.get('risk') is None or item['risk'] > p['max_risk']: problems.append('RISIKO')
        if item.get('cost_pct') is None or item['cost_pct'] > p['max_cost_pct']: problems.append('KOSTNAD')
        if not item.get('detail'): problems.append('DETALJER_I_KØ')
        detail=item.get('detail',{})
        if detail.get('verified_at') and (at(detail['verified_at'])>now or (now-at(detail['verified_at'])).days>7):problems.append('GAMLE_DETALJER')
        if detail.get('source_url') and (not detail.get('sectors') or not detail.get('regions') or not detail.get('exposure_at')):problems.append('EKSPONERING_MANGLER')
        if detail.get('exposure_at'):
            exposure_time=at(str(detail['exposure_at'])[:10]+'T00:00:00+00:00')
            if exposure_time>now or (now-exposure_time).days>120:problems.append('GAMMEL_EKSPONERING')
        # Distribution accounting requires cash-flow data; first model admits accumulation only.
        if 'akkumul' not in str(item.get('distribution', '')).lower(): problems.append('UTBYTTEDATA_MANGLER')
        if item.get('kind') == 'etf':
            if item.get('detail', {}).get('ucits') is not True: problems.append('UCITS_UVERIFISERT')
            if item.get('spread_pct') is None or item['spread_pct'] > p['max_spread_pct']: problems.append('SPREAD')
        else:
            trade = item.get('detail', {}).get('trading', {})
            if trade.get('buyFrequency') != 'DAILY' or trade.get('sellFrequency') != 'DAILY': problems.append('HANDELSFRIST_UVERIFISERT')
    return problems


def rank(items, now, p):
    groups = {}
    rows = []
    for item in items:
        r = item.get('returns', {})
        week, month, quarter = r.get('yield_1w'), r.get('yield_1m'), r.get('yield_3m')
        score = None if None in (week, month, quarter) else 0.6 * week + 0.25 * month + 0.15 * quarter
        row = {**item, 'score': score, 'blocks': eligibility(item, now, p)}
        if score is None: row['blocks'].append('MANGLER_TREND')
        elif week < p['min_week_pct'] or quarter <= 0: row['blocks'].append('SVAK_TREND')
        groups.setdefault((item.get('category'), item.get('returns_currency')), []).append(row)
        rows.append(row)
    for group in groups.values():
        group.sort(key=lambda r: (-(r['score'] if r['score'] is not None else -1e9), r['id']))
        for i, row in enumerate(group, 1): row['rank'] = i
    return sorted(rows, key=lambda r: (-(r['score'] if r['score'] is not None else -1e9), r['id']))


def frame_id(items):
    evidence = [{k: x.get(k) for k in ('id', 'price', 'price_at', 'returns', 'nok_rate', 'tradable', 'complex', 'risk', 'cost_pct', 'spread_pct', 'distribution', 'detail')} for x in sorted(items, key=lambda a:a['id'])]
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()[:20]


def overlap(a, b):
    """Known top-holding intersection only; partial holdings never imply full coverage."""
    aa = {x.get('name'): float(x.get('weight') or 0) for x in a.get('detail', {}).get('holdings', [])}
    bb = {x.get('name'): float(x.get('weight') or 0) for x in b.get('detail', {}).get('holdings', [])}
    return sum(min(w, bb.get(n, 0)) for n, w in aa.items() if n)


def fill_allocation_limit(item, positions, equity, allocation, p):
    """Recheck concentration at execution, after earlier pending fills."""
    category_value=sum(x['quantity']*x['last_nok'] for x in positions.values() if x['category']==item['category'])
    allocation=min(allocation,equity*p['category_cap_pct']/100-category_value)
    for field,cap in [('sectors',p['sector_cap_pct']),('regions',p['region_cap_pct'])]:
        for exposure in item.get('detail',{}).get(field,[]):
            weight=float(exposure.get('weight') or 0)/100
            if weight<=0:continue
            used=sum(x['quantity']*x['last_nok']*sum(float(y.get('weight') or 0)/100 for y in x.get(field,[]) if y.get('exposureType')==exposure.get('exposureType')) for x in positions.values())
            allocation=min(allocation,(equity*cap/100-used)/weight)
    return allocation


def cycle(state, items, now, parameters=None, *, buy_hold=False):
    p = valid_parameters({**DEFAULTS, **(parameters or {})})
    s = deepcopy(state or initial(p)); now = at(now) if isinstance(now, str) else now
    rows = rank(items, now, p); lookup = {r['id']: r for r in rows}
    fid = hashlib.sha256((frame_id(items)+json.dumps(p,sort_keys=True)+str(buy_hold)).encode()).hexdigest()[:20]
    if s.get('last_frame') == fid:
        return s, {'state': 'UNCHANGED', 'changes': [], 'rows': rows}
    changes = []; pending = []
    # Previously queued orders execute only on evidence dated AFTER the decision.
    for order in s['orders']:
        item = lookup.get(order['id'])
        if item is None or eligibility(item, now, p, buy=False): pending.append(order); continue
        if at(item['price_at']).date() <= at(order['requested_at']).date(): pending.append(order); continue
        if at(item['observed_at']) <= at(order['requested_at']): pending.append(order); continue
        if item['kind'] == 'fond':
            trade = item.get('detail', {}).get('trading', {})
            next_at = order.get('next_at')
            if not next_at or now < at(next_at): pending.append(order); continue
        price = item['price'] * item['nok_rate']
        friction = (p['fee_bps'] + (p['fx_bps'] if item['currency'] != 'NOK' else 0)) / 10000
        if item['kind'] == 'etf': friction += (item.get('spread_pct') or 0) / 200
        if order['side'] == 'BUY':
            if not p['enabled'] and not buy_hold:
                changes.append({'side':'CANCEL','id':item['id'],'reason':'Modellutvelgelse deaktivert'});continue
            # Recheck every gate; changed evidence can cancel a pending model buy.
            blocks = [b for b in item['blocks'] if not buy_hold or b not in ('SVAK_TREND','MANGLER_TREND')]
            if blocks:
                changes.append({'side': 'CANCEL', 'id': item['id'], 'reason': ', '.join(item['blocks'])}); continue
            equity_before = s['cash']+sum(x['quantity']*x['last_nok'] for x in s['positions'].values())
            allocation = min(order['allocation'], s['cash']-equity_before*p['reserve_pct']/100, equity_before*(100 if buy_hold else p['max_position_pct'])/100)
            if not buy_hold:
                allocation=fill_allocation_limit(item,s['positions'],equity_before,allocation,p)
                if len(s['positions'])>=p['max_positions'] or any(x['isin']==item['isin'] for x in s['positions'].values()):allocation=0
                if allocation<equity_before*0.01:allocation=0
            if allocation <= 0:
                changes.append({'side':'CANCEL','id':item['id'],'reason':'Kapital eller eksponeringsgrense ved utførelse'});continue
            qty = allocation / (price * (1 + friction))
            s['cash'] -= allocation
            s['positions'][item['id']] = {'id': item['id'], 'isin': item['isin'], 'name': item['name'],
                'category': item['category'], 'quantity': qty, 'entry_nok': price, 'cost_nok': allocation,
                'last_nok': price, 'peak_nok': price, 'bought_at': now.isoformat(),
                'rank_at_buy': item['rank'], 'score_at_buy': item['score'], 'rank_now': item['rank'],
                'decision_at': order['requested_at'], 'kind': item['kind'],
                'sectors':item.get('detail',{}).get('sectors',[]),'regions':item.get('detail',{}).get('regions',[])}
            pnl = None
        else:
            pos = s['positions'].pop(item['id'], None)
            if not pos: continue
            proceeds = pos['quantity'] * price * (1 - friction); s['cash'] += proceeds
            pnl = proceeds - pos['cost_nok']; s['cooldowns'][item['isin']] = now.isoformat()
        event = {**order, 'name':item['name'], 'executed_at': now.isoformat(), 'price_at': item['price_at'],
                 'price_nok': price, 'pnl_nok': pnl, 'execution': 'DELAYED_MODEL_ESTIMATE'}
        s['trades'].append(event); changes.append(event)
    s['orders'] = pending
    pending_ids = {o['id'] for o in pending}
    for key, pos in s['positions'].items():
        row = lookup.get(key)
        if not row or eligibility(row, now, p, buy=False): continue
        price = row['price'] * row['nok_rate']; pos['last_nok'] = price
        pos['peak_nok'] = max(pos['peak_nok'], price); pos['rank_now'] = row['rank']
        gain = pos['peak_nok'] / pos['entry_nok'] - 1
        floor = pos['peak_nok'] * (1 - p['stop_pct'] / 100)
        if gain >= p['protect_from_pct'] / 100:
            floor = max(floor, pos['entry_nok'] * (1 + gain * p['retain_gain_pct'] / 100))
        pos['floor_nok'] = max(pos.get('floor_nok', 0), floor)
        if p['enabled'] and not buy_hold and key not in pending_ids and (price <= pos['floor_nok'] or (row.get('returns', {}).get('yield_1w') or 0) < -p['min_week_pct']):
            s['orders'].append({'id': key, 'side': 'SELL', 'requested_at': now.isoformat(),
                'next_at': row.get('detail', {}).get('trading', {}).get('nextSellAt'),
                'reason': 'Salgsgrense/trend svekket; senere modellkurs, ikke garantert stoppris'})
    equity = s['cash'] + sum(x['quantity'] * x['last_nok'] for x in s['positions'].values())
    committed = sum(o.get('allocation', 0) for o in s['orders'] if o['side'] == 'BUY')
    if p['enabled'] and not buy_hold:
        slots = p['max_positions'] - len(s['positions']) - sum(o['side'] == 'BUY' for o in s['orders'])
        owned = {x['isin'] for x in s['positions'].values()}
        for row in rows:
            if slots <= 0: break
            if row['blocks'] or row['isin'] in owned or row['id'] in {o['id'] for o in s['orders']}: continue
            cooldown = s['cooldowns'].get(row['isin'])
            if cooldown and (now - at(cooldown)).days < p['cooldown_days']: continue
            cat = row['category']
            cat_value = sum(x['quantity'] * x['last_nok'] for x in s['positions'].values() if x['category'] == cat)
            cat_value += sum(o.get('allocation', 0) for o in s['orders'] if o.get('category') == cat and o['side']=='BUY')
            allocation = min(equity * p['max_position_pct']/100, s['cash']-committed-equity*p['reserve_pct']/100,
                             equity*p['category_cap_pct']/100-cat_value)
            # Look through fund categories to actual known sector/region weights.
            for field, cap in [('sectors',p['sector_cap_pct']),('regions',p['region_cap_pct'])]:
                exposure = row.get('detail',{}).get(field,[])
                for x in exposure:
                    weight = float(x.get('weight') or 0)/100
                    if weight <= 0:continue
                    used = 0
                    for pos in s['positions'].values():
                        used += pos['quantity']*pos['last_nok']*sum(float(y.get('weight') or 0)/100 for y in pos.get(field,[]) if y.get('exposureType')==x.get('exposureType'))
                    for order in s['orders']:
                        if order['side']!='BUY':continue
                        used += order.get('allocation',0)*sum(float(y.get('weight') or 0)/100 for y in lookup.get(order['id'],{}).get('detail',{}).get(field,[]) if y.get('exposureType')==x.get('exposureType'))
                    allocation = min(allocation,(equity*cap/100-used)/weight)
            if allocation < equity * 0.01:
                row['blocks'].append('KAPITAL_ELLER_EKSPONERING');continue
            if any(overlap(row, lookup.get(k, {})) >= 40 for k in s['positions']):
                row['blocks'].append('OVERLAPP');continue
            s['orders'].append({'id': row['id'], 'isin': row['isin'], 'side': 'BUY', 'category': cat,
                'allocation': allocation, 'requested_at': now.isoformat(),
                'next_at': row.get('detail', {}).get('trading', {}).get('nextBuyAt'),
                'reason': f"Positiv ukestrend, kategori-rang {row['rank']}; risiko/kostnad godkjent"})
            committed += allocation; slots -= 1; owned.add(row['isin'])
    s['last_frame'] = fid
    s['history'].append({'at': now.isoformat(), 'equity': equity, 'cash': s['cash'], 'frame': fid})
    s['history'] = s['history'][-1500:]; s['trades'] = s['trades'][-2000:]
    s['peak_equity'] = max(s.get('peak_equity', equity), equity)
    s['max_drawdown_pct'] = max(s.get('max_drawdown_pct', 0), (1-equity/s['peak_equity'])*100)
    return s, {'state': 'COMPLETED', 'changes': changes, 'rows': rows,
               'equity': equity, 'frame': fid, 'orders_pending': len(s['orders'])}
