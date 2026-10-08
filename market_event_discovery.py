"""Bounded official Norwegian events, independent of portfolio finalist ranking.

Events reserve analysis capacity only. They never alter scores or authorize orders.
Other jurisdictions require their own verified source adapters.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import math
import re
import time
from urllib.parse import urlencode
import urllib.request

from services.storage_service import get_storage_service

KEY = 'market_events/norway.json'
NEWS_API = 'https://api3.oslo.oslobors.no/v1/newsreader/'
SHORT_API = 'https://ssr.finanstilsynet.no/api/v2/instruments'
MAX_EVENTS = 2000
MAX_DETAILS = 6
POLL_SECONDS = 900


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def event_id(event):
    fields = ('source_url', 'isin', 'actor', 'occurred_at') if str(event.get('kind', '')).startswith('SHORT') else ('source_url', 'kind', 'quantity')
    return hashlib.sha256(json.dumps([event.get(k) for k in fields], ensure_ascii=False).encode()).hexdigest()[:24]


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def _text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()


def insider_events(messages, details, now):
    """Official metadata is discovery evidence; only explicit purchase text is a purchase.

    Options, compensation, borrowed shares and transfers remain unclassified.
    Publication time is used, never a guessed trade time or inferred execution price.
    """
    out = []
    for meta in messages[:200]:
        date = timestamp(meta.get('publishedTime'))
        if not date or not now - timedelta(days=90) <= date <= now:
            continue
        if meta.get('test') or meta.get('correctedByMessageId') or not any(
                c.get('id') == 1102 for c in meta.get('category', [])):
            continue
        mid = str(meta.get('messageId') or meta.get('id') or '')
        if not mid.isdigit() or not meta.get('issuerSign'):
            continue
        detail = details.get(mid, {})
        body = _text(detail.get('body'))
        e = dict(kind='INSIDER_NOTIFICATION', issuer=meta.get('issuerName', ''),
                 issuer_symbol=meta['issuerSign'], market='Norge', occurred_at=date.isoformat(),
                 observed_at=now.isoformat(), source_url='https://newsweb.oslobors.no/message/' + mid,
                 source='Euronext Oslo NewsWeb', title=meta.get('title', ''),
                 evidence_status='OFFICIAL_NOTIFICATION_UNCLASSIFIED', detail_checked=bool(detail),
                 corrected_message_id=meta.get('correctionForMessageId') or 0, message_id=mid)
        # Deliberately narrow grammar, including close-associate evidence in the same sentence.
        paragraphs = [_text(p) for p in re.split(r'\n+|</p>|<br\s*/?>', str(detail.get('body') or ''))]
        matches = [re.search(r'^([A-Z][^!?]{2,180}?) has purchased ([\d,]+) shares at an average price of (USD|NOK|EUR|SEK|DKK) ([\d.]+) per share', p) for p in paragraphs]
        match = next((m for m in matches if m), None)
        excluded = re.search(r'option|share[- ]based|borrowed shares|redelivery|internal transfer|buyback|repurchase', body, re.I)
        if match and not excluded:
            actor_clause, quantity, currency, price = match.groups()
            qty, unit_price = _number(quantity.replace(',', '')), _number(price)
            if qty and unit_price:
                associate = re.search(r',\s*a close associate of (.+?),\s*$', actor_clause)
                actor = actor_clause[:associate.start()].strip() if associate else actor_clause.strip()
                e.update(kind='INSIDER_PURCHASE', actor=actor, related_person=associate.group(1) if associate else '',
                         quantity=qty, price=unit_price, currency=currency,
                         evidence_status='EXPLICIT_OFFICIAL_PURCHASE', evidence_excerpt=match.group(0)[:500])
        e['id'] = event_id(e)
        out.append(e)
    return out


def short_events(instruments, now):
    """Compare consecutive official snapshots; absent actor is below threshold/unknown.

    Public aggregated short is neither total short interest nor short-sale volume.
    First known snapshot is a baseline, not proof of a newly opened short.
    """
    out = []
    for instrument in instruments:
        history = sorted((e for e in instrument.get('events', []) if timestamp(e.get('date')) and
                          timestamp(e['date']) <= now), key=lambda e: timestamp(e['date']))
        for previous, current in zip(history, history[1:]):
            date = timestamp(current['date'])
            if date < now - timedelta(days=90):
                continue
            old = {str(p.get('positionHolder')): p for p in previous.get('activePositions', []) if p.get('positionHolder')}
            new = {str(p.get('positionHolder')): p for p in current.get('activePositions', []) if p.get('positionHolder')}
            for actor in sorted(set(old) | set(new)):
                before = _number(old[actor].get('shortPercent')) if actor in old else None
                after = _number(new[actor].get('shortPercent')) if actor in new else None
                if (actor in old and before is None) or before == after or (actor in new and (after is None or after < .5)):
                    continue
                if actor not in new:
                    kind = 'SHORT_BELOW_PUBLIC_THRESHOLD_OR_UNKNOWN'
                elif actor not in old:
                    kind = 'SHORT_NEW_PUBLIC_POSITION'
                else:
                    kind = 'SHORT_INCREASE' if after > before else 'SHORT_REDUCTION'
                e = dict(kind=kind, issuer=instrument.get('issuerName', ''), isin=instrument.get('isin', ''),
                         actor=actor, previous_pct=before, current_pct=after,
                         public_aggregate_pct=_number(current.get('shortPercent')),
                         metric='PUBLIC_DISCLOSED_SHORT_POSITION', publication_threshold_pct=.5,
                         market='Norge', occurred_at=date.isoformat(), observed_at=now.isoformat(),
                         source='Finanstilsynet', source_url=SHORT_API,
                         evidence_status='OFFICIAL_PUBLIC_REGISTER')
                e['id'] = event_id(e)
                out.append(e)
    return out


def _request_json(url, *, post=False, timeout=15):
    request = urllib.request.Request(url, data=b'' if post else None,
                                     headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Official response exceeds bounded size')
        data = json.loads(raw)
    if post:
        if data.get('header', {}).get('result.val') != 0:
            raise ValueError('NewsWeb rejected request')
        return data['data']
    return data


def refresh_events(*, now=None, storage=None, request_json=None):
    now = now or datetime.now(timezone.utc)
    storage = storage or get_storage_service()
    deadline = time.monotonic() + 45
    def bounded_request(url, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Event discovery cycle budget exhausted")
        return _request_json(url, timeout=min(15, remaining), **kwargs)
    request = request_json or bounded_request
    cached = storage.read_json(KEY, {}) or {}
    checked = timestamp(cached.get('checked_at'))
    if checked and 0 <= (now - checked).total_seconds() < POLL_SECONDS:
        return cached
    incoming, sources, invalidated_messages = [], {}, set()
    detail_attempts = dict(cached.get("detail_attempts", {}))
    for source in ('short', 'insider'):
        try:
            if source == 'insider':
                query = urlencode(dict(category=1102, fromDate=(now-timedelta(days=7)).date().isoformat(), toDate=now.date().isoformat()))
                data = request(NEWS_API + 'list?' + query, post=True)
                messages = data['messages']
                if not isinstance(messages, list):
                    raise ValueError('Invalid official message list')
                invalidated_messages.update(str(m.get('id')) for m in messages if m.get('correctedByMessageId'))
                prior = {e.get('message_id'): e for e in cached.get('events', []) if e.get('message_id')}
                details, failures = {}, 0
                pending = [m for m in messages[:200] if any(c.get('id') == 1102 for c in m.get('category', [])) and not m.get('correctedByMessageId') and
                           not prior.get(str(m.get('id')), {}).get('detail_checked')]
                pending.sort(key=lambda m: detail_attempts.get(str(m.get("id")), ""))
                for m in pending[:MAX_DETAILS]:
                    mid = str(m.get('id'))
                    if not mid.isdigit():
                        continue
                    detail_attempts[mid] = now.isoformat()
                    try:
                        detail = request(NEWS_API + 'message?' + urlencode({'messageId': mid}), post=True)['message']
                        if str(detail.get('messageId')) != mid:
                            raise ValueError('Official message identity mismatch')
                        details[mid] = detail
                    except Exception:
                        failures += 1
                incoming += insider_events(messages, details, now)
                partial = bool(data.get('overflow') or len(messages) > 200 or len(pending) > MAX_DETAILS or failures)
                sources[source] = dict(status='PARTIAL' if partial else 'OK', checked_at=now.isoformat(),
                                       detail_failures=failures, remaining_details=max(0, len(pending)-len(details)),
                                       window_days=7, last_success_at=now.isoformat())
            else:
                data = request(SHORT_API)
                if not isinstance(data, list):
                    raise ValueError('Invalid official short register')
                incoming += short_events(data, now)
                sources[source] = dict(status='OK', checked_at=now.isoformat(), last_success_at=now.isoformat())
        except Exception as exc:
            sources[source] = dict(status='UNAVAILABLE', checked_at=now.isoformat(),
                                   last_success_at=cached.get('sources', {}).get(source, {}).get('last_success_at'),
                                   error=type(exc).__name__)
    def merge(current):
        # Do not replace classified details with an unclassified metadata refresh.
        events = {e['id']: e for e in (current or {}).get('events', []) if e.get('message_id') not in invalidated_messages}
        for e in incoming:
            if e.get('message_id'):
                same = [key for key, old in events.items() if old.get('message_id') == e['message_id']]
                if not e.get('detail_checked') and any(events[key].get('detail_checked') for key in same):
                    continue
                for key in same:
                    del events[key]
            events[e['id']] = e
        # Corrections supersede their original disclosure even if details cannot be classified.
        superseded = {str(e['corrected_message_id']) for e in events.values() if e.get('corrected_message_id')}
        rows = sorted((e for e in events.values() if timestamp(e.get('occurred_at')) and
                       now-timedelta(days=90) <= timestamp(e['occurred_at']) <= now and
                       e.get('message_id') not in superseded), key=lambda e: (e['occurred_at'], e['id']), reverse=True)[:MAX_EVENTS]
        return dict(checked_at=now.isoformat(), events=rows, sources=sources,
                    retention_limit_reached=len(rows) == MAX_EVENTS,
                    detail_attempts=dict(sorted(detail_attempts.items(), key=lambda item: item[1], reverse=True)[:200]),
                    coverage='NORWAY_OFFICIAL_ONLY', retention_days=90)
    return storage.mutate_json(KEY, merge, default={})


def _name(value):
    return re.sub(r'[^\w]', '', str(value or '').casefold())


def candidate_events(universe, state, now):
    """Route official identities only to a unique investable universe record."""
    by_isin, by_symbol, by_name = defaultdict(set), defaultdict(set), defaultdict(set)
    for row in universe:
        ticker = str(row.get('ticker') or row.get('symbol') or '').upper()
        if not ticker:
            continue
        if row.get('isin'):
            by_isin[str(row['isin']).upper()].add(ticker)
        # Oslo-only resolver: never alias a US dual listing by guessed ticker suffix.
        by_symbol[ticker.removesuffix('.OL')].add(ticker)
        for field in ('company', 'name', 'longName', 'shortName'):
            if row.get(field):
                by_name[_name(row[field])].add(ticker)
    mapped = defaultdict(list)
    for e in state.get('events', []):
        date = timestamp(e.get('occurred_at'))
        observed = timestamp(e.get('observed_at'))
        if not date or not observed or observed > now or not now-timedelta(days=7) <= date <= now:
            continue
        matches = by_isin.get(str(e.get('isin', '')).upper(), set()) if e.get('isin') else set()
        if not matches and e.get('issuer_symbol'):
            matches = by_symbol.get(str(e['issuer_symbol']).upper(), set())
        if not matches:
            matches = by_name.get(_name(e.get('issuer')), set())
        if len(matches) == 1:
            mapped[next(iter(matches))].append(e)
    return dict(mapped)


def prioritize_analysis(ranked, universe, mapped, limit, reserve=10):
    """Bounded slots for both bullish and bearish events; buy/risk gates unchanged."""
    lookup = {str(r.get('ticker') or r.get('symbol') or '').upper(): dict(r) for r in universe}
    # Round-robin event families prevents short activity starving insider discoveries.
    ordered = sorted(mapped, key=lambda t: max(e['occurred_at'] for e in mapped[t]), reverse=True)
    insider = [t for t in ordered if any(e['kind'].startswith('INSIDER') for e in mapped[t])]
    short = [t for t in ordered if any(e['kind'].startswith('SHORT') for e in mapped[t])]
    selected = []
    for pair in zip(insider + [None]*len(short), short + [None]*len(insider)):
        for ticker in pair:
            if ticker and ticker in lookup and ticker not in selected and len(selected) < min(reserve, limit):
                selected.append(ticker)
    rows = [{**lookup[t], 'official_market_events': mapped[t]} for t in selected]
    for row in ranked:
        ticker = str(row.get('ticker') or row.get('symbol') or '').upper()
        if ticker not in selected and len(rows) < limit:
            rows.append(dict(row))
            selected.append(ticker)
    return rows


def purchase_clusters(events, now):
    groups = defaultdict(list)
    for e in {e['id']: e for e in events}.values():
        date = timestamp(e.get('occurred_at'))
        if e.get('kind') == 'INSIDER_PURCHASE' and date and now-timedelta(days=90) <= date <= now:
            groups[(e['issuer'], e.get('actor'), e['currency'])].append(e)
    return [dict(issuer=issuer, actor=actor, currency=currency,
                 purchases_30d=sum(timestamp(e['occurred_at']) >= now-timedelta(days=30) for e in rows),
                 purchases_90d=len(rows), shares_90d=sum(e['quantity'] for e in rows),
                 value_90d=sum(e['quantity']*e['price'] for e in rows),
                 source_urls=sorted({e['source_url'] for e in rows}))
            for (issuer, actor, currency), rows in groups.items()]


def event_revision(mapped):
    """Semantic digest: same-day register revisions matter, poll timestamps do not."""
    fields = ('id', 'kind', 'current_pct', 'previous_pct', 'public_aggregate_pct',
              'quantity', 'price', 'currency', 'actor', 'related_person')
    rows = sorted([{k: e.get(k) for k in fields} for events in mapped.values() for e in events], key=lambda e: e['id'])
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
