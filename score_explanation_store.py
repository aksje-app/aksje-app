"""
score_explanation_store.py

Persistent score explanations for Testing & Learning.

Purpose:
- Keep score explanations after a Streamlit/session restart.
- Store both latest explanation per ticker and a compact historical JSONL log.
- Prefer StorageService/Postgres on Render with local fallback through StorageService.

No trading/order execution is connected here.
"""

from __future__ import annotations
import logging
from utils import _now_iso  # v18.6.3 centralized helpers

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence




def _safe_ticker(ticker: str) -> str:
    return "".join(ch for ch in str(ticker or "").upper() if ch.isalnum() or ch in ".-_")[:24] or "UNKNOWN"


def _storage():
    try:
        from services.storage_service import get_storage_service

        return get_storage_service()
    except Exception:
        return None


def _storage_name(name: str) -> str:
    return f"score_explanations/{name}"


def _get_any(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    # Case-insensitive fallback for dataframes/translated UI rows.
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        lk = str(key).lower()
        if lk in lowered and lowered[lk] is not None:
            return lowered[lk]
    return default


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _compact_raw(row: Mapping[str, Any]) -> Dict[str, Any]:
    keep = [
        "ticker", "symbol", "name", "score", "ai_score", "smart_score", "strength", "risk",
        "confidence", "action", "recommendation", "sector", "reason", "note", "score_parts",
        "forecast_strength", "forecast_strength_label",
        "Ticker", "AI-score", "Smart-score", "Strength", "Risiko", "Forklaring", "Kilde",
    ]
    return {k: row.get(k) for k in keep if k in row}


def _fingerprint(payload: Mapping[str, Any]) -> str:
    comparable = {
        k: v for k, v in payload.items()
        if k not in {"stored_at", "updated_at", "raw", "_fingerprint"}
    }
    blob = json.dumps(comparable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


def normalize_score_explanation(
    row: Mapping[str, Any],
    *,
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize score/ranking rows from app services or UI into one persistent shape."""
    if not isinstance(row, Mapping):
        return None

    t = ticker or _get_any(row, ["ticker", "symbol", "Ticker"])
    t_safe = _safe_ticker(str(t or ""))
    if not t_safe or t_safe == "UNKNOWN":
        return None

    explanation = _get_any(row, ["reason", "note", "explanation", "Forklaring"], "")
    if explanation is None:
        explanation = ""

    payload: Dict[str, Any] = {
        "ticker": t_safe,
        "source": source or str(_get_any(row, ["source", "Kilde"], "Score")),
        "ai_score": _to_float(_get_any(row, ["ai_score", "score", "AI-score"])),
        "smart_score": _to_float(_get_any(row, ["smart_score", "Smart-score"])),
        "strength": _to_float(_get_any(row, ["strength", "Strength", "forecast_strength"])),
        "risk": _get_any(row, ["risk", "Risiko"], ""),
        "confidence": _to_float(_get_any(row, ["confidence", "Confidence"])),
        "action": _get_any(row, ["action", "recommendation", "Anbefaling"], ""),
        "sector": _get_any(row, ["sector", "Sektor"], ""),
        "reason": str(explanation) if explanation else "-",
        "score_parts": _get_any(row, ["score_parts", "parts", "components"], {}) or {},
        "context": dict(context or {}),
        "raw": _compact_raw(row),
    }
    payload["_fingerprint"] = _fingerprint(payload)
    payload["stored_at"] = _now_iso()
    return payload


def save_score_explanation(
    row: Mapping[str, Any],
    *,
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    storage: Any = None,
) -> Optional[Dict[str, Any]]:
    """Persist a normalized score explanation.

    The latest per ticker keeps the last 50 distinct fingerprints. The history
    JSONL only appends when a new distinct explanation appears, avoiding a new
    duplicate record on every Streamlit rerender.
    """
    payload = normalize_score_explanation(row, ticker=ticker, source=source, context=context)
    if not payload:
        return None

    storage = storage or _storage()
    if storage is None:
        return None

    t_safe = _safe_ticker(payload["ticker"])
    latest_key = _storage_name(f"latest_{t_safe}.json")
    history_key = _storage_name("history.jsonl")

    latest_rows = storage.read_json(latest_key, default=[])
    if not isinstance(latest_rows, list):
        latest_rows = []

    existing_fps = {str(r.get("_fingerprint")) for r in latest_rows if isinstance(r, Mapping)}
    is_new = payload.get("_fingerprint") not in existing_fps

    if is_new:
        latest_rows.insert(0, payload)
        latest_rows = latest_rows[:50]
        try:
            storage.append_jsonl(history_key, payload)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    else:
        # Keep the latest slot fresh without growing history.
        latest_rows = [dict(r) for r in latest_rows if isinstance(r, Mapping)]
        for idx, existing in enumerate(latest_rows):
            if existing.get("_fingerprint") == payload.get("_fingerprint"):
                existing["updated_at"] = payload["stored_at"]
                latest_rows[idx] = existing
                break

    try:
        storage.write_json(latest_key, latest_rows)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return payload


def capture_score_explanations(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    storage: Any = None,
) -> List[Dict[str, Any]]:
    saved: List[Dict[str, Any]] = []
    storage = storage or _storage()
    if storage is None:
        return saved
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        payload = save_score_explanation(row, source=source, context=context, storage=storage)
        if payload:
            saved.append(payload)
    return saved


def load_latest_score_explanations(ticker: str, *, limit: int = 20, storage: Any = None) -> List[Dict[str, Any]]:
    storage = storage or _storage()
    if storage is None:
        return []
    t_safe = _safe_ticker(ticker)
    latest_key = _storage_name(f"latest_{t_safe}.json")
    rows = storage.read_json(latest_key, default=[])
    if isinstance(rows, list) and rows:
        return [dict(r) for r in rows[:limit] if isinstance(r, Mapping)]

    # Fallback to history if latest file was not present.
    history = storage.read_jsonl(_storage_name("history.jsonl"), limit=max(limit * 10, 100))
    filtered = [dict(r) for r in reversed(history) if isinstance(r, Mapping) and _safe_ticker(str(r.get("ticker", ""))) == t_safe]
    return filtered[:limit]


def load_score_explanation_history(*, limit: int = 200, storage: Any = None) -> List[Dict[str, Any]]:
    storage = storage or _storage()
    if storage is None:
        return []
    rows = storage.read_jsonl(_storage_name("history.jsonl"), limit=limit)
    return [dict(r) for r in rows if isinstance(r, Mapping)]


def score_explanations_for_ui(ticker: str, *, limit: int = 20, storage: Any = None) -> List[Dict[str, Any]]:
    """Return persistent explanations formatted for the Norwegian Streamlit table."""
    rows = []
    for r in load_latest_score_explanations(ticker, limit=limit, storage=storage):
        rows.append({
            "Kilde": r.get("source") or "Lagret score",
            "Ticker": r.get("ticker"),
            "AI-score": r.get("ai_score"),
            "Smart-score": r.get("smart_score"),
            "Strength": r.get("strength"),
            "Risiko": r.get("risk"),
            "Confidence": r.get("confidence"),
            "Anbefaling": r.get("action"),
            "Forklaring": r.get("reason") or "-",
            "Lagret": r.get("stored_at") or r.get("updated_at"),
        })
    return rows
