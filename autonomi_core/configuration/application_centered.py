"""Governed activation gate for the v19 autonomy-centered application shell."""
from __future__ import annotations

from typing import Any, Mapping

CONFIG_PATH = "autonomy.application_centered.enabled"
MIN_VALIDATIONS = 3


def application_centered_enabled() -> bool:
    from .registry import read
    return bool(read(CONFIG_PATH, False))


def shadow_readiness(records: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if records is None:
        from autonomi_core.runtime.parallel_validation import load_parallel_validation_history
        records = load_parallel_validation_history(100)
    valid = [r for r in records if r.get("authority_preserved") is True and r.get("mode") == "SHADOW_READ_ONLY"]
    violations = [r.get("validation_id") for r in records if not r.get("authority_preserved") or not r.get("writes_blocked")]
    return {"ready": len(valid) >= MIN_VALIDATIONS and not violations, "validations": len(valid),
            "minimum": MIN_VALIDATIONS, "violations": violations,
            "rule": "Ny applikasjonsstruktur aktiveres først etter godkjent Shadow Mode."}


def request_activation(*, actor: str = "USER") -> dict[str, Any]:
    readiness = shadow_readiness()
    if not readiness["ready"]:
        raise ValueError(f"Shadow Mode er ikke klar: {readiness['validations']}/{readiness['minimum']} gyldige valideringer")
    from .registry import propose
    return propose({CONFIG_PATH: True}, reason="v19.0.0 Autonomy-Centered Application etter godkjent Shadow Mode", actor=actor)


def application_navigation() -> tuple[tuple[str, str, str], ...]:
    return (("🏠", "Dashboard", "dashboard"), ("🧠", "Autonomi", "autonomy"),
            ("📈", "Analyse", "analysis"), ("🎯", "Top Picks", "top_picks"),
            ("🧾", "Paper Trading", "paper_trading"),
            ("💼", "Portefølje", "portfolio"), ("📚", "Rapporter", "reports"),
            ("⚙️", "System", "system"))


def compatibility_manifest() -> dict[str, Any]:
    return {"legacy_deleted": False, "legacy_mode": "EXPERT_DIAGNOSTICS", "other_panels_visible": False,
            "parameter_owner": "Central Autonomy Configuration",
            "engine_details": ["News", "Insider", "Research"],
            "operations_under_autonomy": ["Scheduler", "Varsler", "Drift"],
            "rollback": "Sett autonomy.application_centered.enabled tilbake via konfigurasjonsrollback"}
