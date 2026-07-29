"""Fail-closed runtime safety and deployment identity for v19.14.2.

The module is deliberately pure Python and has no Streamlit dependency.  It is
used by the UI, background workers, notifications and the Paper Trading order
layer so every code path reads the same environment truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any, Mapping

_TRUE = {"1", "true", "yes", "on", "enabled", "aktiv"}
_FALSE = {"0", "false", "no", "off", "disabled", "av", ""}
_TEST_TOKENS = ("test", "staging", "stage", "stabil", "preview", "sandbox", "qa", "dev")


def _raw(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def parse_env_bool(name: str, *, default: bool = False) -> tuple[bool, bool, str]:
    """Return ``(value, valid, raw)`` without accepting ambiguous values."""
    raw = _raw(name)
    if not raw:
        return bool(default), True, raw
    lowered = raw.lower()
    if lowered in _TRUE:
        return True, True, raw
    if lowered in _FALSE:
        return False, True, raw
    return False, False, raw


def deployment_environment(env: Mapping[str, str] | None = None) -> str:
    values = env or os.environ
    explicit = str(
        values.get("APP_ENVIRONMENT")
        or values.get("DEPLOYMENT_ENVIRONMENT")
        or values.get("RENDER_ENVIRONMENT")
        or ""
    ).strip().lower()
    if explicit:
        return explicit
    inferred = " ".join(
        str(values.get(key) or "")
        for key in ("RENDER_SERVICE_NAME", "RENDER_GIT_BRANCH", "GIT_BRANCH", "BRANCH")
    ).lower()
    if any(token in inferred for token in _TEST_TOKENS):
        return "test"
    return "production"


def is_test_environment(env: Mapping[str, str] | None = None) -> bool:
    value = deployment_environment(env)
    return value != "production" and any(token in value for token in _TEST_TOKENS + ("test",))


def _allow_in_test(name: str) -> bool:
    value, valid, _ = parse_env_bool(name, default=False)
    return bool(value and valid)


@dataclass(frozen=True)
class PaperTradingDecision:
    allowed: bool
    code: str
    label: str
    color: str
    reason: str
    environment: str
    configured_value: str


def paper_trading_decision() -> PaperTradingDecision:
    enabled, valid, raw = parse_env_bool("PAPER_TRADING_ENABLED", default=False)
    environment = deployment_environment()
    if not valid:
        return PaperTradingDecision(
            False, "INVALID_CONFIGURATION", "AV", "red",
            "PAPER_TRADING_ENABLED har ugyldig verdi og behandles som AV.", environment, raw,
        )
    if not enabled:
        return PaperTradingDecision(
            False, "DISABLED", "AV", "red",
            "Paper Trading er deaktivert av PAPER_TRADING_ENABLED.", environment, raw or "ikke satt",
        )
    if is_test_environment() and not _allow_in_test("ALLOW_PAPER_TRADING_IN_TEST"):
        return PaperTradingDecision(
            False, "TEST_ENVIRONMENT_BLOCK", "AV", "red",
            "Paper Trading er blokkert i testmiljø uten ALLOW_PAPER_TRADING_IN_TEST=true.", environment, raw,
        )
    return PaperTradingDecision(
        True, "ENABLED", "AKTIV", "green", "Paper Trading er eksplisitt aktivert.", environment, raw,
    )


def notifications_allowed() -> tuple[bool, str]:
    configured = bool(_raw("PUSHOVER_APP_TOKEN") and _raw("PUSHOVER_USER_KEY"))
    if not configured:
        return False, "Pushover-nøkler er ikke konfigurert."
    if is_test_environment() and not _allow_in_test("ALLOW_NOTIFICATIONS_IN_TEST"):
        return False, "Varsling er blokkert i testmiljø."
    return True, "Varsling er konfigurert."


def scheduler_allowed() -> tuple[bool, str]:
    raw = _raw("REPORT_SCHEDULER_ENABLED")
    if raw:
        enabled, valid, _ = parse_env_bool("REPORT_SCHEDULER_ENABLED", default=False)
        if not valid:
            return False, "REPORT_SCHEDULER_ENABLED har ugyldig verdi."
        if enabled and is_test_environment() and not _allow_in_test("ALLOW_SCHEDULER_IN_TEST"):
            return False, "Scheduler er blokkert i testmiljø."
        return enabled, "Scheduler er eksplisitt aktivert." if enabled else "Scheduler er eksplisitt deaktivert."
    if is_test_environment():
        return False, "Scheduler er AV som sikker standard i testmiljø."
    return True, "Scheduler bruker produksjonsstandard."


def runtime_background_allowed() -> tuple[bool, str]:
    raw = _raw("RUNTIME_BACKGROUND_ENABLED")
    if raw:
        enabled, valid, _ = parse_env_bool("RUNTIME_BACKGROUND_ENABLED", default=False)
        if not valid:
            return False, "RUNTIME_BACKGROUND_ENABLED har ugyldig verdi."
        if enabled and is_test_environment() and not _allow_in_test("ALLOW_BACKGROUND_IN_TEST"):
            return False, "Bakgrunnstjenester er blokkert i testmiljø."
        return enabled, "Bakgrunnstjenester er eksplisitt aktivert." if enabled else "Bakgrunnstjenester er eksplisitt deaktivert."
    if is_test_environment():
        return False, "Bakgrunnstjenester er AV som sikker standard i testmiljø."
    return True, "Bakgrunnstjenester bruker produksjonsstandard."


def deployment_identity() -> dict[str, str]:
    commit = _raw("RENDER_GIT_COMMIT") or _raw("GIT_COMMIT") or _raw("SOURCE_COMMIT") or "ukjent"
    branch = _raw("RENDER_GIT_BRANCH") or _raw("GIT_BRANCH") or _raw("BRANCH") or "ukjent"
    return {
        "environment": deployment_environment(),
        "service": _raw("RENDER_SERVICE_NAME") or _raw("SERVICE_NAME") or "lokal",
        "branch": branch,
        "commit": commit,
        "commit_short": commit[:8] if commit != "ukjent" else commit,
        "external_url": _raw("RENDER_EXTERNAL_URL"),
    }


def runtime_safety_snapshot() -> dict[str, Any]:
    paper = paper_trading_decision()
    notifications, notification_reason = notifications_allowed()
    scheduler, scheduler_reason = scheduler_allowed()
    background, background_reason = runtime_background_allowed()
    database_configured = bool(_raw("DATABASE_URL"))
    test_env = is_test_environment()
    violations: list[str] = []
    if test_env and database_configured and not _allow_in_test("ALLOW_DATABASE_IN_TEST"):
        violations.append("Testmiljøet har DATABASE_URL uten ALLOW_DATABASE_IN_TEST=true.")
    if test_env and bool(_raw("PUSHOVER_APP_TOKEN") or _raw("PUSHOVER_USER_KEY")) and not _allow_in_test("ALLOW_NOTIFICATIONS_IN_TEST"):
        # Presence is shown as isolated, not fatal; send functions remain blocked.
        pass
    return {
        **deployment_identity(),
        "is_test_environment": test_env,
        "paper_trading": asdict(paper),
        "database_configured": database_configured,
        "database_allowed": not violations,
        "notifications_allowed": notifications,
        "notification_reason": notification_reason,
        "scheduler_enabled": scheduler,
        "scheduler_reason": scheduler_reason,
        "background_enabled": background,
        "background_reason": background_reason,
        "blocking_violations": violations,
        "safe": not violations,
    }


def assert_runtime_safe() -> dict[str, Any]:
    snapshot = runtime_safety_snapshot()
    if snapshot["blocking_violations"]:
        raise RuntimeError(" ".join(snapshot["blocking_violations"]))
    return snapshot


__all__ = [
    "PaperTradingDecision", "assert_runtime_safe", "deployment_environment",
    "deployment_identity", "is_test_environment", "notifications_allowed",
    "paper_trading_decision", "parse_env_bool", "runtime_background_allowed",
    "runtime_safety_snapshot", "scheduler_allowed",
]
