"""Central versioned configuration framework for AI Aksje Analyzer v18.6.91.

The framework keeps one canonical configuration document in StorageService.
It preserves user values across Streamlit reruns, browser refreshes, restarts,
and application upgrades. Unknown fields are retained for forward/backward
compatibility. Legacy persistent_config keys are migrated on first use.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

FRAMEWORK_VERSION = 1
APP_COMPAT_VERSION = "v18.6.91"
CANONICAL_KEY = "configuration/framework.json"
BACKUP_PREFIX = "configuration/backups"

# Existing v18.6.90b keys mapped into one canonical document.
LEGACY_SECTIONS = {
    "autonomous_portfolio/parameters.json": "autonomous_portfolio.parameters",
    "autonomous_portfolio/portfolio.json": "autonomous_portfolio.portfolio",
    "controlled_learning/state.json": "controlled_learning.state",
    "controlled_learning/hypotheses.json": "controlled_learning.hypotheses",
    "controlled_learning/experiments.json": "controlled_learning.experiments",
    "controlled_learning/parameter_versions.json": "controlled_learning.parameter_versions",
    "controlled_learning/management_reports.json": "controlled_learning.management_reports",
    "controlled_learning/promotion_approvals.json": "controlled_learning.promotion_approvals",
    "market_intelligence/jobs.json": "market_intelligence.jobs",
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _storage():
    from services.storage_service import get_storage_service
    return get_storage_service()


def _empty_document() -> dict[str, Any]:
    return {
        "framework_version": FRAMEWORK_VERSION,
        "app_compat_version": APP_COMPAT_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "revision": 0,
        "sections": {},
        "metadata": {
            "source": "configuration_framework",
            "migration_complete": False,
        },
    }


def _split_path(path: str) -> list[str]:
    return [part for part in str(path or "").replace("/", ".").split(".") if part]


def _get_nested(root: Mapping[str, Any], path: str, default: Any = None) -> Any:
    node: Any = root
    for part in _split_path(path):
        if not isinstance(node, Mapping) or part not in node:
            return deepcopy(default)
        node = node[part]
    return deepcopy(node)


def _set_nested(root: dict[str, Any], path: str, value: Any) -> None:
    parts = _split_path(path)
    if not parts:
        raise ValueError("Configuration section path cannot be empty")
    node = root
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = deepcopy(value)


def _normalize_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_document()
    doc = _empty_document()
    doc.update({k: deepcopy(v) for k, v in raw.items() if k != "sections"})
    doc["sections"] = deepcopy(raw.get("sections")) if isinstance(raw.get("sections"), dict) else {}
    doc["framework_version"] = int(raw.get("framework_version") or FRAMEWORK_VERSION)
    doc["revision"] = int(raw.get("revision") or 0)
    doc["metadata"] = deepcopy(raw.get("metadata")) if isinstance(raw.get("metadata"), dict) else {}
    return doc


def _write_document(doc: dict[str, Any]) -> bool:
    storage = _storage()
    doc = _normalize_document(doc)
    doc["framework_version"] = FRAMEWORK_VERSION
    doc["app_compat_version"] = APP_COMPAT_VERSION
    doc["updated_at"] = _now()
    doc["revision"] = int(doc.get("revision") or 0) + 1
    return bool(storage.write_json(CANONICAL_KEY, doc))


def _migrate_legacy(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.setdefault("metadata", {})
    if metadata.get("migration_complete"):
        return doc
    storage = _storage()
    migrated: list[str] = []
    for legacy_key, section in LEGACY_SECTIONS.items():
        existing = _get_nested(doc.get("sections", {}), section, default=None)
        if existing is not None:
            continue
        legacy_value = storage.read_json(f"persistent_config/{legacy_key}", default=None)
        if legacy_value is not None:
            _set_nested(doc.setdefault("sections", {}), section, legacy_value)
            migrated.append(legacy_key)
    metadata["migration_complete"] = True
    metadata["migrated_legacy_keys"] = migrated
    metadata["migration_at"] = _now()
    _write_document(doc)
    return doc


def load_document() -> dict[str, Any]:
    storage = _storage()
    raw = storage.read_json(CANONICAL_KEY, default=None)
    doc = _normalize_document(raw)
    if raw is None:
        _write_document(doc)
        raw = storage.read_json(CANONICAL_KEY, default=doc)
        doc = _normalize_document(raw)
    return _migrate_legacy(doc)


def read_section(section: str, default: Any = None) -> Any:
    doc = load_document()
    return _get_nested(doc.get("sections", {}), section, default)


def write_section(section: str, value: Any, *, reason: str = "USER_SAVE") -> bool:
    doc = load_document()
    _set_nested(doc.setdefault("sections", {}), section, value)
    metadata = doc.setdefault("metadata", {})
    metadata["last_change_reason"] = reason
    metadata["last_changed_section"] = section
    metadata["last_changed_at"] = _now()
    return _write_document(doc)


def read_legacy_key(key: str, default: Any = None) -> Any:
    section = LEGACY_SECTIONS.get(key)
    if section:
        return read_section(section, default)
    return read_section(f"legacy.{key}", default)


def write_legacy_key(key: str, value: Any) -> bool:
    section = LEGACY_SECTIONS.get(key, f"legacy.{key}")
    return write_section(section, value, reason=f"LEGACY_ADAPTER:{key}")


def checksum(doc: Mapping[str, Any] | None = None) -> str:
    payload = deepcopy(dict(doc or load_document()))
    payload.pop("updated_at", None)
    payload.pop("revision", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()


def export_bundle() -> str:
    doc = load_document()
    bundle = {
        "format": "AI_AKSJE_ANALYZER_CONFIGURATION",
        "format_version": 1,
        "exported_at": _now(),
        "checksum": checksum(doc),
        "configuration": doc,
    }
    return json.dumps(bundle, ensure_ascii=False, indent=2, default=str)


def import_bundle(payload: str | bytes, *, create_backup: bool = True) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Konfigurasjonsfilen må inneholde et JSON-objekt.")
    if parsed.get("format") == "AI_AKSJE_ANALYZER_CONFIGURATION":
        candidate = parsed.get("configuration")
    else:
        candidate = parsed
    if not isinstance(candidate, dict) or not isinstance(candidate.get("sections"), dict):
        raise ValueError("Ugyldig konfigurasjonsformat: feltet 'sections' mangler.")
    current = load_document()
    if create_backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _storage().write_json(f"{BACKUP_PREFIX}/before_import_{stamp}.json", current)
    imported = _normalize_document(candidate)
    imported["created_at"] = current.get("created_at") or imported.get("created_at") or _now()
    imported.setdefault("metadata", {})["last_import_at"] = _now()
    imported["metadata"]["imported_from_checksum"] = parsed.get("checksum")
    _write_document(imported)
    return load_document()


def status() -> dict[str, Any]:
    storage = _storage()
    health = storage.status_dict()
    doc = load_document()
    return {
        **health,
        "framework_version": doc.get("framework_version"),
        "app_compat_version": doc.get("app_compat_version"),
        "revision": doc.get("revision"),
        "updated_at": doc.get("updated_at"),
        "checksum": checksum(doc),
        "canonical_key": CANONICAL_KEY,
    }
