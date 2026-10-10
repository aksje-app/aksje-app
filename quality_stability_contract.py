"""Hard stability contracts for the Quality module.

These rules are intentionally small, deterministic and user-flow oriented.
They are used by application routing and by release acceptance tests so that
"green tests" cannot merely prove that a label exists.
"""
from __future__ import annotations

from typing import Any, Mapping

QUALITY_ROUTE = "quality_valuation"
QUALITY_REPORTS_RETURN = {"aa_nav": QUALITY_ROUTE, "qv_reports": "1"}

# Routes that app.py is allowed to accept from aa_nav deep links.
SUPPORTED_DEEP_LINK_NAV = frozenset({
    "dashboard", "analysis", "top_picks", "portfolio", "reports", "jobs",
    "jobber", "scheduler", "planlegger", "approvals", "godkjenninger",
    "alerts", "varsler", "operations", "drift", "driftssenter",
    "drift_center", "paper", "paper_trading", "papertrading", "long_engine",
    "market", QUALITY_ROUTE, "ai", "autonomy", "autonomous", "autonomi",
    "fx_alerts", "currency_alerts", "valutavarsler", "settings",
    "innstillinger", "admin", "systemstatus", "system", "control_center",
    "super_portfolio", "superfund",
})


def is_supported_deep_link_nav(value: Any) -> bool:
    return str(value or "").strip().lower() in SUPPORTED_DEEP_LINK_NAV


def validate_quality_row(row: Mapping[str, Any]) -> list[str]:
    """Return hard semantic contradictions; empty means PASS."""
    errors: list[str] = []
    group = str(row.get("group") or "")
    quality_state = str(row.get("quality_state") or "")
    reason = str(row.get("review_reason_category") or "")
    try:
        stars = int(row.get("overall_stars") or 0)
    except (TypeError, ValueError):
        stars = 0
    scores = []
    for key in ("quality_score", "valuation_score", "trend_score", "data_score"):
        try:
            scores.append(int(row.get(key)))
        except (TypeError, ValueError):
            pass

    if stars >= 5 and scores and min(scores) < 4:
        errors.append("5_STARS_WITH_WEAK_SUBSCORE")
    if quality_state in {"QUALITY", "IMPROVING"} and reason == "QUALITY_WEAK":
        errors.append("QUALITY_STATE_REASON_CONTRADICTION")
    if group in {"Kvalitetsselskap", "Attraktivt priset kandidat"}:
        try:
            qscore = int(row.get("quality_score") or 0)
        except (TypeError, ValueError):
            qscore = 0
        if qscore and qscore < 3:
            errors.append("QUALITY_GROUP_WITH_LOW_QUALITY_SCORE")
    return errors


def validate_v2_summary(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    disagreements = int(summary.get("disagreement_count") or 0)
    available = bool(summary.get("classification_available", False))
    if available:
        weaker = int(summary.get("v2_weaker_count") or 0)
        stronger = int(summary.get("v2_stronger_count") or 0)
        weaker_tickers = {str(v).strip().upper() for v in (summary.get("v2_weaker_tickers") or []) if str(v).strip()}
        stronger_tickers = {str(v).strip().upper() for v in (summary.get("v2_stronger_tickers") or []) if str(v).strip()}
        if weaker + stronger != disagreements:
            errors.append("V2_DISAGREEMENT_SUM_MISMATCH")
        if weaker != len(weaker_tickers) or stronger != len(stronger_tickers):
            errors.append("V2_TICKER_COUNT_MISMATCH")
        if weaker_tickers & stronger_tickers:
            errors.append("V2_TICKER_DIRECTION_OVERLAP")
        if not str(summary.get("classification_schema") or ""):
            errors.append("V2_CLASSIFICATION_SCHEMA_MISSING")
    return errors


def validate_report_return_query(query: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    nav = str(query.get("aa_nav") or "")
    if nav != QUALITY_ROUTE:
        errors.append("REPORT_RETURN_NOT_QUALITY")
    if str(query.get("qv_reports") or "") != "1":
        errors.append("REPORT_RETURN_NOT_SELECTOR")
    if not is_supported_deep_link_nav(nav):
        errors.append("REPORT_RETURN_ROUTE_REJECTED")
    return errors
