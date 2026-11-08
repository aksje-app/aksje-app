"""Closed learning-position comparisons. Never writes portfolios or trade rules.

Actual simulated fills are compared with the last published official daily
index close available at each event. This is a daily reference, not an intraday
execution or a measured net-of-cost alpha. Retrospectively chosen comparators
are useful diagnostics but cannot satisfy the strategy's benchmark gate.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import math
from zoneinfo import ZoneInfo

PREFIX = 'controlled_learning/closed_benchmarks/'
INDEX = PREFIX + 'index.json'
SUMMARY = PREFIX + 'latest.json'
PORTFOLIO = 'autonomous_portfolio/learning_portfolio.json'
POLICY = 'LAST_PUBLISHED_OFFICIAL_DAILY_CLOSE_V1'
MAX_INDEX_BYTES = 8 * 1024**2
MARKETS = {'NORGE': ('XOSL', 'Europe/Oslo', 'OSEBX.OL'),
           'SVERIGE': ('XSTO', 'Europe/Stockholm', '^OMX'),
           'USA': ('XNYS', 'America/New_York', '^GSPC'),
           'BRASIL': ('BVMF', 'America/Sao_Paulo', '^BVSP')}
# Same all-share index provider spelling; never alias it to the OSEBX index.
ALIASES = {'^OSEAX': 'OSEAX.OL'}


def report_view(value):
    """Small receipts/reports must not duplicate the UI's per-trade dataset."""
    return {k:v for k,v in value.items() if k not in ('recent_positions','by_cohort','latest_attempts')} if isinstance(value,dict) else {}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Unverifiable timezone')
    return result.astimezone(timezone.utc)


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a price')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite outcome')
    return result


def position_id(row):
    # Includes original prices, times, cohort and source metadata. No lookup
    # can attach another version of a trade or silently relabel a cohort.
    return digest(row)


def market_for(row):
    market = str(row.get('market') or '').upper()
    ticker = str(row.get('ticker') or '').upper()
    if market in MARKETS:
        return market
    if ticker.endswith('.OL'):
        return 'NORGE'
    if ticker.endswith('.ST'):
        return 'SVERIGE'
    if ticker.endswith('.SA'):
        return 'BRASIL'
    if ticker and '.' not in ticker:
        return 'USA'
    raise ValueError('Unsupported or ambiguous market')


def benchmark_market(symbol):
    if symbol == 'OSEAX.OL':
        return 'NORGE'
    for market, (_, _, benchmark) in MARKETS.items():
        if symbol == benchmark:
            return market
    raise ValueError('Unsupported benchmark exchange')


@lru_cache(maxsize=512)
def session_closes(market, start, end):
    schedule = _calendar(market).schedule(start, end)
    return tuple((day.date().isoformat(), row['market_close'].to_pydatetime().astimezone(timezone.utc))
                 for day, row in schedule.iterrows())


@lru_cache(maxsize=4)
def _calendar(market):
    import pandas_market_calendars as calendars
    return calendars.get_calendar(MARKETS[market][0])


def reference_point(series, at, market):
    # A publication buffer avoids using an unfinished auction/index value.
    local_day = at.astimezone(ZoneInfo(MARKETS[market][1])).date()
    sessions = session_closes(market, (local_day-timedelta(days=14)).isoformat(), local_day.isoformat())
    eligible = [(day, close) for day, close in sessions if close+timedelta(minutes=15) <= at]
    if not eligible:
        raise ValueError('No completed reference session')
    day, close = eligible[-1]
    matches = [p for p in series if p.get('date') == day]
    if len(matches) != 1:
        raise ValueError('Missing or conflicting expected benchmark session: '+day)
    price = number(matches[0]['close'])
    if price <= 0:
        raise ValueError('Invalid benchmark close')
    return {'date': day, 'observed_at': close.isoformat(), 'available_at': (close+timedelta(minutes=15)).isoformat(),
            'price': price}


