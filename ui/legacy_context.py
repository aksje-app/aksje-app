"""Compatibility bridge for renderers extracted from the legacy Streamlit shell.

The bridge is intentionally read-only with regard to business rules: it exposes the
legacy module namespace to extracted renderer functions while preserving the new
module's own callables. This lets v19.2.x split app.py safely before deeper service
dependency injection in later versions.
"""
from __future__ import annotations
from typing import Any, Iterable, MutableMapping

def bind_legacy_context(
    module_globals: MutableMapping[str, Any],
    legacy_context: MutableMapping[str, Any],
    *,
    preserve: Iterable[str] = (),
) -> None:
    protected = set(preserve) | {"bind_legacy_context", "_PRESERVE"}
    for name, value in legacy_context.items():
        if name.startswith("__") or name in protected:
            continue
        module_globals[name] = value
