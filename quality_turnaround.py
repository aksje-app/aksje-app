"""Independent, observational turnaround evidence. Never changes trade gates."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

MODEL = "turnaround_watch@1.0"


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def date(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def evaluate_turnaround(raw: Mapping[str, Any], *, as_of: datetime) -> dict[str, Any]:
    """Use equal-duration, same-season YoY data observed no later than as_of.

    Retrieval time is availability when publication time is unknown. Fiscal
    period end alone is never treated as a tradable information timestamp.
    """
    now = date(as_of)
    observed = date(raw.get("interim_observed_at"))
    result = {"model": MODEL, "shadow_only": True, "production_effect": False,
              "status": "INSUFFICIENT", "financial_improvement": False,
              "missing": [], "source": str(raw.get("interim_source") or "NOT_AVAILABLE")[:200],
              "primary_filing_status": str(raw.get("primary_filing_status") or "NOT_VERIFIED"),
              "observed_at": observed.isoformat() if observed else None,
              "price_evidence": "NOT_AVAILABLE", "event_evidence": "NOT_AVAILABLE"}
    result["announcement_coverage"] = raw.get("official_announcement_coverage") or {"status": "NOT_AVAILABLE"}
    result["event_coverage"] = raw.get("official_event_coverage") or {"status": "NOT_AVAILABLE"}
    result["interim_periods"] = list(raw.get("interim_periods") or [])[:16]
    if not observed or observed > now:
        result["missing"].append("POINT_IN_TIME_INTERIM_AVAILABILITY")
        return result
    periods = []
    for row in list(raw.get("interim_periods") or [])[:16]:
        if not isinstance(row, Mapping):
            continue
        end = date(row.get("period_end"))
        published = date(row.get("published_at"))
        available = max(observed, published) if published else observed
        if end and end <= now and available <= now and row.get("duration_months") in (3, 6):
            periods.append((end, dict(row)))
    periods.sort(key=lambda pair: pair[0], reverse=True)
    if not periods:
        result["missing"].append("INTERIM_STATEMENTS")
        return result
    latest_date, latest = periods[0]
    result["period_end"] = latest_date.date().isoformat()
    result["age_days"] = (now - latest_date).days
    # +/- 15 days accommodates 52/53-week fiscal calendars without quarter mixing.
    prior = next((r for end, r in periods[1:] if 350 <= (latest_date - end).days <= 380
                  and r.get("duration_months") == latest["duration_months"]), None)
    if result["age_days"] > 240:
        result["missing"].append("FRESH_INTERIM_STATEMENTS")
    if not prior:
        result["missing"].append("COMPARABLE_PRIOR_YEAR_PERIOD")
        return result
    result["comparison_period_end"] = str(prior["period_end"])
    metrics = {}
    for key in ("revenue", "operating_income", "net_income", "fcf", "eps"):
        current, old = number(latest.get(key)), number(prior.get(key))
        metrics[key] = {"current": current, "prior": old,
                        "delta": current - old if current is not None and old is not None else None,
                        "growth_pct": (current / old - 1) * 100 if current is not None and old is not None and old > 0 else None}
    rev, op = metrics["revenue"], metrics["operating_income"]
    margin = op["current"] / rev["current"] if rev["current"] is not None and rev["current"] > 0 and op["current"] is not None else None
    old_margin = op["prior"] / rev["prior"] if rev["prior"] is not None and rev["prior"] > 0 and op["prior"] is not None else None
    result["metrics"] = metrics
    result["operating_margin_delta_pp"] = (margin - old_margin) * 100 if margin is not None and old_margin is not None else None
    for key in ("revenue", "operating_income"):
        if metrics[key]["delta"] is None:
            result["missing"].append(f"YOY_{key.upper()}")
    for key in ("fcf", "net_income", "eps"):
        if metrics[key]["delta"] is None:
            result["missing"].append(f"OPTIONAL_YOY_{key.upper()}")
    required_missing = any(not key.startswith("OPTIONAL_") for key in result["missing"])
    improving = (not required_missing and rev["current"] > 0 and rev["delta"] >= 0 and op["current"] > 0
                 and op["delta"] > 0 and margin is not None and old_margin is not None and margin > old_margin)
    result["financial_improvement"] = bool(improving)
    result["status"] = "POSSIBLE_TURNAROUND" if improving else "INSUFFICIENT" if required_missing else "NO_IMPROVEMENT"
    market = raw.get("turnaround_market_evidence") or {}
    market_time = date(market.get("observed_at"))
    if market_time and market_time <= now:
        result["price_evidence"] = dict(market)
    events = [dict(e) for e in (raw.get("official_market_events") or [])[:20]
              if date(e.get("observed_at")) and date(e.get("occurred_at"))
              and date(e["observed_at"]) <= now and 0 <= (now - date(e["occurred_at"])).days <= 90]
    if events:
        result["event_evidence"] = events
    result["interpretation"] = "Mulig nyere forbedring; svak flerårig kvalitet kan fortsatt gjelde. Ingen kjøpsordre eller endring av risikokrav."
    return result


def discovery_watch(row: Mapping[str, Any]) -> bool:
    """Market-wide inexpensive watch before the 20-name detailed-analysis cut.

    A discovery flag reserves analysis, never asserts financial confirmation.
    """
    growth = number(row.get("earnings_growth"))
    momentum = number(row.get("momentum_score"))
    trend = number(row.get("trend_score"))
    return bool(growth is not None and growth > 0 and momentum is not None and momentum >= 60
                and trend is not None and trend >= 60)


def reserve_watch_slots(ranked, limit, official_tickers=()):
    limit = max(1, min(20, int(limit)))
    official = set(official_tickers)
    event_rows = [row for row in ranked if row["ticker"] in official]
    growth_rows = [row for row in ranked if discovery_watch(row)]
    watch = []
    for index in range(max(len(event_rows), len(growth_rows))):
        for pool in (event_rows, growth_rows):
            if index < len(pool) and pool[index] not in watch and len(watch) < min(4, limit):
                watch.append(pool[index])
        if len(watch) >= min(4, limit):
            break
    selected = list(watch)
    tickers = {row["ticker"] for row in watch}
    for row in ranked:
        if row["ticker"] not in tickers and len(selected) < limit:
            selected.append(row)
            tickers.add(row["ticker"])
    return selected, [row["ticker"] for row in watch]


def market_context(prescreen):
    observed = datetime.now(timezone.utc).isoformat()
    return {r["ticker"]: {"observed_at": observed, "source": "FULL_MARKET_PRESCREEN",
                           "momentum_score": r.get("momentum_score"), "trend_score": r.get("trend_score"),
                           "volume_ratio": r.get("volume_ratio"), "relative_strength": r.get("relative_strength"),
                           "coverage": "AVAILABLE_FIELDS_ONLY"}
            for r in prescreen.get("rows", []) if r.get("ticker")}
