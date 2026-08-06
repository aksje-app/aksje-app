"""Immutable, fail-closed Autonomy replay snapshots.

The contract captures every input needed by the portfolio decision gateway and
separately records the actions actually committed by the Autonomy cycle.  A
snapshot is FULL_REPLAY only after checksums, offline decision reproduction and
portfolio/action reconciliation all pass.  No missing value is synthesized.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app_version import APP_VERSION, AUTONOMY_POLICY_VERSION, RANKING_MODEL_VERSION
from durable_runtime import read_json as durable_read_json, write_json as durable_write_json
from storage_architecture import runtime_data_path


SCHEMA_VERSION = "2.0"
CONTRACT = "AI_AKSJE_ANALYZER_FULL_REPLAY"
ROOT = runtime_data_path("full_replay")
INDEX_PATH = ROOT / "index.json"
INDEX_KEY = "full_replay/index.json"
REQUIRED_FILES = (
    "configuration.json",
    "portfolio_before.json",
    "market_snapshot.json",
    "evidence_snapshot.json",
    "candidates_input.json",
    "decision_trace.json",
    "actions.json",
    "portfolio_after.json",
)


def _stable_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_id(value: Any) -> str:
    text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "")).strip("._")
    if not text:
        raise ValueError("run_id mangler")
    return text


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _evidence_snapshot(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in candidates:
        raw = source.get("raw") if isinstance(source.get("raw"), Mapping) else {}
        rows.append({
            "ticker": source.get("ticker"),
            "valid_for_decision": source.get("valid_for_decision"),
            "evidence_valid_for_decision": source.get("evidence_valid_for_decision"),
            "evidence_status": source.get("evidence_status"),
            "data_contract": copy.deepcopy(source.get("data_contract") or {}),
            "source_provenance": copy.deepcopy(source.get("source_provenance") or raw.get("source_provenance") or {}),
            "news_evidence": copy.deepcopy(source.get("news_evidence") or raw.get("news_evidence") or []),
            "insider_evidence": copy.deepcopy(source.get("insider_evidence") or raw.get("insider_evidence") or []),
        })
    return rows


def _decision_input(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the complete candidate; the decision gateway may use nested raw data."""
    return copy.deepcopy(dict(candidate))


def replay_decisions(candidates: Sequence[Mapping[str, Any]], portfolio_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Run the production decision gateway offline against frozen input."""
    from autonomi_core.portfolio_decisions.layer import assess_candidate

    results: list[dict[str, Any]] = []
    for source in candidates:
        candidate = _decision_input(source)
        decision = assess_candidate(candidate, copy.deepcopy(dict(portfolio_context)))
        results.append({
            "ticker": decision.get("ticker"),
            "action": decision.get("action"),
            "first_blocker_code": decision.get("first_blocker_code") or "",
            "blocker_codes": list(decision.get("blocker_codes") or []),
            "gates": copy.deepcopy(decision.get("gates") or {}),
            "thresholds": copy.deepcopy(decision.get("thresholds") or {}),
            "position_size": copy.deepcopy(decision.get("position_size") or {}),
        })
    return results


def build_snapshot(
    *,
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    portfolio_before: Mapping[str, Any],
    portfolio_after: Mapping[str, Any],
    portfolio_context: Mapping[str, Any],
    parameters: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a complete in-memory contract and prove it before persistence."""
    rid = _safe_id(run_id)
    clean_candidates = [_decision_input(row) for row in candidates if isinstance(row, Mapping)]
    files: dict[str, Any] = {
        "configuration.json": {
            "app_version": APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "autonomy_policy_version": AUTONOMY_POLICY_VERSION,
            "ranking_model_version": RANKING_MODEL_VERSION,
            "parameters": copy.deepcopy(dict(parameters)),
            "portfolio_context": copy.deepcopy(dict(portfolio_context)),
            "network_allowed_during_replay": False,
            "production_writes_allowed_during_replay": False,
        },
        "portfolio_before.json": copy.deepcopy(dict(portfolio_before)),
        "market_snapshot.json": copy.deepcopy(dict(market_snapshot)),
        "evidence_snapshot.json": _evidence_snapshot(clean_candidates),
        "candidates_input.json": clean_candidates,
        "decision_trace.json": replay_decisions(clean_candidates, portfolio_context),
        "actions.json": [copy.deepcopy(dict(row)) for row in actions if isinstance(row, Mapping)],
        "portfolio_after.json": copy.deepcopy(dict(portfolio_after)),
    }
    hashes = {name: _sha256(_stable_bytes(payload)) for name, payload in files.items()}
    manifest = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "run_id": rid,
        "created_at": _now(),
        "app_version": APP_VERSION,
        "required_files": list(REQUIRED_FILES),
        "hashes": hashes,
        "immutable": True,
        "offline": True,
        "learning_mode": "OBSERVE",
        "production_parameters_changed": False,
    }
    bundle = {"manifest": manifest, "files": files}
    audit = audit_snapshot(bundle, rerun=True)
    manifest["audit"] = audit
    manifest["replay_level"] = "FULL_REPLAY" if audit["ok"] else "DECISION_REPLAY"
    return bundle


