"""Bounded scheduled quality screen prepared before required reports.

The job is observational: it never places trades.  It selects a small set from
the latest market report, runs before (not inside) the required report window,
and publishes an unlisted PDF.  Partial provider coverage remains visible.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from durable_runtime import read_json
from storage_architecture import runtime_data_path


LOCAL_ZONE = ZoneInfo("Europe/Oslo")
SCHEDULED_LIMIT = 15
PRE_REPORT_SLOTS = (
    (time(7, 20), time(7, 45), "08:00"),
    (time(13, 20), time(13, 45), "14:00"),
    (time(21, 20), time(21, 45), "22:00"),
)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def scheduled_slot(now: datetime | None = None) -> str:
    current = (now or datetime.now(timezone.utc)).astimezone(LOCAL_ZONE)
    if current.weekday() > 4:
        return ""
    clock = current.time().replace(tzinfo=None)
    for start, end, report_time in PRE_REPORT_SLOTS:
        if start <= clock <= end:
            return f"{current.date().isoformat()}T{report_time}@Europe/Oslo"
    return ""


def _candidate_rows(latest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in latest.get("candidates") or []:
        if isinstance(value, Mapping):
            rows.append(dict(value))
    for market in latest.get("market_runs") or []:
        if not isinstance(market, Mapping):
            continue
        for value in market.get("candidates") or []:
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def select_symbols(latest: Mapping[str, Any], *, limit: int = SCHEDULED_LIMIT) -> list[str]:
    """Prefer holdings, then the latest highest-scoring market candidates."""
    from quality_valuation import _safe_ticker

    selected: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        ticker = _safe_ticker(value)
        if ticker and ticker not in seen and len(selected) < max(1, int(limit)):
            seen.add(ticker)
            selected.append(ticker)

    portfolio = latest.get("portfolio_intelligence") or {}
    if isinstance(portfolio, Mapping):
        for row in portfolio.get("positions") or []:
            if isinstance(row, Mapping):
                add(row.get("ticker"))
    super_portfolio = latest.get("super_portfolio_snapshot") or {}
    if isinstance(super_portfolio, Mapping):
        for row in super_portfolio.get("positions") or []:
            if isinstance(row, Mapping):
                add(row.get("ticker"))

    rows = _candidate_rows(latest)
    rows.sort(key=lambda row: _number(
        row.get("autonomy_adjusted_investment_score", row.get("investment_score", row.get("score")))
    ), reverse=True)
    for row in rows:
        add(row.get("ticker") or row.get("symbol"))
    return selected


def _latest_market_run() -> dict[str, Any]:
    value = read_json(
        "market_intelligence/latest_run.json",
        runtime_data_path("market_intelligence", "latest_run.json"),
        {},
    )
    return dict(value) if isinstance(value, Mapping) else {}


def _publish_pdf(result: dict[str, Any]) -> str:
    from public_report_store import publish_durable_pdf
    from quality_valuation_ui import build_screen_pdf
    from report_delivery import public_report_url

    result.setdefault("report_id", f"QV-{str(result.get('generated_at') or '').replace(':', '').replace('-', '')[:15]}")
    result["public_pdf_name"] = f"Kvalitet_verdsettelse_{result['report_id']}.pdf"
    publish_durable_pdf(result, build_screen_pdf(result))
    result["report_url"] = public_report_url(result)
    return str(result.get("report_url") or "")


def run_due_scheduled_screen(now: datetime | None = None) -> dict[str, Any]:
    """Run at most once per pre-report slot and fail without blocking reports."""
    from quality_valuation_store import load_latest, persist_screen

    slot = scheduled_slot(now)
    if not slot:
        return {"state": "NOT_DUE"}
    previous = load_latest()
    if str(previous.get("scheduled_slot") or "") == slot:
        return {"state": "ALREADY_COMPLETED", "scheduled_slot": slot,
                "run_key": previous.get("run_key"), "report_url": previous.get("report_url")}

    latest_market = _latest_market_run()
    symbols = select_symbols(latest_market)
    if not symbols:
        return {"state": "NO_CANDIDATES", "scheduled_slot": slot}

    from quality_valuation_control import single_manual_screen
    from quality_valuation import run_screen
    from quality_valuation_data import isolated_financial_snapshot, memory_budget_ok, observed_driver_prices
    from quality_valuation_ui import required_report_busy

    if required_report_busy():
        return {"state": "DEFERRED_REQUIRED_REPORT", "scheduled_slot": slot}
    with single_manual_screen() as acquired:
        if not acquired:
            return {"state": "ALREADY_RUNNING", "scheduled_slot": slot}
        result = run_screen(
            symbols, isolated_financial_snapshot, deadline_seconds=165,
            memory_guard=lambda: memory_budget_ok() and not required_report_busy(),
        )
        result.update({
            "run_mode": "SCHEDULED_SHADOW", "scheduled_slot": slot,
            "source_report_id": latest_market.get("report_id") or latest_market.get("run_id"),
        })
        names = [name for items in (result.get("groups") or {}).values() for item in items
                 for name in item.get("market_drivers") or []]
        if names and result.get("elapsed_seconds", 999) < 145 and memory_budget_ok():
            result["driver_prices"] = observed_driver_prices(names)
        _publish_pdf(result)
        result["run_key"] = persist_screen(result)

    # Only future primary-source verified rows can create investment alerts.
    # Current Yahoo screening therefore normally produces zero events.
    from quality_valuation_alerts import transition_messages
    events = transition_messages(previous, result)
    sent = 0
    if events:
        from notifier import send_pushover_alert
        for event in events:
            ok, _ = send_pushover_alert(
                event["text"], title=event["title"], url=result.get("report_url") or None,
                url_title="Åpne kvalitetsrapport", priority=0,
            )
            sent += int(bool(ok))
    return {
        "state": str(result.get("state") or "COMPLETED"),
        "scheduled_slot": slot, "selected": result.get("selected"),
        "completed": result.get("completed"), "failures": len(result.get("failures") or []),
        "run_key": result.get("run_key"), "report_url": result.get("report_url"),
        "verified_alerts": len(events), "alerts_sent": sent,
    }
