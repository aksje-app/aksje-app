"""Strategy-relevant evidence policy for production entry decisions.

Missing evidence may only block an entry when the affected evidence area is
material to the strategies that actually qualify the candidate.  Unverified
facts are always neutral: they cannot authorize a trade or add evidence credit.
"""
from __future__ import annotations

from typing import Any, Mapping


TERMINAL = {"AVAILABLE", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "VERIFIED_FACTS_NONE"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _status(candidate: Mapping[str, Any], area: str) -> str:
    coverage = _mapping(candidate.get("evidence_coverage"))
    detail = _mapping(coverage.get(area))
    return str(detail.get("status") or "NOT_SEARCHED").upper()


def _qualifying_strategies(candidate: Mapping[str, Any]) -> set[str]:
    analysis = _mapping(candidate.get("analysis_ranking"))
    matches = analysis.get("matches") or candidate.get("strategy_matches") or []
    if isinstance(matches, str):
        matches = [matches]
    return {str(item).strip().casefold() for item in matches if str(item).strip()}


def evidence_decision_assessment(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fail-closed, strategy-relevant evidence assessment.

    News remains required because it is used as a general event-risk screen in
    the current production model. Insider evidence is required only when the
    candidate qualifies exclusively through the Insider strategy. Candidates
    with an independent Growth, Momentum, Quality, Value, Income or Event
    Recovery qualification are not invalidated by a temporary insider-source
    failure; the insider area is neutralised instead.
    """
    coverage = _mapping(candidate.get("evidence_coverage"))
    if not coverage:
        legacy_valid = candidate.get("evidence_valid_for_decision") is True
        return {
            "valid_for_decision": legacy_valid,
            "required_areas": [], "missing_required_areas": [] if legacy_valid else ["legacy_evidence_contract"],
            "neutralised_optional_areas": [], "statuses": {},
            "qualifying_strategies": sorted(_qualifying_strategies(candidate)),
            "policy_version": "STRATEGY_RELEVANT_EVIDENCE_V1_LEGACY_BRIDGE",
        }
    strategies = _qualifying_strategies(candidate)
    independent = strategies - {"insider"}
    required = {"news"}
    if "insider" in strategies and not independent:
        required.add("insider")
    statuses = {area: _status(candidate, area) for area in ("news", "insider")}
    missing = sorted(area for area in required if statuses[area] not in TERMINAL)
    neutralised = sorted(area for area in ("news", "insider") if area not in required and statuses[area] not in TERMINAL)
    return {
        "valid_for_decision": not missing,
        "required_areas": sorted(required),
        "missing_required_areas": missing,
        "neutralised_optional_areas": neutralised,
        "statuses": statuses,
        "qualifying_strategies": sorted(strategies),
        "policy_version": "STRATEGY_RELEVANT_EVIDENCE_V1",
    }