def measure(row, series_by_symbol, *, now):
    opened, closed = stamp(row['opened_at']), stamp(row['closed_at'])
    entry, exit_price = number(row['average_price']), number(row['close_price'])
    if not opened <= closed <= now or min(entry, exit_price) <= 0:
        raise ValueError('Invalid or future position boundaries')
    market = market_for(row)
    requested = str(row.get('benchmark_ticker') or '')
    original = ALIASES.get(requested, requested)
    fallback = MARKETS[market][2]
    candidates = list(dict.fromkeys([s for s in (original, fallback) if s]))
    errors = []
    for symbol in candidates:
        try:
            reference_market = benchmark_market(symbol)
            entry_reference = reference_point(series_by_symbol.get(symbol, []), opened, reference_market)
            exit_reference = reference_point(series_by_symbol.get(symbol, []), closed, reference_market)
            break
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(symbol+': '+str(exc))
    else:
        raise ValueError('; '.join(errors) or 'No benchmark series')
    retrospective = not requested or symbol != original
    stock_return = 100 * (exit_price/entry-1)
    benchmark_return = 100 * (exit_reference['price']/entry_reference['price']-1)
    record = {'schema': 1, 'position_id': position_id(row), 'source_sha256': digest(row),
        'ticker': row['ticker'], 'cohort': row.get('learning_cohort') or 'LEGACY_UNVERSIONED',
        'market': market, 'opened_at': row['opened_at'], 'closed_at': row['closed_at'],
        'requested_benchmark': requested or None, 'benchmark_symbol': symbol,
        'original_benchmark_errors': errors, 'retrospective_comparator': retrospective,
        'policy': POLICY, 'entry_reference': entry_reference, 'exit_reference': exit_reference,
        'gross_return_pct': stock_return, 'benchmark_return_pct': benchmark_return,
        'excess_return_pct': stock_return-benchmark_return,
        'net_after_costs_measured': False, 'daily_reference_not_intraday_execution': True,
        'validation_eligible': bool(not retrospective and row.get('evidence_valid_at_entry') is True
                                    and row.get('learning_cohort') not in (None, '', 'LEGACY_OBSERVATION', 'LEGACY_UNVERSIONED')),
        'measured_at': now.isoformat(), 'production_applied': False}
    record['sha256'] = digest(record)
    return record


def verified_measurement(row, record):
    try:
        if not isinstance(record, dict) or record['position_id'] != position_id(row) or record['source_sha256'] != digest(row):
            return None
        if digest({k:v for k,v in record.items() if k != 'sha256'}) != record['sha256']:
            return None
        if record['policy'] != POLICY or record.get('production_applied') is not False:
            return None
        if min(number(row['close_price']), number(row['average_price']),
               number(record['exit_reference']['price']), number(record['entry_reference']['price'])) <= 0:
            return None
        if record.get('net_after_costs_measured') is not False or record.get('daily_reference_not_intraday_execution') is not True:
            return None
        if record.get('cohort') != (row.get('learning_cohort') or 'LEGACY_UNVERSIONED') or record.get('ticker') != row.get('ticker'):
            return None
        if not stamp(row['opened_at']) <= stamp(row['closed_at']) <= stamp(record['measured_at']):
            return None
        gross = 100*(number(row['close_price'])/number(row['average_price'])-1)
        benchmark = 100*(number(record['exit_reference']['price'])/number(record['entry_reference']['price'])-1)
        if not math.isclose(number(record['gross_return_pct']), gross, abs_tol=1e-9) or not math.isclose(number(record['benchmark_return_pct']), benchmark, abs_tol=1e-9) or not math.isclose(number(record['excess_return_pct']), gross-benchmark, abs_tol=1e-9):
            return None
        for field, boundary in (('entry_reference','opened_at'), ('exit_reference','closed_at')):
            expected = reference_point([{'date':record[field]['date'],'close':record[field]['price']}], stamp(row[boundary]), benchmark_market(record['benchmark_symbol']))
            if expected != record[field]:
                return None
        requested = str(row.get('benchmark_ticker') or '')
        eligible = bool(requested and record['benchmark_symbol'] == ALIASES.get(requested, requested)
                        and row.get('evidence_valid_at_entry') is True
                        and row.get('learning_cohort') not in (None,'','LEGACY_OBSERVATION','LEGACY_UNVERSIONED'))
        if record.get('validation_eligible') is not eligible or record.get('retrospective_comparator') is not (not requested or record['benchmark_symbol'] != ALIASES.get(requested, requested)):
            return None
        return record
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


