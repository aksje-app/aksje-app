"""Shared utility helpers for AI Aksje Analyzer.

v18.6.3a: single source of truth for common conversions, clamping,
UTC timestamps and Postgres availability checks.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import psycopg2  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None  # type: ignore


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert common numeric inputs safely to float.

    Handles None, empty strings, percentages, spaces, comma decimals,
    NaN and infinity. Returns default on failure.
    """
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            v = float(value)
            return v if math.isfinite(v) else default
        s = str(value).strip()
        if not s or s.lower() in {"none", "nan", "null", "na", "n/a", "inf", "-inf"}:
            return default
        s = s.replace("%", "").replace(" ", "")
        # Norwegian decimal comma. If both comma and dot exist, assume comma is thousands separator.
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
        v = float(s)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _clamp(value: Any, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi], converting safely to float."""
    try:
        v = _safe_float(value, lo)
        return max(lo, min(hi, v))
    except Exception:
        return lo


def _now_iso() -> str:
    """UTC timestamp in ISO-8601 seconds format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def using_postgres() -> bool:
    """Return True when a Postgres database URL is configured."""
    url: Optional[str] = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("RENDER_DATABASE_URL")
    return bool(url and str(url).lower().startswith(("postgres://", "postgresql://")))
