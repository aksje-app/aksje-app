"""Safe, read-only handoff from the proven Paper scanner to Autonomi.

The bridge deliberately carries immutable technical observations and strategy
decisions only.  It never changes a candidate score, portfolio action, order
permission or trading threshold.  That makes Paper usable as an input and
benchmark while the two execution paths are compared before any retirement.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any, Mapping, Sequence

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path


BRIDGE_KEY = "autonomi_core/paper_engine_handoff/latest.json"
BRIDGE_PATH = runtime_data_path("autonomi_core", "paper_engine_handoff", "latest.json")
BRIDGE_SCHEMA_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _checksum(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def publish_paper_engine_handoff(
    *,
    run_id: str,
    market_snapshot: Mapping[str, Any],
    parallel_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = dict(market_snapshot or {})
    decisions = [
        dict(row) for row in list((parallel_result or {}).get("decisions") or [])
        if isinstance(row, Mapping)
    ]
    technical_by_ticker: dict[str, list[dict[str, Any]]] = {}
    autonomy_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for decision in decisions:
        ticker = str(decision.get("ticker") or "").strip().upper()
        family = str(decision.get("strategy_family") or "").strip().lower()
        if not ticker:
            continue
        compact = {
            key: decision.get(key) for key in (
                "decision_id", "strategy_family", "strategy_id", "strategy_version_id",
                "action", "raw_decision", "score", "confidence", "reasons", "blockers",
                "candidate_snapshot_id", "snapshot_checksum", "evaluated_at",
                "execution_authorized", "error",
            ) if key in decision
        }
        target = autonomy_by_ticker if family == "autonomy" else technical_by_ticker if family == "technical" else None
        if target is not None:
            target.setdefault(ticker, []).append(compact)

    candidates: dict[str, dict[str, Any]] = {}
    for candidate in list(snapshot.get("candidates") or []):
        if not isinstance(candidate, Mapping):
            continue
        ticker = str(candidate.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        candidates[ticker] = {
            "ticker": ticker,
            "market_snapshot_id": snapshot.get("snapshot_id"),
            "candidate_snapshot_id": candidate.get("candidate_snapshot_id"),
            "snapshot_checksum": candidate.get("checksum"),
            "captured_at": candidate.get("captured_at") or snapshot.get("captured_at"),
            "price": candidate.get("price"),
            "technical": dict(candidate.get("technical") or {}),
            "technical_decisions": technical_by_ticker.get(ticker, []),
            "autonomy_shadow_decisions": autonomy_by_ticker.get(ticker, []),
            "source": "paper_scanner",
            "execution_authorized": False,
        }

    body = {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "run_id": str(run_id or snapshot.get("run_id") or ""),
        "published_at": _now(),
        "market_snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "market_snapshot_checksum": str(snapshot.get("checksum") or ""),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "mode": "OBSERVATIONAL_INPUT_ONLY",
        "score_mutation_allowed": False,
        "order_execution_allowed": False,
    }
    body["checksum"] = _checksum(body)
    write_json(BRIDGE_KEY, BRIDGE_PATH, body)
    return body


def load_paper_engine_handoff(*, max_age_minutes: int | None = None) -> dict[str, Any]:
    value = read_json(BRIDGE_KEY, BRIDGE_PATH, {})
    handoff = dict(value) if isinstance(value, Mapping) else {}
    checksum = str(handoff.pop("checksum", "") or "")
    if not handoff or not checksum or _checksum(handoff) != checksum:
        return {"available": False, "reason": "MISSING_OR_INVALID_CHECKSUM", "candidates": {}}
    handoff["checksum"] = checksum
    raw_limit = max_age_minutes if max_age_minutes is not None else os.getenv("PAPER_AUTONOMY_INPUT_MAX_AGE_MINUTES", "1440")
    try:
        limit = max(15, int(raw_limit))
        published = datetime.fromisoformat(str(handoff.get("published_at") or "").replace("Z", "+00:00"))
        published = published.replace(tzinfo=published.tzinfo or timezone.utc).astimezone(timezone.utc)
        age_minutes = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 60.0)
    except Exception:
        return {"available": False, "reason": "INVALID_TIMESTAMP", "candidates": {}}
    if age_minutes > limit:
        return {**handoff, "available": False, "reason": "STALE", "age_minutes": round(age_minutes, 1), "candidates": {}}
    return {**handoff, "available": True, "reason": "OK", "age_minutes": round(age_minutes, 1)}


def attach_paper_engine_inputs(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    handoff = load_paper_engine_handoff()
    inputs = dict(handoff.get("candidates") or {}) if handoff.get("available") else {}
    matched = 0
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        ticker = str(candidate.get("ticker") or "").strip().upper()
        bridge_input = inputs.get(ticker)
        if bridge_input:
            candidate["paper_engine_input"] = dict(bridge_input)
            matched += 1
    return {
        "available": bool(handoff.get("available")),
        "reason": handoff.get("reason"),
        "source_run_id": handoff.get("run_id"),
        "market_snapshot_id": handoff.get("market_snapshot_id"),
        "published_at": handoff.get("published_at"),
        "age_minutes": handoff.get("age_minutes"),
        "input_candidates": len(inputs),
        "matched_candidates": matched,
        "mode": "OBSERVATIONAL_INPUT_ONLY",
        "score_mutation_allowed": False,
        "order_execution_allowed": False,
    }


__all__ = [
    "attach_paper_engine_inputs", "load_paper_engine_handoff",
    "publish_paper_engine_handoff", "BRIDGE_SCHEMA_VERSION",
]
