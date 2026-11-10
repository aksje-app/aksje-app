"""Versioned signal research: matched next-open entries, normalized adjusted prices.

This is a gross total-return proxy in listing currency, not a fill, NOK account,
net result or tax/dividend-cash ledger. Missing comparable benchmarks stay null.
"""
from copy import deepcopy
from datetime import timedelta
import math

POLICY = 'NEXT_COMMON_OPEN_ADJUSTED_PROXY_V2'
RETURN_BASIS = 'PROVIDER_ADJUSTED_TOTAL_RETURN_PROXY_V1'
BENCHMARKS = {'NORGE':'OSEBX.OL','USA':'^SP500TR','SVERIGE':None}


def positive(value):
    if isinstance(value,bool):
        raise ValueError('Boolean is not a price')
    n = float(value)
    if not math.isfinite(n) or n<=0:
        raise ValueError('Invalid reference price')
    return n


def sessions(market, start, end):
    from services.learning_position_outcomes import _calendar
    schedule = _calendar(market).schedule(start,end)
    return [(day.date().isoformat(),row['market_open'].to_pydatetime(),row['market_close'].to_pydatetime())
            for day,row in schedule.iterrows()]


def measure(row, stock, benchmark, *, now, previous=None, cost_contract=None):
    from services.learning_position_outcomes import stamp
    original = deepcopy(previous or {})
    signal_at = stamp(row['entry_at'])
    if now.tzinfo is None or signal_at>now:
        raise ValueError('Invalid measurement clock')
    calendar = sessions(row['market'],signal_at.date().isoformat(),
                        (max(now,signal_at)+timedelta(days=14)).date().isoformat())
    eligible = [s for s in calendar if s[1]>signal_at]
    if not eligible:
        return {**original,'state':'AWAITING_NEXT_OPEN'}
    entry_day,entry_open,_ = eligible[0]
    completed = [s for s in eligible if s[2]+timedelta(minutes=15)<=now][:60]
    if not completed:
        return {**original,'state':'AWAITING_COMPLETED_ENTRY_SESSION'}
    stock_by_date = {p['date']:p for p in stock}
    bench_by_date = {p['date']:p for p in benchmark}
    expected = [s[0] for s in completed]
    if entry_day not in stock_by_date:
        return {**original,'state':'MISSING_EXPECTED_ENTRY_BAR'}
    if any(day not in stock_by_date for day in expected):
        return {**original,'state':'MISSING_EXPECTED_STOCK_SESSION'}
    try:
        entry = stock_by_date[entry_day]
        if any(stock_by_date[d].get('return_basis')!=RETURN_BASIS for d in expected):
            raise ValueError('Undocumented adjusted price basis')
        if any(stock_by_date[d].get('source_ticker',row['ticker'])!=row['ticker'] for d in expected):
            raise ValueError('Adjusted series instrument identity mismatch')
        stock_open = positive(entry['open'])
        curve = [100*positive(stock_by_date[d]['close'])/stock_open for d in expected]
        comparable = bool(BENCHMARKS[row['market']] and entry_day in bench_by_date
                          and bench_by_date[entry_day].get('return_basis')==RETURN_BASIS)
        bench_open = positive(bench_by_date[entry_day]['open']) if comparable else None
        bench_curve = [100*positive(bench_by_date[d]['close'])/bench_open
                       if comparable and d in bench_by_date and bench_by_date[d].get('return_basis')==RETURN_BASIS
                       else None for d in expected]
        measurements = {}
        for horizon in (1,5,20,60):
            if len(curve)<horizon:
                continue
            value = curve[horizon-1]
            bench_value = bench_curve[horizon-1]
            ret = value-100
            paired = bench_value is not None
            bench_ret = bench_value-100 if paired else None
            measurements[str(horizon)] = {
                'horizon_days':horizon,'market_date':expected[horizon-1],
                'price':round(value,8),'benchmark_price':round(bench_value,8) if paired else None,
                'return_pct':round(ret,4),'benchmark_return_pct':round(bench_ret,4) if paired else None,
                'excess_return_pct':round(ret-bench_ret,4) if paired else None,
                'maximum_gain_pct':round(max(curve[:horizon])-100,4),
                'maximum_drawdown_pct':round(min(curve[:horizon])-100,4),
                'measurement_policy':POLICY,'return_basis':RETURN_BASIS,'price_unit':'NORMALIZED_INDEX_100',
                'source_basis':{'stock_adjusted_entry_open':stock_open,
                    'stock_adjusted_exit_close':positive(stock_by_date[expected[horizon-1]]['close']),
                    'benchmark_adjusted_entry_open':bench_open,
                    'benchmark_adjusted_exit_close':positive(bench_by_date[expected[horizon-1]]['close']) if paired else None,
                    'exit_session_close_at':completed[horizon-1][2].isoformat()},
                'net_return_pct':None,'net_status':'NOT_MODELLED_NO_EXECUTION_FX_COST_LEDGER',
            }
        from services.learning_cost_reference import cost_reference, reference_changed
        for key,reading in measurements.items():
            endpoint=stock_by_date[reading['market_date']]
            reading['cost_reference']=cost_reference(
                gross_factor=positive(endpoint['close'])/stock_open,
                currency=(row.get('signal_reference') or {}).get('reference_currency'),
                entry_at=entry_open.isoformat(),exit_at=reading['source_basis']['exit_session_close_at'],
                contract=cost_contract,fx_entry=entry.get('fx_open_quote'),fx_exit=endpoint.get('fx_close_quote'))
        for key,old in (original.get('horizon_measurements') or {}).items():
            fresh = measurements.get(key)
            if fresh is None or any(old.get(f)!=fresh.get(f) for f in
                                    ('market_date','return_pct','maximum_gain_pct','maximum_drawdown_pct')):
                return {**original,'state':'NORMALIZED_HISTORY_REVISION'}
            if old.get('benchmark_return_pct') is not None and fresh.get('benchmark_return_pct') is not None and old.get('benchmark_return_pct')!=fresh.get('benchmark_return_pct'):
                return {**original,'state':'NORMALIZED_HISTORY_REVISION'}
            if reference_changed(old.get('cost_reference'),fresh.get('cost_reference')):
                return {**original,'state':'NORMALIZED_HISTORY_REVISION'}
            measurements[key] = old  # Preserve the exact frozen result and provenance.
        reference = original.get('entry_reference') or {
            'market_date':entry_day,'market_open_at':entry_open.isoformat(),
            'signal_at':signal_at.isoformat(),'raw_open_reference':positive(entry['raw_open']),
            'is_executed_fill':False,'price_unit':'NORMALIZED_INDEX_100',
            'benchmark_ticker':BENCHMARKS[row['market']],
        }
        marks = [{'market_date':d,'price':round(curve[i],8),
                  'return_pct':round(curve[i]-100,4),
                  'benchmark_price':round(bench_curve[i],8) if bench_curve[i] is not None else None,
                  'benchmark_return_pct':round(bench_curve[i]-100,4) if bench_curve[i] is not None else None,
                  'excess_return_pct':round(curve[i]-bench_curve[i],4) if bench_curve[i] is not None else None,
                  'measurement_policy':POLICY,'return_basis':RETURN_BASIS}
                 for i,d in enumerate(expected)]
        current_marks = {m['market_date']:m for m in marks}
        for old in original.get('daily_marks') or []:
            fresh = current_marks.get(old['market_date'])
            if fresh is None or old.get('return_pct')!=fresh.get('return_pct'):
                return {**original,'state':'NORMALIZED_HISTORY_REVISION'}
            for field in ('benchmark_return_pct','excess_return_pct'):
                if old.get(field) is not None and fresh.get(field) is not None and old[field]!=fresh[field]:
                    return {**original,'state':'NORMALIZED_HISTORY_REVISION'}
            marks[expected.index(old['market_date'])]=old
        complete_comparison = comparable and all(m.get('benchmark_return_pct') is not None for m in marks)
        return {'state':'MEASURED' if complete_comparison else 'MEASURED_WITHOUT_COMPARABLE_BENCHMARK',
                'measurement_policy':POLICY,'entry_price':100.,
                'benchmark_entry_price':100. if comparable or any(m.get('benchmark_return_pct') is not None for m in measurements.values()) else None,
                'entry_reference':reference,'horizon_measurements':measurements,
                'return_basis':RETURN_BASIS,'net_return_pct':None,'daily_marks':marks,
                'trade_authorized':False}
    except (ValueError,TypeError,KeyError,ZeroDivisionError):
        return {**original,'state':'UNVERIFIED_PRICE_BASIS'}
