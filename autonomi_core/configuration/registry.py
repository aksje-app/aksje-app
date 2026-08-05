"""Central, versioned and governed operational configuration registry."""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping


REGISTRY_KEY = "autonomi_core/configuration_registry.json"
SCHEMA_VERSION = 1
ROOTS = ("autonomy", "discovery", "analysis", "portfolio", "learning", "runtime", "notifications", "reporting")
LEGACY_KEY_MAP = {
    "autonomi_core/policy.json": "autonomy.policy",
    "autonomi_core/interface_mode.json": "autonomy.interface",
    "autonomi_core/user_mission.json": "autonomy.last_user_mission",
    "autonomous_portfolio/parameters.json": "portfolio.parameters",
    "controlled_learning/state.json": "learning.settings",
    "market_intelligence/jobs.json": "runtime.scheduler.jobs",
    "market_intelligence/draft_job.json": "runtime.scheduler.draft",
    "adaptive_ranking/model_state.json": "analysis.adaptive_ranking.model_state",
}
SENSITIVE_PREFIXES = ("analysis.factor_weights", "portfolio.", "learning.", "runtime.execution")
_MIGRATING = False
_CACHE: dict[str, Any] | None = None
_CACHE_AT = 0.0
_CACHE_STORAGE_ID: int | None = None
_CACHE_TTL_SECONDS = max(1.0, float(os.getenv("CONFIG_READ_CACHE_SECONDS", "30") or 30))


def migration_in_progress() -> bool:
    return _MIGRATING


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _storage():
    from services.storage_service import get_storage_service
    return get_storage_service()


def _parts(path: str) -> list[str]:
    return [part for part in str(path or "").replace("/", ".").split(".") if part]


def _get(root: Mapping[str, Any], path: str, default: Any = None) -> Any:
    node: Any = root
    for part in _parts(path):
        if not isinstance(node, Mapping) or part not in node:
            return deepcopy(default)
        node = node[part]
    return deepcopy(node)


def _set(root: dict[str, Any], path: str, value: Any) -> None:
    parts = _parts(path)
    if not parts or parts[0] not in ROOTS:
        raise ValueError(f"Konfigurasjonssti må starte med ett av: {', '.join(ROOTS)}")
    node = root
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = deepcopy(value)


def _checksum(values: Mapping[str, Any]) -> str:
    raw = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _version(revision: int) -> str:
    return f"CFG-{max(0, int(revision)):06d}"


def _empty() -> dict[str, Any]:
    values = {root: {} for root in ROOTS}
    return {
        "schema_version": SCHEMA_VERSION, "revision": 0, "config_version": _version(0),
        "created_at": _now(), "updated_at": _now(), "values": values,
        "checksum": _checksum(values), "history": [], "versions": [], "approvals": [],
        "migration": {"complete": False, "sources": []},
    }


