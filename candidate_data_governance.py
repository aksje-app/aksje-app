"""Candidate data contract and non-destructive rescue audit."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


DATA_CONTRACT_VERSION = "1.0"
CRITICAL_FIELDS = ("ticker", "market")
IMPORTANT_GROUPS = {
    "price": ("price", "last_price", "current_price"),
    "liquidity": ("liquidity_score", "avg_volume", "average_volume"),
    "risk": ("risk_score", "volatility"),
}
OPTIONAL_GROUPS = {
    "valuation": ("pe", "forward_pe", "pb", "ps"),
    "revisions": ("revision_score", "analyst_revision_score"),
    "short_interest": ("short_data", "short_interest_pct_float", "short_interest_pct"),
    "insider": ("insider_score", "insider_evidence"),
}


def _present(row: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(row.get(key) not in (None, "", [], {}) for key in keys)


def assess_candidate_data(row: Mapping[str, Any]) -> dict[str, Any]:
    missing_critical = [key for key in CRITICAL_FIELDS if not _present(row, (key,))]
    missing_important = [name for name, keys in IMPORTANT_GROUPS.items() if not _present(row, keys)]
    missing_optional = [name for name, keys in OPTIONAL_GROUPS.items() if not _present(row, keys)]
    score = row.get("local_base_score", row.get("effective_entry_score", row.get("investment_score")))
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = None
    rescue_reasons = []
    if not missing_critical and missing_important and numeric_score is not None and numeric_score >= 60.0:
        rescue_reasons.append("STRONG_PARTIAL_SCORE")
    if not missing_critical and len(missing_optional) >= 2 and numeric_score is not None and numeric_score >= 65.0:
        rescue_reasons.append("OPTIONAL_DATA_GAPS")
    return {
        "schema_version": DATA_CONTRACT_VERSION,
        "ticker": str(row.get("ticker") or ""),
        "missing_critical": missing_critical,
        "missing_important": missing_important,
        "missing_optional": missing_optional,
        "decision_data_state": "BLOCKED" if missing_critical else ("RESCUE" if rescue_reasons else "READY"),
        "rescue_required": bool(rescue_reasons),
        "rescue_reasons": rescue_reasons,
        "unknown_optional_fields_are_not_zero": True,
    }


def build_candidate_data_audit(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [assess_candidate_data(row) for row in candidates if isinstance(row, Mapping)]
    return {
        "schema_version": DATA_CONTRACT_VERSION,
        "candidate_count": len(rows),
        "ready_count": sum(row["decision_data_state"] == "READY" for row in rows),
        "rescue_count": sum(row["decision_data_state"] == "RESCUE" for row in rows),
        "blocked_count": sum(row["decision_data_state"] == "BLOCKED" for row in rows),
        "rescue_queue": [row for row in rows if row["rescue_required"]],
        "candidates": rows,
        "selection_order_invariant_required": True,
    }


def deterministic_global_shortlist(candidates: Sequence[Mapping[str, Any]], *, limit: int = 60, minimum_per_market: int = 10) -> list[dict[str, Any]]:
    """Deterministic market minimum plus score-ranked global remainder; no market maximum."""
    rows = [dict(row) for row in candidates if isinstance(row, Mapping)]
    def key(row: Mapping[str, Any]) -> tuple[float, str]:
        try:
            score = float(row.get("local_base_score", row.get("effective_entry_score", row.get("investment_score", -1e9))))
        except (TypeError, ValueError):
            score = -1e9
        return (-score, str(row.get("ticker") or ""))
    rows.sort(key=key)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    markets = sorted({str(row.get("market") or "Ukjent") for row in rows})
    for market in markets:
        for row in [item for item in rows if str(item.get("market") or "Ukjent") == market][:max(0, minimum_per_market)]:
            ticker = str(row.get("ticker") or "")
            if ticker not in seen and len(selected) < limit:
                selected.append(row); seen.add(ticker)
    for row in rows:
        ticker = str(row.get("ticker") or "")
        if ticker not in seen and len(selected) < limit:
            selected.append(row); seen.add(ticker)
    return sorted(selected, key=key)


__all__ = ["DATA_CONTRACT_VERSION", "assess_candidate_data", "build_candidate_data_audit", "deterministic_global_shortlist"]
