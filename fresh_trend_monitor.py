"""Durable 15-minute Fresh Trend follow-up for RC16.31cb.

The monitor is observational.  It refreshes only the bounded Fresh Trend queue;
it cannot change investment scores, BUY/risk gates, portfolios or orders.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import os
from typing import Any, Mapping, Sequence

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

VERSION = "v19.22.0-rc16.31cb"
STATE_KEY = "fresh_trend/monitor_state.json"
STATE_PATH = runtime_data_path("fresh_trend", "monitor_state.json")
INTERVAL_MINUTES = 15
MAX_CANDIDATES = 12
FOLLOW_UP_SESSIONS = 5


def _f(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value else None
    except Exception:
        return None


def _now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _business_days(start: date, end: date) -> int:
    if end < start:
        return 0
    days = 0
    cursor = start
    from datetime import timedelta
    while cursor <= end:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def _due(state: Mapping[str, Any], now: datetime) -> bool:
    if os.getenv("FRESH_TREND_MONITOR_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return False
    try:
        last = datetime.fromisoformat(str(state.get("last_scan_at") or "").replace("Z", "+00:00"))
        return (now - last.astimezone(timezone.utc)).total_seconds() >= INTERVAL_MINUTES * 60
    except Exception:
        return True


def _components(receipt: Mapping[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, float]:
    fs = receipt.get("fresh_signal") if isinstance(receipt.get("fresh_signal"), Mapping) else {}
    score = float(_f(fs.get("score")) or 0.0)
    vr = float(_f(receipt.get("volume_ratio_20")) or 0.0)
    hold = int(receipt.get("breakout_hold_sessions") or 0)
    rs5 = float(_f(receipt.get("market_rs_5d_percentile")) or 50.0)
    rs_sector = float(_f(receipt.get("sector_rs_5d_percentile")) or 50.0)
    acceleration = float(_f(receipt.get("momentum_acceleration_3v20")) or 0.0)
    r3 = float(_f(receipt.get("return_3d_pct")) or 0.0)
    freshness = max(0.0, 100.0 - 12.0 * float(fs.get("trend_age_sessions") or 0))
    confirmation = min(100.0, 25.0 * hold + 25.0 * min(vr, 2.0) + 0.25 * (rs5 + rs_sector))
    velocity = min(100.0, max(0.0, 45.0 + 12.0 * acceleration + 4.0 * r3))
    risk = 0.0
    rsi = _f(receipt.get("rsi"))
    if rsi is not None:
        risk += max(0.0, rsi - 68.0) * 3.0
    if vr and vr < 0.8:
        risk += 25.0
    if receipt.get("breakout_20d") and not receipt.get("breakout_holding"):
        risk += 25.0
    prior_components = (previous or {}).get("components") if isinstance((previous or {}).get("components"), Mapping) else {}
    previous_score = _f(prior_components.get("Fresh Score"))
    if previous_score is None:
        previous_score = _f((previous or {}).get("score"))
    return {"Freshness": round(freshness, 1), "Confirmation": round(confirmation, 1),
            "Velocity": round(velocity, 1), "Risk": round(min(100.0, risk), 1),
            "Fresh Score": round(score, 1), "Score delta": round(score - previous_score, 1) if previous_score is not None else 0.0}


def _status(receipt: Mapping[str, Any], comp: Mapping[str, float], previous: Mapping[str, Any] | None) -> tuple[str, str]:
    score = comp["Fresh Score"]; delta = comp["Score delta"]
    last = _f(receipt.get("last_price")); prior_high = _f(receipt.get("prior_20d_high"))
    was_breakout = bool(receipt.get("breakout_20d") or (previous or {}).get("breakout_20d") or (previous or {}).get("breakout_holding"))
    false_breakout = bool(was_breakout and not receipt.get("breakout_holding") and last and prior_high and last < prior_high)
    if false_breakout or (score < 45 and str((previous or {}).get("status") or "") in {"AKSELERERER", "STERKT BEKREFTET"}):
        return "FALSKT BREAKOUT", "🔴"
    if delta <= -10 or comp["Velocity"] < 35:
        return "MISTER MOMENT", "🟠"
    if score >= 85 and comp["Confirmation"] >= 65:
        return "STERKT BEKREFTET", "🟢"
    if score >= 65 and (delta >= 4 or comp["Velocity"] >= 65):
        return "AKSELERERER", "⚡"
    return "NYTT", "🆕"


def _pullback_retest(receipt: Mapping[str, Any]) -> dict[str, Any]:
    price = _f(receipt.get("last_price")); breakout = _f(receipt.get("prior_20d_high")); sma20 = _f(receipt.get("sma20"))
    reference = breakout or sma20
    distance = ((price / reference - 1.0) * 100.0) if price and reference else None
    detected = bool(distance is not None and -1.5 <= distance <= 2.0 and (receipt.get("breakout_20d") or receipt.get("breakout_holding")))
    held = bool(detected and price and reference and price >= reference)
    return {"detected": detected, "held": held, "reference": round(reference, 4) if reference else None,
            "distance_pct": round(distance, 2) if distance is not None else None,
            "label": "RETEST HOLDER" if held else "PULLBACK/RETEST" if detected else "INGEN RETEST"}


def _message(row: Mapping[str, Any]) -> tuple[str, str]:
    path = " → ".join(str(int(round(float(x)))) for x in row.get("score_path", []))
    c = row.get("components") or {}; retest = row.get("pullback_retest") or {}
    title = f"{row.get('emoji','⚡')} Fresh Trend: {row.get('status')}"
    body = (f"{row.get('ticker')} · score {path}\n"
            f"Freshness {c.get('Freshness',0):.0f} · Confirmation {c.get('Confirmation',0):.0f} · "
            f"Velocity {c.get('Velocity',0):.0f} · Risk {c.get('Risk',0):.0f}\n"
            f"RS marked/sektor {row.get('market_rs_5d_percentile','-')}/{row.get('sector_rs_5d_percentile','-')} · {retest.get('label')}")
    return title, body


def monitor_receipts(receipts: Sequence[Mapping[str, Any]], *, now: datetime | None = None,
                     state: Mapping[str, Any] | None = None, notify: bool = True) -> dict[str, Any]:
    """Evaluate refreshed receipts and persist/notify meaningful transitions."""
    now = _now(now); current = dict(state or read_json(STATE_KEY, STATE_PATH, {}) or {})
    tracked = dict(current.get("tracked") or {}); alerts = []; rows = []
    for receipt in list(receipts)[:MAX_CANDIDATES]:
        ticker = str(receipt.get("ticker") or "").upper()
        if not ticker:
            continue
        previous = tracked.get(ticker) if isinstance(tracked.get(ticker), Mapping) else {}
        first = str(previous.get("first_seen_at") or now.isoformat(timespec="seconds"))
        try: first_date = datetime.fromisoformat(first.replace("Z", "+00:00")).date()
        except Exception: first_date = now.date()
        session = _business_days(first_date, now.date())
        if session > FOLLOW_UP_SESSIONS:
            continue
        comp = _components(receipt, previous); status, emoji = _status(receipt, comp, previous)
        scores = list(previous.get("score_path") or [])[-7:] + [comp["Fresh Score"]]
        row = {**dict(receipt), "monitor_version": VERSION, "first_seen_at": first,
               "last_scan_at": now.isoformat(timespec="seconds"), "follow_up_session": session,
               "components": comp, "score_path": scores[-8:], "status": status, "emoji": emoji,
               "pullback_retest": _pullback_retest(receipt)}
        previous_status = str(previous.get("status") or "")
        meaningful = not previous_status or status != previous_status or abs(comp["Score delta"]) >= 10
        if meaningful:
            title, body = _message(row); event = {"ticker": ticker, "status": status, "title": title, "message": body, "sent": False}
            if notify:
                from notifier import normalize_notification_result, send_pushover_alert
                ok, detail = normalize_notification_result(send_pushover_alert(body, title=title))
                event.update({"sent": ok, "detail": detail})
            alerts.append(event)
        tracked[ticker] = row; rows.append(row)
    missed = []
    active = {str(r.get("ticker") or "").upper() for r in rows}
    for ticker, old in tracked.items():
        if ticker in active or not isinstance(old, Mapping):
            continue
        peak = max([float(x) for x in old.get("score_path") or [0]])
        if peak >= 65 and not old.get("missed_opportunity_recorded"):
            missed.append({"ticker": ticker, "peak_fresh_score": peak, "last_status": old.get("status"),
                           "reason": "Forlot Fresh Trend-køen uten kjøpshandling; mål etterfølgende 5/20-dagers utfall.",
                           "recorded_at": now.isoformat(timespec="seconds")})
            tracked[ticker] = {**dict(old), "missed_opportunity_recorded": True}
    result = {"version": VERSION, "state": "COMPLETED", "last_scan_at": now.isoformat(timespec="seconds"),
              "interval_minutes": INTERVAL_MINUTES, "follow_up_sessions": FOLLOW_UP_SESSIONS,
              "tracked": tracked, "watchlist": rows, "alerts": alerts,
              "missed_opportunities": list(current.get("missed_opportunities") or [])[-250:] + missed,
              "production_scoring_changed": False, "trade_authority": False}
    write_json(STATE_KEY, STATE_PATH, result)
    return result


def run_due_monitor(*, now: datetime | None = None, notify: bool = True) -> dict[str, Any]:
    now = _now(now); state = read_json(STATE_KEY, STATE_PATH, {}) or {}
    if not _due(state, now):
        return {"state": "NOT_DUE", "last_scan_at": state.get("last_scan_at"), "interval_minutes": INTERVAL_MINUTES}
    latest = read_json("market_intelligence/latest_run.json", runtime_data_path("market_intelligence", "latest_run.json"), {}) or {}
    discovery = latest.get("trend_discovery") if isinstance(latest.get("trend_discovery"), Mapping) else {}
    receipts = [dict(x) for x in discovery.get("fresh_trend_watchlist") or [] if isinstance(x, Mapping)][:MAX_CANDIDATES]
    if not receipts:
        result = {**dict(state), "state": "NO_CANDIDATES", "last_scan_at": now.isoformat(timespec="seconds")}
        write_json(STATE_KEY, STATE_PATH, result); return result
    # Refresh the small monitored queue only. The ordinary report retains its full 294/294 stage-1 scan.
    try:
        from candidate_market_data import enrich_candidate_rows
        from trend_intelligence import annotate_run
        seeds = [{"ticker": r.get("ticker"), "market": r.get("market"), "sector": r.get("sector"),
                  "exchange_name": r.get("exchange_name"), "raw": dict(r)} for r in receipts]
        refreshed = enrich_candidate_rows(seeds, max_workers=min(4, len(seeds)), force_refresh=True)
        temp = {"markets": latest.get("markets") or ["Norge"], "candidates": refreshed, "fresh_screening_candidates": refreshed}
        annotate_run(temp, {})
        receipts = list((temp.get("trend_discovery") or {}).get("fresh_trend_watchlist") or receipts)
    except Exception as exc:
        state["refresh_warning"] = f"{type(exc).__name__}: {str(exc)[:400]}"
    return monitor_receipts(receipts, now=now, state=state, notify=notify)