def summarize(rows, index):
    from app_version import APP_VERSION
    stored_count = len(rows)
    rows = list({position_id(r):r for r in rows}.values())
    measured = [m for r in rows if (m := verified_measurement(r, (index.get('records') or {}).get(position_id(r))))]
    groups = defaultdict(list)
    for record in measured:
        groups[(record['cohort'], record['market'])].append(record)
    def stats(items):
        return {'measured':len(items), 'mean_gross_return_pct':sum(r['gross_return_pct'] for r in items)/len(items) if items else None,
                'mean_benchmark_return_pct':sum(r['benchmark_return_pct'] for r in items)/len(items) if items else None,
                'mean_excess_return_pct':sum(r['excess_return_pct'] for r in items)/len(items) if items else None,
                'beat_benchmark':sum(r['excess_return_pct']>0 for r in items),
                'retrospective_comparators':sum(r['retrospective_comparator'] for r in items),
                'eligible_original_benchmarks':sum(r['validation_eligible'] for r in items)}
    return {'schema':1,'closed_positions':len(rows), 'stored_closed_rows':stored_count,
        'duplicate_rows_not_counted_twice':stored_count-len(rows), **stats(measured), 'unmeasured':len(rows)-len(measured),
        'by_cohort':[{'cohort':cohort,'market':market,**stats(items)} for (cohort,market),items in sorted(groups.items())],
        'current_cohort':{'cohort':APP_VERSION,**stats([r for r in measured if r['cohort']==APP_VERSION])},
        'recent_positions':[{k:r[k] for k in ('ticker','cohort','market','opened_at','closed_at',
            'requested_benchmark','benchmark_symbol','gross_return_pct','benchmark_return_pct','excess_return_pct',
            'retrospective_comparator','validation_eligible','entry_reference','exit_reference','sha256')}
            for r in sorted(measured,key=lambda r:r['closed_at'],reverse=True)[:200]],
        'net_after_costs_measured':False, 'production_applied':False, 'strategy_validated':False,
        'production_recommendation':'NO_RULE_CHANGE_WITHOUT_VALIDATED_EVIDENCE',
        'aggregation':'EQUAL_WEIGHTED_CLOSED_POSITIONS_NOT_PORTFOLIO_NAV',
        'interpretation':'Lukkede handler alene er ikke hele porteføljen eller bevis på bedre strategi. Daglige indeksreferanser; før kostnader. Ettervalgte referanser kan ikke validere strategien.'}


def cached_series(symbols, service, now):
    from learning_observation_engine import yfinance_series_loader
    output, missing = {}, []
    for symbol in symbols:
        key=PREFIX+'series/'+now.date().isoformat()+'/'+digest(symbol)+'.json'
        value=service.read_json(key, None)
        if isinstance(value,dict) and value.get('symbol')==symbol:
            output[symbol]=value.get('rows') or []
        else:
            missing.append(symbol)
    if missing:
        loaded=yfinance_series_loader(missing,(now-timedelta(days=366)).date().isoformat())
        for symbol in missing:
            rows=loaded.get(symbol) or []
            # Do not freeze a transient empty response for the entire day.
            if rows:
                key=PREFIX+'series/'+now.date().isoformat()+'/'+digest(symbol)+'.json'
                saved=service.write_json_immutable(key,{'symbol':symbol,'observed_at':now.isoformat(),'rows':rows,'source':'YFINANCE_ADJUSTED_DAILY_CLOSE'})
                rows=saved['rows']
            output[symbol]=rows
    return output


