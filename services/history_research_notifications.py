"""Bounded, descriptive historical-research summaries; no strategy authority."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from zoneinfo import ZoneInfo

PREFIX = 'strategy_history/notifications/'
SUMMARY = PREFIX + 'latest.json'
PROGRESS = 'strategy_history/optimization_progress.json'
ENGINES = ('AUTONOMY', 'SUPER_PORTFOLIO')
LABELS = dict(zip(ENGINES, ('Autonomi', 'Superporteføljen')))
MAX_INDEX_BYTES = 8 * 1024**2


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def observation(result, ticker, engine, method):
    """Use the first finalist, ranked before holdout, never the best holdout."""
    from portfolio_history_optimizer import COST_PCT, GAP, STOPS, HOLDS
    if result.get('ticker') != ticker:
        return {'status': 'UNMEASURABLE', 'reason': 'SOURCE_IDENTITY_OR_METHOD'}
    if str(result.get('status') or '').startswith('INSUFFICIENT_'):
        return {'status': 'INSUFFICIENT_HISTORY'}
    if result.get('method_version') != method:
        return {'status': 'UNMEASURABLE', 'reason': 'SOURCE_IDENTITY_OR_METHOD'}
    if result.get('status') != 'COMPLETE_RESEARCH':
        return {'status': 'UNMEASURABLE', 'reason': 'NOT_COMPLETE_RESEARCH'}
    if (result.get('portfolio') != engine or
            result.get('scope') != 'UNCONDITIONAL_ENTRY_EXIT_GRID_NOT_PORTFOLIO_REPLAY' or
            result.get('cost_round_trip_pct') != COST_PCT or result.get('purge_sessions') != GAP):
        return {'status': 'UNMEASURABLE', 'reason': 'SOURCE_CONTRACT'}
    try:
        dates = [datetime.fromisoformat(result[k]) for k in ('train_end', 'validation_start', 'holdout_start')]
        if not dates[0] < dates[1] < dates[2]:
            raise ValueError('Chronological splits required')
        finalist = result['finalists'][0]
        score = finalist['holdout']
        if isinstance(score['total_pct'], bool) or type(score['trades']) is not int:
            raise ValueError('Invalid numeric result')
        value = float(score['total_pct'])
        trades = score['trades']
        if not isfinite(value) or trades < 1 or finalist['stop_pct'] not in STOPS or finalist['hold_sessions'] not in HOLDS:
            raise ValueError('Invalid held-out result')
        return {'status': 'MEASURED', 'return_pct': value, 'trades': trades,
                'stop_pct': finalist['stop_pct'], 'hold_sessions': finalist['hold_sessions'],
                'source_sha256': digest(result)}
    except (ValueError, TypeError, KeyError, IndexError):
        return {'status': 'UNMEASURABLE', 'reason': 'NO_VALID_HELD_OUT_RESULT'}


def summarize(progress, records, *, cohort, now):
    completed = sorted(set(progress.get('completed_tickers') or []))
    engines = {}
    for engine in ENGINES:
        rows = [(records.get(t) or {}).get(engine) or {} for t in completed]
        measured = [r for r in rows if r.get('status') == 'MEASURED']
        pairs = Counter((r['stop_pct'], r['hold_sessions']) for r in measured)
        common = sorted(pairs, key=lambda p: (-pairs[p], p))
        engines[engine] = {'measured': len(measured),
            'positive': sum(r['return_pct'] > 0 for r in measured),
            'negative': sum(r['return_pct'] < 0 for r in measured),
            'flat': sum(r['return_pct'] == 0 for r in measured),
            'positive_share_pct': 100 * sum(r['return_pct'] > 0 for r in measured) / len(measured) if measured else None,
            'insufficient': sum(r.get('status') == 'INSUFFICIENT_HISTORY' for r in rows),
            'unmeasurable': sum(r.get('status') == 'UNMEASURABLE' for r in rows),
            'most_selected': {'stop_pct': common[0][0], 'hold_sessions': common[0][1], 'symbols': pairs[common[0]]} if common else None}
    processed = len(completed)
    pending = sum(t not in records for t in completed)
    return {'schema': 1, 'cohort': cohort, 'method_version': progress.get('method_version'),
            'total': int(progress.get('total') or 0), 'processed': processed,
            'failed': int(progress.get('failed') or 0), 'source_status': progress.get('status'),
            'source_updated_at': progress.get('updated_at'), 'updated_at': now.isoformat(),
            'coverage_processed': processed - pending, 'coverage_pending': pending,
            'engines': engines, 'status': 'BUILDING' if pending else 'READY',
            'selection': 'FIRST_FINALIST_RANKED_BEFORE_HOLDOUT', 'production_changed': False,
            'scope': 'HISTORICAL_EXIT_RESEARCH_ONLY', 'strategy_validated': False,
            'interpretation': 'Ulike aksjer/testperioder, ikke porteføljeavkastning eller prognose. Modellkost 0,30 % per avsluttet handel.'}


def collect(*, service, now, limit=24):
    from portfolio_history_optimizer import METHOD_VERSION
    progress = service.read_json(PROGRESS, {}) or {}
    if progress.get('method_version') != METHOD_VERSION or not progress.get('started_at'):
        return {'status': 'WAITING_FOR_CURRENT_METHOD', 'production_changed': False}
    cohort = digest([METHOD_VERSION, progress['started_at']])
    key = PREFIX + 'indexes/' + cohort + '.json'
    index = service.read_json(key, {}) or {}
    records = index.get('records') or {}
    pending = sorted(set(progress.get('completed_tickers') or []) - set(records))
    updates = {}
    for ticker in pending[:max(1, min(32, int(limit)))]:
        hashed = sha256(ticker.encode()).hexdigest()
        updates[ticker] = {engine: observation(service.read_json(
            'strategy_history/optimized/' + engine + '/' + hashed + '.json', {}) or {},
            ticker, engine, METHOD_VERSION) for engine in ENGINES}
    if updates:
        def merge(current):
            value = {**(current or {}), 'cohort': cohort,
                     'records': {**((current or {}).get('records') or {}), **updates}}
            if len(json.dumps(value, allow_nan=False).encode()) > MAX_INDEX_BYTES:
                raise ValueError('Research notification index reached 8 MiB; no history removed')
            return value
        index = service.mutate_json(key, merge)
    summary = summarize(progress, index.get('records') or {}, cohort=cohort, now=now)
    summary['collected_in_batch'] = len(updates)
    service.write_json(SUMMARY, summary)
    return summary


def message(summary, previous=None):
    total, done = summary['total'], summary['processed']
    number = lambda n: f'{n:,}'.replace(',', ' ')
    lines = [f"Vi har undersøkt {number(done)} av {number(total)} aksjer." if total else 'Testingen venter på en liste over aksjer som skal undersøkes.']
    same = previous and previous.get('cohort') == summary['cohort']
    if same:
        added = done - previous['processed']
        lines.append(f"{number(added)} flere aksjer er undersøkt siden forrige melding." if added > 0 else
                     'Ingen nye aksjer er ferdig undersøkt siden forrige melding.' if added == 0 else
                     'Antallet undersøkte aksjer er korrigert siden forrige melding.')
    lines.extend(['', 'De historiske testene viser:'])
    for engine in ENGINES:
        row = summary['engines'][engine]
        share = row['positive_share_pct']
        text = ('Foreløpig for lite data til å vise et resultat.' if share is None else
                f"{row['positive']} av {row['measured']} undersøkte aksjer ga gevinst i testen." if row['measured'] < 100 else
                f"Omtrent {share:.0f} av 100 aksjer ga gevinst i testen.")
        lines.append(f"{LABELS[engine]}: {text}")
    lines.extend(['', 'Tallene viser hvor ofte testene ga gevinst. Om dette gir bedre handel i praksis, er ennå ikke dokumentert.',
                  'Handelsreglene dine er uendret.'])
    return '\n'.join(lines)


def send_daily(*, service, summary, now):
    """Serialize deliveries with the same cross-process lane as the scheduler."""
    from resource_coordinator import execution_lane
    from notifier import send_pushover_alert, normalize_notification_result
    local = now.astimezone(ZoneInfo('Europe/Oslo'))
    if local.hour < 8:
        return {'status': 'NOT_DUE_YET'}
    if summary.get('status') != 'READY':
        return {'status': 'WAITING_FOR_SUMMARY'}
    with execution_lane('history_research_notification') as acquired:
        if not acquired:
            return {'status': 'DEFERRED_BUSY'}
        key = PREFIX + 'deliveries/' + local.date().isoformat() + '.json'
        prior = service.read_json(key, {}) or {}
        if prior.get('sent') is True:
            return {'status': 'ALREADY_SENT', 'sent': False}
        attempts = list(prior.get('attempts') or [])
        if attempts:
            age = (now - datetime.fromisoformat(attempts[-1]['at'])).total_seconds()
            if age < 3600 or len(attempts) >= 5:
                return {'status': 'RETRY_DEFERRED', 'sent': False}
        previous = service.read_json(PREFIX + 'last_delivered.json', {}) or {}
        text = message(summary, previous.get('summary'))
        source_time = summary.get('source_updated_at')
        try:
            age = (now - datetime.fromisoformat(source_time)).total_seconds()
            if age < 0 or (age > 8*3600 and summary.get('source_status') == 'RUNNING'):
                text = 'Testingen har ikke meldt ny fremdrift de siste 8 timene.\n\n' + text
        except (TypeError, ValueError):
            text = 'Vi kan ikke bekrefte hvor oppdaterte resultatene er.\n\n' + text
        try:
            ok, detail = normalize_notification_result(send_pushover_alert(
                text, title='Historisk læring – kort oppdatering', relevance_event={'category': 'learning_report'}))
        except Exception as exc:
            ok, detail = False, type(exc).__name__
        sent = bool(ok) and 'duplicate' not in str(detail).lower()
        attempts.append({'at': now.isoformat(), 'sent': sent, 'detail': str(detail)[:180]})
        receipt = {'sent': sent, 'status': 'SENT' if sent else 'DELIVERY_UNCONFIRMED',
                   'at': now.isoformat(), 'attempts': attempts, 'summary': summary, 'message': text}
        service.write_json(key, receipt)
        if sent:
            service.write_json(PREFIX + 'last_delivered.json', receipt)
        return {'status': receipt['status'], 'sent': sent, 'attempts': len(attempts)}


def run_once(*, service=None, now=None, limit=24, notify=True):
    from services.storage_service import get_storage_service
    service = service or get_storage_service()
    now = now or datetime.now(timezone.utc)
    summary = collect(service=service, now=now, limit=limit)
    delivery = send_daily(service=service, summary=summary, now=now) if notify else {'status': 'NOT_REQUESTED'}
    return {**summary, 'notification': delivery}
