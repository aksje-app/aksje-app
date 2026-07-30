"""Fail-fast checks for runtime packages required by critical workflows.

The application previously generated a PDF successfully and failed only at the
semantic integrity stage because ``pypdf`` was available in development but was
not declared in ``requirements.txt``.  This module provides one canonical check
used by the web app, the unattended scheduler, tests and the Render build smoke.
"""
from __future__ import annotations

import importlib
from importlib import metadata
from typing import Any, Iterable

REQUIRED_RUNTIME_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("pypdf", "PDF-lesing og semantisk rapportintegritet"),
)


def check_runtime_dependencies(
    required: Iterable[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a serialisable dependency status without hiding import errors."""
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    for module_name, purpose in tuple(required or REQUIRED_RUNTIME_DEPENDENCIES):
        item: dict[str, Any] = {
            "module": module_name,
            "purpose": purpose,
            "available": False,
            "version": "",
            "error": "",
        }
        try:
            importlib.import_module(module_name)
            item["available"] = True
            try:
                item["version"] = metadata.version(module_name)
            except metadata.PackageNotFoundError:
                item["version"] = "ukjent"
        except Exception as exc:  # include binary/import-time failures, not only ModuleNotFoundError
            item["error"] = f"{type(exc).__name__}: {exc}"
            errors.append(
                f"Mangler runtime-avhengighet '{module_name}' for {purpose}: {item['error']}"
            )
        checks.append(item)
    return {"ok": not errors, "checks": checks, "errors": errors}


def assert_runtime_dependencies(
    required: Iterable[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Raise a deterministic startup error when a critical package is missing."""
    result = check_runtime_dependencies(required)
    if not result["ok"]:
        raise RuntimeError("Runtime-avhengighetskontroll feilet: " + " | ".join(result["errors"]))
    return result
