"""Bounded daily historical OHLC collection and coarse stop/hold comparisons.

Uses only an explicit symbol universe; no fake progress or look-ahead entry prices.
This is a background experiment, not an order or production-rule authority.
"""
from __future__ import annotations
from datetime import datetime, timezone
import os
import time
import hashlib
from services.storage_service import get_storage_service
from super_portfolio_market_data import load_price_series_bounded

PREFIX = "strategy_history/"
STOPS = (3.0, 5.0, 7.0, 10.0)
HOLDS = (5, 10, 20, 60)

def simulate(rows, stop_pct, hold_days):
    """Next-day-open entry; earliest subsequent daily LOW stop, otherwise close at horizon.
    Conservative gap fills at opening price when below stop; no fees assumed.
    """
    result = []
    if len(rows) < hold_days + 2:
        return result
    for signal in range(len(rows) - hold_days - 1):
        entry_bar = rows[signal + 1]
        entry = float(entry_bar.get("open") or 0)
        if entry <= 0: continue
        stop = entry * (1 - stop_pct / 100.0)
        exit_price = None
        for age in range(1, hold_days + 1):
            bar = rows[signal + 1 + age]
            low = float(bar.get("low") or bar.get("close") or 0)
            opened = float(bar.get("open") or bar.get("close") or 0)
            if low > 0 and low <= stop:
                exit_price = min(stop, opened) if opened > 0 else stop
                break
        if exit_price is None:
            exit_price = float(rows[signal + 1 + hold_days].get("close") or 0)
        if exit_price > 0:
            result.append((exit_price / entry - 1.0) * 100)
    return result

def run_once():
    storage = get_storage_service()
    universe = storage.read_json(PREFIX + "universe.json", {}) or {}
    symbols = sorted({str(x).strip().upper() for x in (universe.get("symbols") or []) if str(x).strip()})
    state = storage.read_json(PREFIX + "progress.json", {}) or {}
    if not symbols:
        # Bootstrap from existing production candidate universes; never invent symbols.
        latest = storage.read_json("market_intelligence/latest_run.json", {}) or {}
        candidates = latest.get("candidates") or []
        symbols = sorted({str(row.get("ticker") or "").strip().upper() for row in candidates
                          if isinstance(row, dict) and str(row.get("ticker") or "").strip()})
        if symbols:
            storage.write_json(PREFIX + "universe.json", {"symbols":symbols,"source":"market_intelligence/latest_run.json"})
    if not symbols:
        state.update({"status": "WAITING_FOR_UNIVERSE", "total": 0, "completed": 0, "updated_at": datetime.now(timezone.utc).isoformat(), "reason": "No verified symbol list supplied"})
        storage.write_json(PREFIX + "progress.json", state)
        return state
    completed = set(state.get("completed_tickers") or []) & set(symbols)
    rejected = set(state.get("rejected_tickers") or []) & set(symbols)
    batch = [x for x in symbols if x not in completed and x not in rejected][:max(1, min(200, int(os.getenv("STRATEGY_HISTORY_PER_RUN", "80"))))]
    if not batch:
        state.update({"status":"COMPLETED", "total":len(symbols),"completed":len(completed), "rejected":len(rejected)})
        storage.write_json(PREFIX + "progress.json", state)
        return state
    started = time.monotonic()
    def on_progress(event):
        state.update({"status": "RUNNING", "batch_completed":event.get("completed"), "batch_total":event.get("total"),"updated_at":datetime.now(timezone.utc).isoformat()})
        storage.write_json(PREFIX + "progress.json", state)
    try:
        series, health = load_price_series_bounded(batch, os.getenv("STRATEGY_HISTORY_START","2020-01-01"),progress_callback=on_progress,control_callback=None,batch_size=20,max_workers=2)
        for ticker in batch:
            bars=series.get(ticker) or []
            if len(bars) < 65:
                rejected.add(ticker)
                continue
            key = hashlib.sha256(ticker.encode()).hexdigest()
            storage.write_json(PREFIX+"prices/"+key+".json", {"ticker":ticker,"bars":bars,"source":"yfinance-auto-adjusted-daily"})
            summary={}
            for stop in STOPS:
                for hold in HOLDS:
                    outcomes=simulate(bars,stop,hold)
                    if outcomes:
                        summary[f"{stop:g}:{hold}"]={"n":len(outcomes),"avg_return_pct":round(sum(outcomes)/len(outcomes),4),"win_rate_pct":round(100*sum(x>0 for x in outcomes)/len(outcomes),2)}
            storage.write_json(PREFIX+"results/"+ticker.replace("/","_")+".json", {"ticker":ticker,"bars":len(bars),"start":bars[0].get("date"),"end":bars[-1].get("date"),"trials":summary,"model":"unconditional-next-open-coarse-baseline","not_validated":True})
            completed.add(ticker)
        rejected.update(set(batch)-set(series))
        state.update({"status":"RUNNING" if len(completed)+len(rejected)<len(symbols) else "COMPLETED","total":len(symbols),"completed":len(completed),"rejected":len(rejected),"completed_tickers":sorted(completed),"rejected_tickers":sorted(rejected),"elapsed_seconds":round(time.monotonic()-started,1),"updated_at":datetime.now(timezone.utc).isoformat(),"health":health,"note":"Exploratory gross returns only; no selection, fees or holdout validation"})
    except Exception as exc:
        state.update({"status":"FAILED","reason":f"{type(exc).__name__}: {exc}"[:250],"updated_at":datetime.now(timezone.utc).isoformat()})
    storage.write_json(PREFIX + "progress.json", state)
    return state
