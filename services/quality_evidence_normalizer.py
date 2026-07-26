"""Canonical quality-evidence normalisation for v19.11.0.

The normaliser converts heterogeneous source values to an explicit 0-100
contract and, crucially, distinguishes missing, invalid and genuinely weak
evidence. Raw volume is never treated as an already-normalised liquidity score.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

QUALITY_EVIDENCE_NORMALIZER_VERSION = "1.0"

STATUS_AVAILABLE = "AVAILABLE"
STATUS_MISSING = "MISSING"
STATUS_INVALID = "INVALID"
STATUS_BELOW_THRESHOLD = "BELOW_THRESHOLD"
STATUS_PASS = "PASS"

_LEVEL_SCORES = {
    "VERY_STRONG": 92.0,
    "SVÆRT_STERK": 92.0,
    "STERK": 82.0,
    "STRONG": 82.0,
    "GOOD": 75.0,
    "GOD": 75.0,
    "MODERATE": 60.0,
    "MODERAT": 60.0,
    "NEUTRAL": 50.0,
    "NØYTRAL": 50.0,
    "LIMITED": 42.0,
    "BEGRENSET": 42.0,
    "WEAK": 28.0,
    "SVAK": 28.0,
    "CONFLICTING": 20.0,
    "KONFLIKT": 20.0,
    "ERROR": None,
    "KILDEFEIL": None,
    "NO_DATA": None,
    "INGEN_DATA": None,
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _mapping_value(value: Mapping[str, Any]) -> tuple[Any, str]:
    for key in ("score", "value", "confidence", "consensus_score", "quality_score", "liquidity_score"):
        if value.get(key) not in (None, ""):
            return value.get(key), key
    level = str(value.get("level") or value.get("status") or value.get("label") or "").strip().upper().replace(" ", "_")
    if level:
        return _LEVEL_SCORES.get(level), f"level:{level}"
    return None, "mapping_without_score"


def normalize_score(value: Any, *, source: str, allow_fraction: bool = True) -> dict[str, Any]:
    """Normalise a quality score while preserving why it was transformed."""
    raw = value
    extracted_from = "direct"
    if isinstance(value, Mapping):
        value, extracted_from = _mapping_value(value)
    if value in (None, ""):
        return {
            "status": STATUS_MISSING,
            "value": None,
            "raw_value": raw,
            "source": source,
            "normalised_from": extracted_from,
            "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
        }
    number = _finite(value)
    if number is None:
        return {
            "status": STATUS_INVALID,
            "value": None,
            "raw_value": raw,
            "source": source,
            "normalised_from": extracted_from,
            "reason": "not_numeric",
            "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
        }
    normalised_from = extracted_from
    if allow_fraction and 0.0 <= number <= 1.0:
        number *= 100.0
        normalised_from = f"{extracted_from}:fraction_0_1"
    elif number < 0.0 or number > 100.0:
        return {
            "status": STATUS_INVALID,
            "value": None,
            "raw_value": raw,
            "source": source,
            "normalised_from": extracted_from,
            "reason": "outside_0_100",
            "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
        }
    return {
        "status": STATUS_AVAILABLE,
        "value": round(_clamp(number), 3),
        "raw_value": raw,
        "source": source,
        "normalised_from": normalised_from,
        "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
    }


def liquidity_score_from_turnover(*, average_volume: Any, price: Any, source: str = "average_volume_x_price") -> dict[str, Any]:
    volume = _finite(average_volume)
    price_value = _finite(price)
    if volume is None or volume <= 0 or price_value is None or price_value <= 0:
        return {
            "status": STATUS_MISSING,
            "value": None,
            "raw_value": {"average_volume": average_volume, "price": price},
            "source": source,
            "normalised_from": "turnover_unavailable",
            "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
        }
    turnover = volume * price_value
    # Logarithmic mapping: roughly 100k/day -> 10, 1m -> 35,
    # 10m -> 60, 100m -> 85 and 400m+ -> 100.
    score = _clamp((math.log10(max(turnover, 1.0)) - 4.6) * 25.0)
    return {
        "status": STATUS_AVAILABLE,
        "value": round(score, 3),
        "raw_value": {"average_volume": round(volume, 3), "price": round(price_value, 6), "turnover": round(turnover, 3)},
        "source": source,
        "normalised_from": "log10_daily_turnover",
        "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
    }


def classify_threshold(component: Mapping[str, Any], threshold: float | None) -> dict[str, Any]:
    row = dict(component or {})
    row["threshold"] = threshold
    status = str(row.get("status") or STATUS_MISSING)
    value = _finite(row.get("value"))
    if status in {STATUS_MISSING, STATUS_INVALID} or value is None or threshold is None:
        row["threshold_status"] = status
    elif value < float(threshold):
        row["threshold_status"] = STATUS_BELOW_THRESHOLD
    else:
        row["threshold_status"] = STATUS_PASS
    return row


def source_consensus_score(value: Any, *, source: str = "source_consensus") -> dict[str, Any]:
    if isinstance(value, Mapping):
        direct = normalize_score(value, source=source)
        if direct["status"] == STATUS_AVAILABLE:
            return direct
        independent = _finite(value.get("independent_sources"))
        primary = bool(value.get("primary_source_present"))
        level = str(value.get("level") or "").strip().upper().replace(" ", "_")
        level_score = _LEVEL_SCORES.get(level)
        parts: list[float] = []
        if level_score is not None:
            parts.append(float(level_score))
        if independent is not None:
            parts.append(_clamp(20.0 + min(independent, 4.0) * 18.0))
        if parts:
            score = sum(parts) / len(parts) + (5.0 if primary else 0.0)
            return {
                "status": STATUS_AVAILABLE,
                "value": round(_clamp(score), 3),
                "raw_value": dict(value),
                "source": source,
                "normalised_from": "structured_consensus",
                "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
            }
    return normalize_score(value, source=source)


def freshness_score(timestamp: Any, *, captured_at: Any = None, source: str = "data_timestamp") -> dict[str, Any]:
    if not timestamp:
        return normalize_score(None, source=source)
    try:
        observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        reference = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00")) if captured_at else datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (reference - observed).total_seconds() / 86400.0)
        if age_days <= 3:
            score = 100.0
        elif age_days <= 7:
            score = 85.0
        elif age_days <= 14:
            score = 65.0
        elif age_days <= 30:
            score = 45.0
        else:
            score = 20.0
        return {
            "status": STATUS_AVAILABLE,
            "value": score,
            "raw_value": str(timestamp),
            "source": source,
            "normalised_from": "age_days",
            "age_days": round(age_days, 3),
            "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
        }
    except Exception:
        return {
            "status": STATUS_INVALID,
            "value": None,
            "raw_value": timestamp,
            "source": source,
            "normalised_from": "timestamp_parse",
            "reason": "invalid_timestamp",
            "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
        }


def coverage_summary(components: Mapping[str, Mapping[str, Any]], *, critical: tuple[str, ...] = ("data_quality", "liquidity", "source_consensus"), minimum_components: int = 2) -> dict[str, Any]:
    rows = {str(name): dict(value or {}) for name, value in dict(components or {}).items()}
    available = [name for name, row in rows.items() if row.get("status") == STATUS_AVAILABLE and row.get("value") is not None]
    missing = [name for name, row in rows.items() if row.get("status") == STATUS_MISSING]
    invalid = [name for name, row in rows.items() if row.get("status") == STATUS_INVALID]
    available_critical = [name for name in critical if name in available]
    sufficient = len(available) >= int(minimum_components) and len(available_critical) >= min(2, len(critical))
    return {
        "available_components": len(available),
        "available_component_names": available,
        "missing_components": missing,
        "invalid_components": invalid,
        "available_critical_components": len(available_critical),
        "critical_component_names": list(critical),
        "minimum_components": int(minimum_components),
        "sufficient_evidence": bool(sufficient),
        "normalizer_version": QUALITY_EVIDENCE_NORMALIZER_VERSION,
    }
