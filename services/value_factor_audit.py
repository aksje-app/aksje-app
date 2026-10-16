"""Read-only extended factor observations for phase 4-7 research.

This module does not score, select finalists, or authorize transactions.
Numbers are retained only when already provided by the upstream data row.
"""
from __future__ import annotations

from typing import Any, Mapping
import math


FACTOR_GROUPS = {
    "valuation": ("trailing_pe", "forward_pe", "price_to_book", "price_to_sales", "ev_to_ebitda", "fcf_yield"),
    "profitability": ("roe", "roic", "operating_margin", "net_margin"),
    "balance_sheet": ("debt_to_equity", "net_debt_to_ebitda", "interest_coverage"),
    "growth": ("earnings_growth", "revenue_growth", "free_cash_flow_growth"),
    "shareholder_returns": ("dividend_yield", "buyback_yield"),
    "risk": ("beta", "volatility_pct", "max_drawdown_pct"),
}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def extended_value_factors(row: Mapping[str, Any]) -> dict[str, Any]:
    """Report available factors and missingness; never rank or trade."""
    groups = {
        group: {key: _finite(row.get(key)) for key in keys}
        for group, keys in FACTOR_GROUPS.items()
    }
    return {
        "groups": groups,
        "missing_by_group": {
            group: [name for name, value in factors.items() if value is None]
            for group, factors in groups.items()
        },
        "observed_factor_count": sum(
            value is not None for factors in groups.values() for value in factors.values()
        ),
        "total_factor_count": sum(map(len, FACTOR_GROUPS.values())),
        "pe_provenance": "UNVERIFIED_TRAILING_OR_FORWARD_FALLBACK"
        if _finite(row.get("trailing_pe")) is not None and row.get("pe_source") is None
        else str(row.get("pe_source") or "MISSING"),
        "shadow_only": True,
        "can_authorize_buy": False,
    }
