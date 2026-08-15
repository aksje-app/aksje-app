"""Canonical, fail-closed decision input resolvers.

Every analytical, portfolio and execution gate must resolve critical inputs
through this module.  A resolver may return zero/unknown, but parallel layers
must never invent different answers for the same candidate.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


PRICE_KEYS = ("price", "current_price", "last_price", "close", "regularMarketPrice", "last")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else float(default)
    except (TypeError, ValueError):
        return float(default)


def candidate_price(candidate: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> float:
    """Return the one canonical execution price for a candidate.

    The market pipeline serialises provider fields below ``raw`` while replay
    snapshots also materialise ``price`` at the snapshot level.  Both forms are
    valid inputs; zero, negative and non-finite values remain fail-closed.
    """
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    decision_inputs = candidate.get("decision_inputs") if isinstance(candidate.get("decision_inputs"), Mapping) else {}
    snapshot = candidate.get("market_snapshot") if isinstance(candidate.get("market_snapshot"), Mapping) else {}
    for source in (candidate, raw, decision_inputs, snapshot):
        for key in PRICE_KEYS:
            value = _number(source.get(key), 0.0)
            if value > 0:
                return value
    if existing:
        for key in ("last_price", "average_price"):
            value = _number(existing.get(key), 0.0)
            if value > 0:
                return value
    return 0.0


def candidate_base_score(candidate: Mapping[str, Any], default: float = 0.0) -> float:
    """Return the unadjusted analytical score used for history and exits."""
    for key in ("autonomy_base_investment_score", "investment_score", "score", "combined_score", "decision_score"):
        if candidate.get(key) is not None:
            return _number(candidate.get(key), default)
    return float(default)


def candidate_entry_score(candidate: Mapping[str, Any], default: float = 0.0) -> float:
    """Return the canonical entry score after neutralising unverified credit."""
    if candidate.get("autonomy_adjusted_investment_score") is not None:
        score = _number(candidate.get("autonomy_adjusted_investment_score"), default)
    else:
        score = candidate_base_score(candidate, default)
    passport = candidate.get("evidence_passport") if isinstance(candidate.get("evidence_passport"), Mapping) else {}
    areas = passport.get("areas") if isinstance(passport.get("areas"), Mapping) else {}
    terminal = {"AVAILABLE", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "VERIFIED_FACTS_NONE"}
    neutralised = 0.0
    for detail in areas.values():
        if not isinstance(detail, Mapping):
            continue
        if str(detail.get("status") or "").upper() not in terminal:
            neutralised += max(0.0, _number(detail.get("ranking_contribution"), 0.0))
    return max(0.0, score - neutralised)


def candidate_score_audit(candidate: Mapping[str, Any]) -> dict[str, float]:
    """Expose raw, neutralised and removed score credit for reports/replay."""
    raw = _number(candidate.get("autonomy_adjusted_investment_score"), candidate_base_score(candidate))
    effective = candidate_entry_score(candidate)
    return {"raw_adjusted_score": round(raw, 4), "effective_entry_score": round(effective, 4),
            "unverified_positive_credit_removed": round(max(0.0, raw - effective), 4)}
