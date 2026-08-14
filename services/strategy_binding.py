"""Fail-safe strategy identity stamping for decisions and simulated trades."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from app_version import (
    APP_VERSION,
    AUTONOMY_POLICY_VERSION,
    AUTONOMY_STRATEGY_VERSION,
    AUTONOMY_STRATEGY_VERSION_ID,
    TECHNICAL_BENCHMARK_IMPLEMENTATION_VERSION,
)


_FALLBACKS = {
    "technical": {
        "strategy_family": "technical",
        "bound": False,
        "strategy_id": "technical_benchmark",
        "strategy_version": "legacy-1.0.0",
        "parameter_version": "paper-trading-rules-current",
        "implementation_version": TECHNICAL_BENCHMARK_IMPLEMENTATION_VERSION,
    },
    "autonomy": {
        "strategy_family": "autonomy",
        "bound": False,
        "strategy_id": "autonomy_main",
        "strategy_version": AUTONOMY_STRATEGY_VERSION,
        "version_id": AUTONOMY_STRATEGY_VERSION_ID,
        "parameter_version": AUTONOMY_POLICY_VERSION,
        "implementation_version": APP_VERSION,
    },
}


@lru_cache(maxsize=8)
def current_strategy_binding(family: str) -> dict[str, Any]:
    key = str(family or "").strip().lower()
    fallback = dict(_FALLBACKS.get(key) or {"strategy_family": key, "bound": False})
    try:
        from services.strategy_registry_service import get_strategy_registry_service
        service = get_strategy_registry_service()
        service.ensure_defaults()
        binding = service.decision_binding(key)
        return {**fallback, **dict(binding or {})}
    except Exception as exc:
        # Strategy metadata is observability. It must never stop a decision or trade.
        fallback["binding_error"] = str(exc)[:300]
        return fallback


def strategy_metadata(family: str) -> dict[str, Any]:
    binding = current_strategy_binding(family)
    return {
        "strategy_family": binding.get("strategy_family") or family,
        "strategy_id": binding.get("strategy_id") or "",
        "strategy_version": binding.get("strategy_version") or "",
        "parameter_version": binding.get("parameter_version") or "",
        "strategy_version_id": binding.get("version_id") or "",
        "strategy_implementation_version": binding.get("implementation_version") or APP_VERSION,
        "strategy_config_checksum": binding.get("config_checksum") or "",
        "strategy_binding_verified": bool(binding.get("bound")),
    }


def stamp_strategy_metadata(row: Mapping[str, Any] | None, family: str) -> dict[str, Any]:
    value = dict(row or {})
    for key, item in strategy_metadata(family).items():
        value.setdefault(key, item)
    return value