def run_maintenance(*, service=None, now=None, series_loader=None, limit=24):
    from services.storage_service import get_storage_service
    from app_version import APP_VERSION
    service=service or get_storage_service()
    now=now or datetime.now(timezone.utc)
    book=service.read_json(PORTFOLIO,{}) or {}
    rows=[r for r in book.get('closed_positions',[]) if isinstance(r,dict)]
    index=service.read_json(INDEX,{}) or {}
    attempts=index.get('attempts') or {}
    def retry_due(row):
        previous=attempts.get(position_id(row),{})
        if not previous:
            return True
        delay=3600 if previous.get('status')=='MISSING_DATA' else 7*86400
        try:return (now-stamp(previous['at'])).total_seconds()>=delay
        except (ValueError,KeyError,TypeError):return True
    pending=[]
    for row in rows:
        current=verified_measurement(row,(index.get('records') or {}).get(position_id(row)))
        # Frozen original measurements do not need repeated downloads. Only
        # missing data (hourly) or a possible upgrade from proxy (weekly) retries.
        if (not current or current['retrospective_comparator']) and retry_due(row):
            pending.append(row)
    pending=list({position_id(r):r for r in pending}.values())
    pending.sort(key=lambda r:(r.get('learning_cohort')!=APP_VERSION,str(r.get('closed_at') or '')))
    batch=pending[:max(1,min(32,int(limit)))]
    symbols=set()
    for row in batch:
        try:
            symbols.add(MARKETS[market_for(row)][2])
            requested=str(row.get('benchmark_ticker') or '')
            if requested in set(MARKETS[m][2] for m in MARKETS) | set(ALIASES) | set(ALIASES.values()):
                symbols.add(ALIASES.get(requested,requested))
        except ValueError:
            pass
    series=(series_loader(sorted(symbols),now) if series_loader else cached_series(sorted(symbols),service,now)) if batch else {}
    updates, outcomes={},{}
    for row in batch:
        identity=position_id(row)
        try:
            candidate=measure(row,series,now=now)
            definition={'position_id':identity,'benchmark':candidate['benchmark_symbol'],'policy':POLICY}
            key=PREFIX+'measurements/'+digest(definition)+'.json'
            saved=service.write_json_immutable(key,candidate)
            if not verified_measurement(row,saved):
                raise ValueError('Stored immutable measurement does not match original trade')
            updates[identity]=saved
            outcomes[identity]={'at':now.isoformat(),'status':'MEASURED' if saved['validation_eligible'] else 'DESCRIPTIVE_COMPARISON','key':key}
        except (ValueError,KeyError,TypeError) as exc:
            outcomes[identity]={'at':now.isoformat(),'status':'MISSING_DATA','reason':str(exc)[:220]}
    def append(current):
        current=dict(current or {});records=dict(current.get('records') or {});history=dict(current.get('history') or {})
        for identity,record in updates.items():
            old=records.get(identity)
            accept=not old or record['validation_eligible'] or not old['validation_eligible']
            if old and old['sha256']!=record['sha256']:
                retained=old['sha256'] if accept else record['sha256']
                history[identity]=list(dict.fromkeys([*(history.get(identity) or []),retained]))
            if accept:
                records[identity]=record
        candidate={**current,'schema':1,'records':records,'history':history,
                   'attempts':{**(current.get('attempts') or {}),**outcomes},'updated_at':now.isoformat()}
        if len(json.dumps(candidate).encode())>MAX_INDEX_BYTES:
            raise ValueError('Closed benchmark evidence index reached its 8 MiB budget; no history deleted')
        return candidate
    index=service.mutate_json(INDEX,append) if outcomes else index
    summary=summarize(rows,index)
    summary={**summary,'updated_at':now.isoformat(),'processed_in_batch':len(batch),
             'pending_after_batch':max(0,len(pending)-len(batch)), 'latest_attempts':list(outcomes.values()),
             'status':'PARTIAL' if summary['unmeasured'] else 'COMPLETED'}
    # A new closure during collection must not be hidden by a fresh timestamp.
    summary['source_portfolio_sha256']=digest(rows)
    service.write_json(SUMMARY,summary)
    return summary