def _action_integrity(actions: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_ticker: dict[str, set[str]] = {}
    for row in actions:
        ticker = str(row.get("ticker") or "").upper()
        action = str(row.get("action") or "").upper()
        if ticker and action in {"BUY", "SELL"}:
            by_ticker.setdefault(ticker, set()).add(action)
        if action in {"BUY", "SELL"} and not row.get("run_id"):
            errors.append("ACTION_RUN_ID_MISSING")
    if any({"BUY", "SELL"}.issubset(values) for values in by_ticker.values()):
        errors.append("SAME_TICKER_BOUGHT_AND_SOLD")
    return errors


def _portfolio_reconciliation(files: Mapping[str, Any]) -> list[str]:
    before = files.get("portfolio_before.json") or {}
    after = files.get("portfolio_after.json") or {}
    actions = files.get("actions.json") or []
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return ["PORTFOLIO_SNAPSHOT_INVALID"]
    errors: list[str] = []
    try:
        expected_cash = float(before.get("cash") or 0.0)
        before_positions = set((before.get("positions") or {}).keys())
        expected_positions = set(before_positions)
        for row in actions:
            action = str(row.get("action") or "").upper()
            ticker = str(row.get("ticker") or "").upper()
            value = float(row.get("value") or 0.0)
            if action == "BUY":
                expected_cash -= value
                expected_positions.add(ticker)
            elif action == "SELL":
                expected_cash += value
                expected_positions.discard(ticker)
        actual_cash = float(after.get("cash") or 0.0)
        if abs(expected_cash - actual_cash) > 0.02:
            errors.append("PORTFOLIO_CASH_RECONCILIATION_FAILED")
        actual_positions = {str(key).upper() for key in (after.get("positions") or {}).keys()}
        if expected_positions != actual_positions:
            errors.append("PORTFOLIO_POSITION_RECONCILIATION_FAILED")
    except (TypeError, ValueError):
        errors.append("PORTFOLIO_RECONCILIATION_ERROR")
    return errors


def audit_snapshot(bundle: Mapping[str, Any], *, rerun: bool = True) -> dict[str, Any]:
    manifest = dict(bundle.get("manifest") or {})
    files = dict(bundle.get("files") or {})
    missing = [name for name in REQUIRED_FILES if name not in files]
    errors = [f"MISSING:{name}" for name in missing]
    if manifest.get("contract") != CONTRACT:
        errors.append("CONTRACT_INVALID")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION_INVALID")
    for name in REQUIRED_FILES:
        if name in files and str((manifest.get("hashes") or {}).get(name) or "") != _sha256(_stable_bytes(files[name])):
            errors.append(f"CHECKSUM_MISMATCH:{name}")
    candidates = files.get("candidates_input.json") or []
    config = files.get("configuration.json") or {}
    context = config.get("portfolio_context") if isinstance(config, Mapping) else {}
    expected = files.get("decision_trace.json") or []
    if not candidates:
        errors.append("CANDIDATES_MISSING")
    required_candidate_fields = (
        "ticker", "investment_score", "risk_score", "liquidity_score",
        "valid_for_decision", "evidence_valid_for_decision", "mission_eligible", "strategy_matches",
    )
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            errors.append(f"CANDIDATE_INVALID:{index}")
            continue
        for field in required_candidate_fields:
            if candidate.get(field) is None:
                errors.append(f"CANDIDATE_FIELD_MISSING:{index}:{field}")
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        if candidate.get("price") is None and raw.get("current_price") is None and raw.get("regularMarketPrice") is None:
            errors.append(f"CANDIDATE_FIELD_MISSING:{index}:price")
        if candidate.get("data_quality") is None and candidate.get("data_quality_score") is None and not candidate.get("data_contract"):
            errors.append(f"CANDIDATE_FIELD_MISSING:{index}:data_quality")
    if not isinstance(context, Mapping) or not context or not context.get("limits"):
        errors.append("PORTFOLIO_CONTEXT_INCOMPLETE")
    if not isinstance(config, Mapping) or not config.get("parameters"):
        errors.append("CONFIGURATION_INCOMPLETE")
    market = files.get("market_snapshot.json") or {}
    if not isinstance(market, Mapping) or not market.get("snapshot_id"):
        errors.append("MARKET_SNAPSHOT_INCOMPLETE")
    if rerun and not errors:
        try:
            actual = replay_decisions(candidates, context)
            if _stable_bytes(actual) != _stable_bytes(expected):
                errors.append("DECISION_REPLAY_MISMATCH")
        except Exception as exc:
            errors.append(f"REPLAY_ERROR:{type(exc).__name__}")
    errors.extend(_action_integrity(files.get("actions.json") or []))
    errors.extend(_portfolio_reconciliation(files))
    return {
        "ok": not errors,
        "errors": sorted(set(errors)),
        "missing": missing,
        "checksums_verified": not any(item.startswith("CHECKSUM_MISMATCH") for item in errors),
        "decision_replay_verified": rerun and "DECISION_REPLAY_MISMATCH" not in errors and not any(item.startswith("REPLAY_ERROR") for item in errors),
        "action_integrity_verified": not any(item in {"ACTION_RUN_ID_MISSING", "SAME_TICKER_BOUGHT_AND_SOLD"} for item in errors),
        "portfolio_reconciliation_verified": not any(item.startswith("PORTFOLIO_") for item in errors),
        "network_calls": False,
        "production_writes": False,
    }


def persist_snapshot(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Persist once. Identical retries are accepted; conflicts fail closed."""
    manifest = dict(bundle.get("manifest") or {})
    files = dict(bundle.get("files") or {})
    run_id = _safe_id(manifest.get("run_id"))
    target = ROOT / run_id
    existing_manifest = target / "run_manifest.json"
    manifest_key = f"full_replay/{run_id}/run_manifest.json"
    existing = durable_read_json(manifest_key, existing_manifest, {})
    if isinstance(existing, Mapping) and existing:
        if existing.get("hashes") != manifest.get("hashes"):
            raise RuntimeError(f"Replaykonflikt for {run_id}; eksisterende snapshot er uforanderlig")
        return {"stored": False, "reused": True, "path": str(target), "manifest": existing}
    target.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        durable_write_json(f"full_replay/{run_id}/{name}", target / name, files[name])
    durable_write_json(manifest_key, existing_manifest, manifest)
    loaded = load_snapshot(run_id)
    audit = audit_snapshot(loaded, rerun=True)
    if not audit["ok"]:
        raise RuntimeError("Replay-snapshot feilet kontroll etter lagring: " + "; ".join(audit["errors"]))
    index = durable_read_json(INDEX_KEY, INDEX_PATH, [])
    rows = [dict(row) for row in index if isinstance(row, Mapping)] if isinstance(index, list) else []
    if not any(str(row.get("run_id")) == run_id for row in rows):
        rows.insert(0, {
            "run_id": run_id,
            "created_at": manifest.get("created_at"),
            "replay_level": manifest.get("replay_level"),
            "schema_version": manifest.get("schema_version"),
        })
        durable_write_json(INDEX_KEY, INDEX_PATH, rows[:10000])
    return {"stored": True, "reused": False, "path": str(target), "manifest": manifest, "audit": audit}


def load_snapshot(run_id: str) -> dict[str, Any]:
    rid = _safe_id(run_id)
    target = ROOT / rid
    manifest = durable_read_json(f"full_replay/{rid}/run_manifest.json", target / "run_manifest.json", {})
    if not isinstance(manifest, Mapping) or not manifest:
        raise FileNotFoundError(f"Replaymanifest mangler for {rid}")
    files = {}
    for name in REQUIRED_FILES:
        value = durable_read_json(f"full_replay/{rid}/{name}", target / name, None)
        if value is not None:
            files[name] = value
    return {"manifest": manifest, "files": files}


def classify_snapshot(run_id: str) -> tuple[str, list[str]]:
    try:
        audit = audit_snapshot(load_snapshot(run_id), rerun=True)
    except FileNotFoundError:
        return "DECISION_REPLAY", ["FULL_REPLAY_SNAPSHOT_MISSING"]
    except Exception as exc:
        return "DECISION_REPLAY", [f"FULL_REPLAY_SNAPSHOT_ERROR:{type(exc).__name__}"]
    return ("FULL_REPLAY", []) if audit["ok"] else ("DECISION_REPLAY", list(audit["errors"]))


def list_snapshot_ids() -> list[str]:
    rows = durable_read_json(INDEX_KEY, INDEX_PATH, [])
    return [str(row.get("run_id")) for row in rows if isinstance(row, Mapping) and row.get("run_id")] if isinstance(rows, list) else []


__all__ = [
    "SCHEMA_VERSION", "CONTRACT", "REQUIRED_FILES", "build_snapshot", "persist_snapshot",
    "load_snapshot", "audit_snapshot", "classify_snapshot", "list_snapshot_ids", "replay_decisions",
]
