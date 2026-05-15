"""v18.5.89 UI/Data Trust helpers.

Dependency-light helpers for consistent status labels, data quality and
blocking explanations. No Streamlit imports here; UI layers can render the
returned dictionaries however they prefer.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

DATA_QUALITY_LEVELS = ("LIVE", "CACHED", "FALLBACK", "PARTIAL", "STALE", "MISSING")

STATUS_LABELS = {
    "LIVE": "Live data",
    "CACHED": "Cache-data",
    "FALLBACK": "Fallback-data",
    "PARTIAL": "Delvis data",
    "STALE": "Utdatert data",
    "MISSING": "Mangler data",
}

STATUS_NOTES = {
    "LIVE": "Datagrunnlaget ser oppdatert ut.",
    "CACHED": "Analysen kan være basert på mellomlagrede data.",
    "FALLBACK": "En fallback-kilde eller beregning er brukt.",
    "PARTIAL": "Noen datakilder mangler eller er ufullstendige.",
    "STALE": "Dataene kan være eldre enn ønsket.",
    "MISSING": "Vesentlige data mangler; resultatet bør ikke tolkes som komplett.",
}

@dataclass(frozen=True)
class DataTrustStatus:
    level: str
    label: str
    note: str
    confidence: Optional[int] = None
    age_minutes: Optional[int] = None
    warnings: tuple[str, ...] = ()


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def age_minutes(updated_at: Any, now: Optional[datetime] = None) -> Optional[int]:
    ts = _parse_timestamp(updated_at)
    if ts is None:
        return None
    now = now or datetime.now(ts.tzinfo or timezone.utc)
    if ts.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    try:
        return max(0, int((now - ts).total_seconds() // 60))
    except Exception:
        return None


def normalize_data_trust(item: Optional[Dict[str, Any]] = None, *, default_level: str = "LIVE", stale_after_minutes: int = 60) -> Dict[str, Any]:
    """Return a normalized data-quality status for UI badges and audit notes."""
    item = item or {}
    explicit = str(
        item.get("data_quality")
        or item.get("data_status")
        or item.get("source_status")
        or item.get("quality")
        or default_level
    ).upper()
    level = explicit if explicit in DATA_QUALITY_LEVELS else str(default_level or "LIVE").upper()
    warnings: List[str] = []

    if item.get("error") or item.get("data_error"):
        level = "PARTIAL" if level == "LIVE" else level
        warnings.append(str(item.get("error") or item.get("data_error"))[:160])
    if item.get("fallback_used") or item.get("using_fallback"):
        level = "FALLBACK"
        warnings.append("Fallback brukt")
    if item.get("missing_data") or item.get("missing_fields"):
        level = "PARTIAL" if level not in {"MISSING", "FALLBACK"} else level
        missing = item.get("missing_data") or item.get("missing_fields")
        if isinstance(missing, (list, tuple, set)):
            warnings.append("Mangler: " + ", ".join(map(str, list(missing)[:5])))
        else:
            warnings.append("Mangler data")

    updated_at = item.get("updated_at") or item.get("last_updated") or item.get("timestamp") or item.get("ts")
    mins = age_minutes(updated_at)
    if mins is not None and mins > int(stale_after_minutes or 60) and level in {"LIVE", "CACHED"}:
        level = "STALE"
        warnings.append(f"Data er {mins} min gammel")

    confidence = _as_int(item.get("confidence"), None)
    status = DataTrustStatus(
        level=level,
        label=STATUS_LABELS.get(level, level),
        note=STATUS_NOTES.get(level, "Datastatus ukjent."),
        confidence=confidence,
        age_minutes=mins,
        warnings=tuple(warnings),
    )
    return asdict(status)


def format_data_trust_line(item: Optional[Dict[str, Any]] = None) -> str:
    status = normalize_data_trust(item)
    bits = [status["label"]]
    if status.get("confidence") is not None:
        bits.append(f"Confidence {status['confidence']}%")
    if status.get("age_minutes") is not None:
        bits.append(f"{status['age_minutes']} min gammel")
    if status.get("warnings"):
        bits.append("; ".join(status["warnings"][:2]))
    return " · ".join(bits)


def explain_blocked_action(reasons: Iterable[Any], *, action: str = "Kjøp") -> str:
    clean = [str(r).strip() for r in reasons if str(r or "").strip()]
    if not clean:
        return f"{action} blokkert: ukjent årsak."
    if len(clean) == 1:
        return f"{action} blokkert: {clean[0]}"
    return f"{action} blokkert: " + "; ".join(clean)


def ui_consistency_tokens() -> Dict[str, Any]:
    return {
        "button_height_px": 38,
        "standard_gap_px": 8,
        "status_min_height_px": 28,
        "toast_policy": "global_non_blocking",
        "button_states": ["idle", "loading", "disabled", "success", "blocked"],
    }
