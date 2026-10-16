"""Non-authorizing deep-value candidate diagnostics for the existing quality prescreen."""
from __future__ import annotations

from typing import Any, Mapping


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def deep_value_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    """Observe valuation and quality evidence; never issue buy authorizations."""
    pe = _number(row.get("trailing_pe"))
    roe = _number(row.get("roe"))
    debt = _number(row.get("debt_to_equity"))
    earnings_growth = _number(row.get("earnings_growth"))
    revenue_growth = _number(row.get("revenue_growth"))
    # Negative/zero PE is not a cheap profitable business.
    low_pe = pe is not None and 0 < pe <= 12
    adequate_roe = roe is not None and roe >= 10
    manageable_debt = debt is not None and debt <= 100
    flags = {
        "positive_low_pe": low_pe,
        "adequate_roe": adequate_roe,
        "manageable_debt": manageable_debt,
        "earnings_growth_known": earnings_growth is not None,
        "revenue_growth_known": revenue_growth is not None,
    }
    missing = [key for key, value in (("trailing_pe", pe), ("roe", roe), ("debt_to_equity", debt)) if value is None]
    status = "INSUFFICIENT_EVIDENCE" if missing else ("DEEP_VALUE_WATCH" if all((low_pe, adequate_roe, manageable_debt)) else "NOT_QUALIFIED")
    return {"status": status, "flags": flags, "missing_fields": missing,
            "trailing_pe": pe, "roe": roe, "debt_to_equity": debt,
            "shadow_only": True, "can_authorize_buy": False,
            "reason": "Cheap valuation is a screening observation, not an investment decision."}
