"""Independent audit of deep-value candidates excluded by the legacy finalist list.

No mutation of ranking, candidate inputs, portfolio state or trading permissions.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from services.deep_value_shadow_service import deep_value_evidence
from services.value_factor_audit import extended_value_factors


def missed_value_candidate_audit(rows: Sequence[Mapping[str, Any]], finalists: Sequence[str]) -> dict[str, Any]:
    chosen = {str(t).strip().upper() for t in finalists}
    missed = []
    counts = {"qualified": 0, "missed": 0, "pe_forward_fallback": 0,
              "pe_unverified": 0, "possible_value_trap": 0}
    for row in rows:
        if str(row.get("data_fetch_status") or "").upper() in {"ERROR", "QUARANTINED"}:
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        evidence = deep_value_evidence(row)
        if evidence["status"] != "DEEP_VALUE_WATCH":
            continue
        counts["qualified"] += 1
        if ticker in chosen:
            continue
        counts["missed"] += 1
        factors = extended_value_factors(row)
        provenance = factors["pe_provenance"]
        if provenance == "forwardPE_fallback":
            counts["pe_forward_fallback"] += 1
        elif provenance == "UNVERIFIED_TRAILING_OR_FORWARD_FALLBACK":
            counts["pe_unverified"] += 1
        # Flags are observations only: no automatic rejection/selection.
        signals = []
        for key in ("earnings_growth", "revenue_growth", "operating_margin", "free_cash_flow"):
            value = row.get(key)
            try:
                if value is not None and float(value) < 0:
                    signals.append(key + "_negative")
            except (TypeError, ValueError):
                pass
        if signals:
            counts["possible_value_trap"] += 1
        missed.append({"ticker": ticker, "legacy_score": row.get("quality_prescreen_score"),
                       "pe_provenance": provenance, "risk_signals": signals,
                       "needs_review": bool(signals) or provenance != "trailingPE",
                       "can_authorize_buy": False})
    missed.sort(key=lambda x: (x["ticker"]))
    return {"counts": counts, "missed_candidates": missed,
            "shadow_only": True, "can_authorize_buy": False}
