"""Fail-closed classification of structured insider transaction rows."""
from __future__ import annotations

from typing import Any, Mapping


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).lower().replace("_", " "): v for k, v in row.items()}
    for name in names:
        key = name.lower().replace("_", " ")
        if key in lowered:
            return lowered[key]
    return None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def transaction_type(row: Mapping[str, Any]) -> str:
    text = " ".join(str(_pick(row, x) or "") for x in ("transaction", "text", "type", "transaction type")).lower()
    position_change = _number(_pick(row, "position change"))
    if any(x in text for x in ("sale", "sell", "disposed", "disposition")) or position_change < 0:
        return "SELL"
    if any(x in text for x in ("purchase", "buy", "open market acquisition")) or position_change > 0:
        return "BUY"
    return "OTHER"
