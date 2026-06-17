from __future__ import annotations

from typing import Any, Mapping


def clamp_score(value: Any, default: float = 5.0) -> float:
    try:
        if value is None or value == "":
            value = default
        score = float(value)
    except Exception:
        score = float(default)
    if score <= 1.0:
        # Support 0..1 scores from existing modules.
        score *= 10.0
    return round(max(0.0, min(10.0, score)), 2)


def first_value(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return None
