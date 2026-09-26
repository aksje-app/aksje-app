"""Scheduled full-market quality screen prepared before required reports.

The scheduled quality job never relies on an arbitrarily old candidate list.
For every due slot it screens the complete currently enabled production-market
universe, ranks the fresh first-pass results, then deep-analyzes fresh finalists
plus a separate bounded set of existing holdings. The job is observational and
never places trades.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
import os
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from durable_runtime import read_json
from storage_architecture import runtime_data_path

LOCAL_ZONE = ZoneInfo("Europe/Oslo")
CANDIDATE_BASIS_MAX_AGE_MINUTES = 60
SCHEDULED_CANDIDATE_LIMIT = 15
SCHEDULED_HOLDING_LIMIT = 5
SCHEDULED_ANALYSIS_LIMIT = 20
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


def _utc_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def market_run_age_minutes(latest: Mapping[str, Any], now: datetime | None = None) -> float | None:
    """Age of the legacy market candidate source, for diagnostics only."""
    stamp = next((_parse_time(latest.get(key)) for key in
                  ("completed_at", "generated_at", "created_at", "updated_at")
                  if _parse_time(latest.get(key)) is not None), None)
    if stamp is None:
        return None
    age = (_utc_now(now) - stamp).total_seconds() / 60
    return round(max(0.0, age), 1)


def scheduled_slot(now: datetime | None = None) -> str:
    current = _utc_now(now).astimezone(LOCAL_ZONE)
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
        if isinstance(market, Mapping):
            for value in market.get("candidates") or []:
                if isinstance(value, Mapping):
                    rows.append(dict(value))
    return rows


def _holding_symbols(latest: Mapping[str, Any], *, limit: int = SCHEDULED_HOLDING_LIMIT) -> list[str]:
    """Holdings have reserved deep-analysis capacity; they never consume finalist slots."""
    from quality_valuation import _safe_ticker
    selected: list[str] = []
    seen: set[str] = set()
    for section in ("portfolio_intelligence", "super_portfolio_snapshot"):
        portfolio = latest.get(section) or {}
        if not isinstance(portfolio, Mapping):
            continue
        for row in portfolio.get("positions") or []:
            if not isinstance(row, Mapping):
                continue
            ticker = _safe_ticker(row.get("ticker"))
            if ticker and ticker not in seen:
                seen.add(ticker)
                selected.append(ticker)
                if len(selected) >= max(0, int(limit)):
                    return selected
    return selected


def select_symbols(latest: Mapping[str, Any], *, limit: int = SCHEDULED_CANDIDATE_LIMIT) -> list[str]:
    """Legacy diagnostic helper: rank saved candidates, but never used as fresh market discovery."""
    from quality_valuation import _safe_ticker
    rows = _candidate_rows(latest)
    rows.sort(key=lambda row: _number(
        row.get("autonomy_adjusted_investment_score", row.get("investment_score", row.get("score")))
    ), reverse=True)
    selected: list[str] = []
    seen: set[str] = set()
    for row in rows:
        ticker = _safe_ticker(row.get("ticker") or row.get("symbol"))
        if ticker and ticker not in seen:
            seen.add(ticker)
            selected.append(ticker)
            if len(selected) >= max(1, int(limit)):
                break
    return selected


def _latest_market_run() -> dict[str, Any]:
    value = read_json(
        "market_intelligence/latest_run.json",
        runtime_data_path("market_intelligence", "latest_run.json"),
        {},
    )
    return dict(value) if isinstance(value, Mapping) else {}


def _scheduled_markets() -> list[str]:
    norway_only = str(os.getenv("PRODUCTION_NORWAY_ONLY", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
    if norway_only:
        return ["Norge"]
    from market_universe import production_market_scopes
    return list(production_market_scopes())


def _full_universe(markets: Sequence[str]) -> list[str]:
    from stocks import get_norwegian_tickers, get_swedish_tickers, get_us_broad_tickers
    rows: list[str] = []
    for market in markets:
        if market == "Norge":
            rows.extend(get_norwegian_tickers(limit=None) or [])
        elif market == "Sverige":
            rows.extend(get_swedish_tickers(limit=None) or [])
        elif market == "USA":
            rows.extend(get_us_broad_tickers(limit=1600) or [])
    return list(dict.fromkeys(str(value or "").strip().upper() for value in rows if str(value or "").strip()))


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
    """Fresh full-market pass -> finalists -> bounded deep analysis, once per report slot."""
    from quality_valuation_store import load_latest, persist_screen

    current = _utc_now(now)
    slot = scheduled_slot(current)
    if not slot:
        return {"state": "NOT_DUE"}
    previous = load_latest()
    if str(previous.get("scheduled_slot") or "") == slot:
        return {
            "state": "ALREADY_COMPLETED", "scheduled_slot": slot,
            "run_key": previous.get("run_key"), "report_url": previous.get("report_url"),
        }

    latest_market = _latest_market_run()
    latest_age = market_run_age_minutes(latest_market, current)
    markets = _scheduled_markets()
    universe = _full_universe(markets)
    if not universe:
        return {"state": "NO_CANDIDATES", "scheduled_slot": slot, "markets": markets}

    from quality_valuation_control import single_manual_screen
    from quality_valuation import run_screen
    from quality_valuation_data import isolated_financial_snapshot, memory_budget_ok, observed_driver_prices
    from quality_valuation_ui import required_report_busy
    from quality_market_prescreen import full_market_prescreen

    if required_report_busy():
        return {"state": "DEFERRED_REQUIRED_REPORT", "scheduled_slot": slot}

    with single_manual_screen() as acquired:
        if not acquired:
            return {"state": "ALREADY_RUNNING", "scheduled_slot": slot}

        prescreen = full_market_prescreen(
            universe,
            SCHEDULED_CANDIDATE_LIMIT,
            memory_guard=lambda: memory_budget_ok() and not required_report_busy(),
            deadline_seconds=900,
        )
        finalists = list(prescreen.get("finalists") or [])
        holdings = _holding_symbols(latest_market)
        analysis_symbols = list(dict.fromkeys([*holdings, *finalists]))[:SCHEDULED_ANALYSIS_LIMIT]
        if not analysis_symbols:
            return {
                "state": "NO_USABLE_CANDIDATES", "scheduled_slot": slot, "markets": markets,
                "market_universe_count": len(universe),
                "market_examined_count": int(prescreen.get("examined_count") or 0),
                "market_failed_count": int(prescreen.get("failed_count") or 0),
            }

        result = run_screen(
            analysis_symbols,
            isolated_financial_snapshot,
            deadline_seconds=165,
            memory_guard=lambda: memory_budget_ok() and not required_report_busy(),
        )
        result.update({
            "run_mode": "SCHEDULED_SHADOW",
            "scheduled_slot": slot,
            "markets": markets,
            "source_report_id": latest_market.get("report_id") or latest_market.get("run_id"),
            "legacy_market_run_age_minutes": latest_age,
            "candidate_basis_max_age_minutes": CANDIDATE_BASIS_MAX_AGE_MINUTES,
            "candidate_basis_refreshed": True,
            "candidate_basis_generated_at": current.isoformat(timespec="seconds"),
            "candidate_basis_source": "FULL_MARKET_PRESCREEN",
            "market_universe_count": int(prescreen.get("universe_count") or len(universe)),
            "market_examined_count": int(prescreen.get("examined_count") or 0),
            "market_usable_count": int(prescreen.get("usable_count") or 0),
            "market_failed_count": int(prescreen.get("failed_count") or 0),
            "market_coverage_complete": bool(prescreen.get("coverage_complete")),
            "market_prescreen_stop_reason": str(prescreen.get("stop_reason") or ""),
            "prescreen_finalists": finalists,
            "holding_symbols": holdings,
        })
        names = [name for items in (result.get("groups") or {}).values() for item in items
                 for name in item.get("market_drivers") or []]
        if names and result.get("elapsed_seconds", 999) < 145 and memory_budget_ok():
            result["driver_prices"] = observed_driver_prices(names)
        _publish_pdf(result)
        result["run_key"] = persist_screen(result)

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
        "scheduled_slot": slot,
        "markets": markets,
        "selected": result.get("selected"),
        "completed": result.get("completed"),
        "failures": len(result.get("failures") or []),
        "market_universe_count": result.get("market_universe_count"),
        "market_examined_count": result.get("market_examined_count"),
        "market_usable_count": result.get("market_usable_count"),
        "market_failed_count": result.get("market_failed_count"),
        "market_coverage_complete": result.get("market_coverage_complete"),
        "candidate_basis_refreshed": True,
        "holding_count": len(result.get("holding_symbols") or []),
        "finalist_count": len(result.get("prescreen_finalists") or []),
        "run_key": result.get("run_key"),
        "report_url": result.get("report_url"),
        "verified_alerts": len(events),
        "alerts_sent": sent,
    }