def validate_values(values: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(set(values) - set(ROOTS))
    if unknown:
        errors.append("Ukjente navnerom: " + ", ".join(unknown))
    numeric_rules = {
        "discovery.minimum_data_quality": (0, 100),
        "discovery.composition.documented_pct": (0, 100),
        "discovery.composition.new_pct": (0, 100),
        "discovery.composition.experimental_pct": (0, 100),
        "analysis.minimum_score": (0, 100),
        "portfolio.parameters.maximum_risk_score": (0, 100),
        "portfolio.parameters.maximum_position_pct": (0.1, 100),
        "portfolio.decision.max_country_pct": (1, 100),
        "portfolio.decision.max_currency_pct": (1, 100),
        "portfolio.decision.minimum_liquidity_score": (0, 100),
        "runtime.scan_limit": (1, 500),
        "reporting.candidate_count": (1, 250),
    }
    for path, (low, high) in numeric_rules.items():
        value = _get(values, path, None)
        if value is None:
            continue
        try:
            number = float(value)
            if number < low or number > high:
                errors.append(f"{path} må være mellom {low} og {high}")
        except (TypeError, ValueError):
            errors.append(f"{path} må være et tall")
    if _get(values, "autonomy.policy.theoretical_only", True) is False:
        errors.append("Autonomi må være teoretisk i denne versjonen")
    if _get(values, "learning.allow_automatic_model_approval", False) is True:
        errors.append("Automatisk modellgodkjenning er ikke tillatt")
    composition = _get(values, "discovery.composition", {})
    if isinstance(composition, Mapping) and composition:
        total = sum(float(composition.get(key, 0)) for key in ("documented_pct", "new_pct", "experimental_pct"))
        if total != 100:
            errors.append("discovery.composition må summere til 100")
    return errors


def _normalize(raw: Any) -> dict[str, Any]:
    doc = deepcopy(raw) if isinstance(raw, dict) else _empty()
    doc.setdefault("values", {})
    for root in ROOTS:
        doc["values"].setdefault(root, {})
    doc.setdefault("history", []); doc.setdefault("versions", []); doc.setdefault("approvals", [])
    doc.setdefault("migration", {"complete": False, "sources": []})
    doc["schema_version"] = SCHEMA_VERSION
    doc["revision"] = int(doc.get("revision") or 0)
    doc["config_version"] = str(doc.get("config_version") or _version(doc["revision"]))
    doc["checksum"] = _checksum(doc["values"])
    return doc


def _legacy_framework_value(framework: Mapping[str, Any], path: str) -> Any:
    return _get(framework.get("sections", {}), path, None)


def _migrate(doc: dict[str, Any]) -> dict[str, Any]:
    global _MIGRATING
    if doc.get("migration", {}).get("complete"):
        return doc
    storage = _storage()
    values = doc["values"]
    sources: list[str] = []
    framework = storage.read_json("configuration/framework.json", default={})
    mappings = {
        "autonomous_portfolio.parameters": "portfolio.parameters",
        "controlled_learning.state": "learning.settings",
        "market_intelligence.jobs": "runtime.scheduler.jobs",
        "legacy.autonomi_core.policy.json": "autonomy.policy",
        "legacy.autonomi_core.interface_mode.json": "autonomy.interface",
        "legacy.autonomi_core.user_mission.json": "autonomy.last_user_mission",
        "legacy.market_intelligence.draft_job.json": "runtime.scheduler.draft",
        "legacy.adaptive_ranking.model_state.json": "analysis.adaptive_ranking.model_state",
    }
    for old, new in mappings.items():
        value = _legacy_framework_value(framework, old) if isinstance(framework, Mapping) else None
        if value is not None and _get(values, new, None) is None:
            _set(values, new, value); sources.append(old)
    _MIGRATING = True
    try:
        from settings_store import load_settings
        settings = load_settings()
    except Exception:
        settings = {}
    finally:
        _MIGRATING = False
    if isinstance(settings, Mapping):
        groups = {
            "discovery.scanner": ("markets", "max_tickers_per_market", "scan_top_picks_only"),
            "analysis.signals": ("min_buy_confidence", "min_buy_score"),
            "portfolio.paper_trading": ("max_open_positions", "max_trades_per_day", "position_size_pct"),
            "runtime.scanner": ("scan_interval_minutes", "background_scanning_enabled", "vacation_mode_enabled"),
            "notifications": ("pushover_enabled", "notify_paper_trades", "notify_watchlist_signal_changes", "notify_min_confidence"),
            "reporting.ui": ("ui_refresh_minutes", "ui_auto_refresh_enabled", "display_timezone"),
        }
        for section, keys in groups.items():
            for key in keys:
                if key in settings and _get(values, f"{section}.{key}", None) is None:
                    _set(values, f"{section}.{key}", deepcopy(settings[key]))
        sources.append("settings/app_settings.json")
    values["autonomy"].setdefault("policy", {})
    values["autonomy"]["policy"].setdefault("theoretical_only", True)
    values["discovery"].setdefault("composition", {"documented_pct": 70, "new_pct": 20, "experimental_pct": 10})
    values["discovery"].setdefault("rotation", {"enabled": True, "quarantine_unchanged": True, "explore_outside_indexes": True})
    values["portfolio"].setdefault("decision", {"max_country_pct": 45.0, "max_currency_pct": 55.0, "minimum_liquidity_score": 40.0})
    values["learning"].setdefault("allow_automatic_model_approval", False)
    doc["migration"] = {"complete": True, "at": _now(), "sources": sources}
    return _commit(doc, event="MIGRATION", reason="Migrering fra gamle innstillinger", actor="SYSTEM", previous=None)


def load_registry() -> dict[str, Any]:
    global _CACHE, _CACHE_AT, _CACHE_STORAGE_ID
    now = time.monotonic()
    storage = _storage()
    storage_id = id(storage)
    if _CACHE is not None and _CACHE_STORAGE_ID == storage_id and now - _CACHE_AT < _CACHE_TTL_SECONDS:
        return deepcopy(_CACHE)
    raw = storage.read_json(REGISTRY_KEY, default=None)
    doc = _normalize(raw)
    if raw is None:
        storage.write_json(REGISTRY_KEY, doc)
    doc = _migrate(doc)
    _CACHE = deepcopy(doc)
    _CACHE_AT = now
    _CACHE_STORAGE_ID = storage_id
    return deepcopy(doc)


def _commit(doc: dict[str, Any], *, event: str, reason: str, actor: str,
            previous: Mapping[str, Any] | None) -> dict[str, Any]:
    global _CACHE, _CACHE_AT, _CACHE_STORAGE_ID
    errors = validate_values(doc["values"])
    if errors:
        raise ValueError("; ".join(errors))
    if previous is not None:
        snapshot = {
            "config_version": previous.get("config_version"), "revision": previous.get("revision"),
            "at": previous.get("updated_at"), "checksum": previous.get("checksum"),
            "values": deepcopy(previous.get("values") or {}),
        }
        doc.setdefault("versions", []).insert(0, snapshot)
        doc["versions"] = doc["versions"][:50]
    doc["revision"] = int(doc.get("revision") or 0) + 1
    doc["config_version"] = _version(doc["revision"])
    doc["updated_at"] = _now(); doc["checksum"] = _checksum(doc["values"])
    doc.setdefault("history", []).insert(0, {
        "event": event, "at": doc["updated_at"], "actor": actor, "reason": reason,
        "config_version": doc["config_version"], "checksum": doc["checksum"],
    })
    doc["history"] = doc["history"][:1000]
    storage = _storage()
    storage.write_json(REGISTRY_KEY, doc)
    _CACHE = deepcopy(doc)
    _CACHE_AT = time.monotonic()
    _CACHE_STORAGE_ID = id(storage)
    return deepcopy(doc)


def read(path: str, default: Any = None) -> Any:
    return _get(load_registry()["values"], path, default)


def update(changes: Mapping[str, Any], *, reason: str, actor: str = "USER",
           compatibility: bool = False) -> dict[str, Any]:
    if not changes:
        return load_registry()
    if not compatibility and any(any(str(path).startswith(prefix) for prefix in SENSITIVE_PREFIXES) for path in changes):
        return propose(changes, reason=reason, actor=actor)
    current = load_registry(); doc = deepcopy(current)
    for path, value in changes.items():
        _set(doc["values"], str(path), value)
    if _checksum(doc["values"]) == current.get("checksum"):
        return current
    return _commit(doc, event="COMPATIBILITY_UPDATE" if compatibility else "UPDATE",
                   reason=reason, actor=actor, previous=current)


def propose(changes: Mapping[str, Any], *, reason: str, actor: str = "USER") -> dict[str, Any]:
    global _CACHE, _CACHE_AT, _CACHE_STORAGE_ID
    current = load_registry(); doc = deepcopy(current)
    candidate = deepcopy(doc["values"])
    for path, value in changes.items():
        _set(candidate, str(path), value)
    if _checksum(candidate) == current.get("checksum"):
        return {"approval_id": "NO_CHANGE", "status": "NO_CHANGE", "base_config_version": current["config_version"], "changes": {}}
    errors = validate_values(candidate)
    if errors:
        raise ValueError("; ".join(errors))
    approval = {
        "approval_id": f"CAP-{uuid.uuid4().hex[:12].upper()}", "status": "PENDING",
        "created_at": _now(), "actor": actor, "reason": reason,
        "base_config_version": current["config_version"], "changes": deepcopy(dict(changes)),
    }
    doc["approvals"].insert(0, approval)
    storage = _storage()
    storage.write_json(REGISTRY_KEY, doc)
    _CACHE = deepcopy(doc)
    _CACHE_AT = time.monotonic()
    _CACHE_STORAGE_ID = id(storage)
    return deepcopy(approval)


def resolve_approval(approval_id: str, approve: bool, *, actor: str = "USER") -> dict[str, Any]:
    global _CACHE, _CACHE_AT, _CACHE_STORAGE_ID
    current = load_registry(); doc = deepcopy(current)
    item = next((row for row in doc["approvals"] if row.get("approval_id") == approval_id), None)
    if not item or item.get("status") != "PENDING":
        raise ValueError("Godkjenningen finnes ikke eller er allerede behandlet")
    item["status"] = "APPROVED" if approve else "REJECTED"; item["resolved_at"] = _now(); item["resolved_by"] = actor
    if not approve:
        storage = _storage()
        storage.write_json(REGISTRY_KEY, doc)
        _CACHE = deepcopy(doc)
        _CACHE_AT = time.monotonic()
        _CACHE_STORAGE_ID = id(storage)
        return deepcopy(doc)
    for path, value in item.get("changes", {}).items():
        _set(doc["values"], path, value)
    return _commit(doc, event="APPROVED_UPDATE", reason=item.get("reason") or "Godkjent endring", actor=actor, previous=current)


def rollback(config_version: str, *, actor: str = "USER") -> dict[str, Any]:
    current = load_registry()
    snapshot = next((row for row in current.get("versions", []) if row.get("config_version") == config_version), None)
    if not snapshot:
        raise ValueError("Konfigurasjonsversjonen finnes ikke i rollback-historikken")
    doc = deepcopy(current); doc["values"] = deepcopy(snapshot["values"])
    return _commit(doc, event="ROLLBACK", reason=f"Rollback til {config_version}", actor=actor, previous=current)


def export_bundle() -> str:
    doc = load_registry()
    return json.dumps({
        "format": "AI_AKSJE_ANALYZER_CENTRAL_AUTONOMY_CONFIG", "format_version": 1,
        "exported_at": _now(), "config_version": doc["config_version"],
        "checksum": doc["checksum"], "values": doc["values"],
    }, ensure_ascii=False, indent=2, default=str)


def import_bundle(payload: str | bytes, *, actor: str = "USER") -> dict[str, Any]:
    parsed = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    if not isinstance(parsed, Mapping) or parsed.get("format") != "AI_AKSJE_ANALYZER_CENTRAL_AUTONOMY_CONFIG":
        raise ValueError("Ugyldig konfigurasjonspakke")
    values = parsed.get("values")
    if not isinstance(values, Mapping):
        raise ValueError("Konfigurasjonspakken mangler values")
    errors = validate_values(values)
    if errors:
        raise ValueError("; ".join(errors))
    changes = {root: deepcopy(values.get(root, {})) for root in ROOTS}
    return propose(changes, reason=f"Import av {parsed.get('config_version') or 'ukjent versjon'}", actor=actor)


def status() -> dict[str, Any]:
    doc = load_registry(); health = _storage().health()
    return {
        "config_version": doc["config_version"], "revision": doc["revision"],
        "checksum": doc["checksum"], "schema_version": doc["schema_version"],
        "backend": health.backend, "persistent": health.persistent, "ok": health.ok,
        "pending_approvals": sum(1 for row in doc["approvals"] if row.get("status") == "PENDING"),
        "migration": doc.get("migration", {}),
    }
