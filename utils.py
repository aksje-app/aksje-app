"""Shared utility helpers for AI Aksje Analyzer.

v18.6.3: single source of truth for common conversions, clamping,
UTC timestamps and Postgres availability checks.  These helpers replace
many drifted copies across the codebase.
"""
from __future__ import annotations
from utils import _safe_float, _now_iso, _clamp, using_postgres  # v18.6.3 centralized helpers

import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None








