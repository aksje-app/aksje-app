"""Versioned references for duplicated, JSON-compatible storage documents."""
from __future__ import annotations

from hashlib import sha256
import json
import os
import re


REFERENCE = "__storage_reference_v1__"
FIELDS = "__storage_fields_v1__"
REPORT_RUN_PREFIXES = ("market_intelligence/runs/", "investment_pipeline/runs/")
_VERSION_PREFIX = "storage_shared/v1/"
_TARGET = re.compile(
    r"(?:storage_shared/v1/[0-9a-f]{64}|repositories/market_snapshots/items/[A-Za-z0-9_.-]{1,120}"
    r"|(?:market_intelligence|investment_pipeline)/runs/[A-Za-z0-9_.-]{1,120})\.json"
    r"|repositories/reports\.json"
)
_CHECKSUM = re.compile(r"[0-9a-f]{64}")
_FIELD = re.compile(r"[A-Za-z0-9_-]{1,80}")
_MAX_DEPTH = 8


def retired_report_run_key(name: str) -> str:
    return "maintenance/retired_run/" + name


class StorageReferenceError(RuntimeError):
    """A reference cannot supply the document promised by its writer."""


def authoritative_postgres(storage) -> bool:
    return storage.using_postgres() and not storage.allow_local_fallback


def references_enabled(storage) -> bool:
    return (
        os.getenv("STORAGE_SHARED_REFERENCES_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
        and authoritative_postgres(storage)
    )


def can_contain_references(name: str) -> bool:
    return name in {
        "market_intelligence/latest_run.json",
        "market_intelligence/report_archive.json",
        "investment_pipeline/latest_run.json",
    } or name.startswith((
        _VERSION_PREFIX,
        "autonomous_portfolio/nok_preparation/",
        "investment_pipeline/proposals/",
        "investment_pipeline/runs/",
        "market_intelligence/runs/",
        "repositories/strategy_decisions/items/",
        "repositories/strategy_runs/items/",
    ))


def dependent_aliases(name: str) -> tuple[str, ...]:
    if name.startswith("market_intelligence/runs/"):
        return ("market_intelligence/latest_run.json",)
    if name.startswith("investment_pipeline/runs/"):
        stem = name.rsplit("/", 1)[-1].removesuffix(".json")
        return ("investment_pipeline/latest_run.json", f"investment_pipeline/proposals/{stem}_proposals.json")
    if name == "repositories/reports.json":
        return ("market_intelligence/report_archive.json",)
    return ()


def content_hash(value) -> str:
    options = {"ensure_ascii": True, "separators": (",", ":"), "default": str}
    # Apply the same key conversion as on disk before sorting, including
    # numeric keys and mixed key spellings that normalize to the same string.
    normalized = json.loads(json.dumps(value, **options))
    encoded = json.dumps(normalized, sort_keys=True, **options)
    return sha256(encoded.encode("ascii")).hexdigest()


def version_key(value) -> str:
    return f"{_VERSION_PREFIX}{content_hash(value)}.json"


def reference(key: str, value, field: str | None = None) -> dict:
    if not _TARGET.fullmatch(key) or (field is not None and (not isinstance(field, str) or not _FIELD.fullmatch(field))):
        raise StorageReferenceError("invalid reference target or projection")
    digest = content_hash(value)
    if field is None and key == f"{_VERSION_PREFIX}{digest}.json":
        return {REFERENCE: digest}
    result = {"key": key, "sha256": digest}
    if field is not None:
        result["field"] = field
    return {REFERENCE: result}


def reference_info(value) -> tuple[str, str, str | None] | None:
    if not isinstance(value, dict) or set(value) != {REFERENCE}:
        return None
    info = value[REFERENCE]
    if isinstance(info, str) and _CHECKSUM.fullmatch(info):
        return f"{_VERSION_PREFIX}{info}.json", info, None
    if not isinstance(info, dict) or not {"key", "sha256"} <= set(info) <= {"key", "sha256", "field"}:
        raise StorageReferenceError("invalid reference metadata")
    key, expected, field = info["key"], info["sha256"], info.get("field")
    if (
        not isinstance(key, str) or not _TARGET.fullmatch(key)
        or not isinstance(expected, str) or not _CHECKSUM.fullmatch(expected)
        or ("field" in info and (not isinstance(field, str) or not _FIELD.fullmatch(field)))
    ):
        raise StorageReferenceError("invalid reference target, checksum or projection")
    return key, expected, field


def referenced_fields(document: dict, fields: dict) -> dict:
    if not fields:
        return document
    if not fields.keys() <= document.keys():
        raise StorageReferenceError("referenced fields must exist on the document")
    return {FIELDS: {"document": {key: value for key, value in document.items() if key not in fields}, "fields": fields}}


def has_references(value) -> bool:
    return isinstance(value, dict) and len(value) == 1 and (REFERENCE in value or FIELDS in value)


def resolve_references(value, load_many, *, validate_value=None):
    """Resolve whole documents and ordered projections with batched key reads."""
    loaded: dict = {}
    resolved: dict = {}

    def materialize(refs, trail):
        keys = {key for key, _, _ in refs}
        if keys.intersection(trail):
            raise StorageReferenceError("reference cycle")
        if len(trail) >= _MAX_DEPTH:
            raise StorageReferenceError("reference nesting limit exceeded")
        wanted = keys.difference(loaded)
        if wanted:
            found = load_many(sorted(wanted))
            missing = wanted.difference(found)
            if missing:
                raise StorageReferenceError(f"missing reference target {min(missing)}")
            loaded.update(found)
        results = []
        for key, expected, field in refs:
            if key not in resolved:
                resolved[key] = decode(loaded[key], trail + (key,))
            result = resolved[key]
            if field is not None:
                if not isinstance(result, dict) or field not in result:
                    raise StorageReferenceError(f"missing reference field {field} at {key}")
                result = result[field]
            if validate_value is not None:
                validate_value(result)
            if content_hash(result) != expected:
                raise StorageReferenceError(f"reference checksum differs at {key}")
            results.append(result)
        return results

    def decode(document, trail):
        if not has_references(document):
            return document
        if REFERENCE in document:
            return materialize([reference_info(document)], trail)[0]
        envelope = document[FIELDS]
        if not isinstance(envelope, dict) or set(envelope) != {"document", "fields"}:
            raise StorageReferenceError("invalid referenced fields envelope")
        plain, fields = envelope["document"], envelope["fields"]
        if not isinstance(plain, dict) or not isinstance(fields, dict) or plain.keys() & fields.keys():
            raise StorageReferenceError("invalid referenced fields")
        references = []
        for spec in fields.values():
            items = spec if isinstance(spec, list) else [spec]
            for item in items:
                info = reference_info(item)
                if info is None:
                    raise StorageReferenceError("missing reference in field")
                references.append(info)
        values = iter(materialize(references, trail))
        expanded = {
            **plain,
            **{field: [next(values) for _ in spec] if isinstance(spec, list) else next(values) for field, spec in fields.items()},
        }
        if validate_value is not None:
            validate_value(expanded)
        return expanded

    return decode(value, ())
