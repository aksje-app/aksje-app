"""v18.5.89 Safe infrastructure/governance/state-audit helpers.

Small, dependency-light utilities for audit logging, feature governance and
regression/smoke checks. Kept separate from analysemotorer to reduce side effects.
"""
from __future__ import annotations
import logging

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from durable_runtime import append_event, read_events

ROOT = Path(__file__).resolve().parent
AUDIT_LOG_FILE = ROOT / "runtime_audit_log.jsonl"

try:
    from governance_registry import get_changelog, get_protected_zones
except Exception:  # keep this helper dependency-light and fail-safe
    def get_changelog():
        return []
    def get_protected_zones():
        return []


@dataclass(frozen=True)
class FeatureStatus:
    key: str
    label: str
    status: str
    owner_area: str
    note: str = ""


FEATURE_REGISTRY: List[FeatureStatus] = [
    FeatureStatus("global_update", "Global oppdatering", "ACTIVE", "UI/state", "Sentral commit-knapp for tunge oppdateringer."),
    FeatureStatus("paper_capital", "Paper capital/cash/kjøpekraft", "ACTIVE", "Paper Trading", "Cash er kjøpekraft; porteføljeverdi inkluderer posisjoner."),
    FeatureStatus("auto_buy_safety_mode", "Sikkerhetsmodus", "ACTIVE", "Trading guardrails", "Blokkerer/strammer inn risikable auto-handlinger."),
    FeatureStatus("pushover_verify", "Pushover verifisering/test", "ACTIVE", "Alerts", "Verifiserer token/user-key og viser API-respons."),
    FeatureStatus("fallback_data_warnings", "Datakvalitet/fallback-varsler", "PARTIAL", "Analysis/data", "Grunnstruktur finnes; bør utvides per datakilde."),
    FeatureStatus("audit_log", "Audit-logg", "ACTIVE", "System/admin", "Logger viktige brukerhandlinger i sesjon og lokal jsonl ved mulig."),
    FeatureStatus("state_audit", "State & audit snapshots", "ACTIVE", "Paper Trading", "Logger før/etter-snapshots for kapital, kjøp, salg og blokkeringer."),
    FeatureStatus("trading_fail_safe", "Trading fail-safe", "ACTIVE", "Trading guardrails", "Sentral validering av cash, duplikatposisjon, dagsgrense og pris før BUY."),
    FeatureStatus("regression_smoke", "Regresjonssjekk", "ACTIVE", "Tests", "Kontrollerer kritiske UI-tekstankere og versjon."),
    FeatureStatus("protected_zones", "Protected zones", "ACTIVE", "Governance", "Kritiske områder har patch-regler og synlige ankere."),
    FeatureStatus("in_app_changelog", "In-app changelog/build identity", "ACTIVE", "Governance", "Viser aktiv build og siste stabile endringer i appen."),
    FeatureStatus("feature_governance", "Feature governance", "ACTIVE", "Governance", "Feature-status samles for å skille ACTIVE/PARTIAL/DUMMY/LEGACY/DISABLED."),
    FeatureStatus("ui_data_trust", "UI/data trust", "ACTIVE", "UI/data", "Datakvalitet, cache/fallback/stale og blokkårsaker vises mer konsekvent."),
    FeatureStatus("ui_consistency_tokens", "UI consistency tokens", "ACTIVE", "UI", "Standardiserte tokens for knapp/status/spacing uten redesign."),
]


def get_feature_registry() -> List[Dict[str, str]]:
    return [asdict(item) for item in FEATURE_REGISTRY]


def add_audit_event(event: str, detail: Optional[Dict[str, Any]] = None, *, level: str = "INFO") -> Dict[str, Any]:
    """Append a small audit event. Never raises; suitable for UI callbacks."""
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "event": str(event),
        "detail": detail or {},
    }
    try:
        append_event("system/runtime_audit.jsonl", AUDIT_LOG_FILE, record)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return record


def read_recent_audit_events(limit: int = 25) -> List[Dict[str, Any]]:
    try:
        return read_events("system/runtime_audit.jsonl", AUDIT_LOG_FILE, limit=max(1, int(limit)))
    except Exception:
        return []


def run_static_regression_checks(root: Optional[Path] = None) -> Dict[str, Any]:
    """D1 smoke checks for critical anchors. Does not import Streamlit/app."""
    root = Path(root or ROOT)
    app = (root / "app.py").read_text(encoding="utf-8", errors="ignore")
    version = (root / "app_version.py").read_text(encoding="utf-8", errors="ignore")
    required_app_anchors = [
        "Global oppdatering",
        "Startkapital / reset-verdi",
        "Bruk porteføljeverdi",
        "Cash/kjøpekraft",
        "Sikkerhetsmodus",
        "Protected zones",
        "Pushover-verifisering",
        "Send testvarsel",
        "UI/data trust",
        "Datakvalitet",
        "Sporbar drift",
    ]
    missing = [anchor for anchor in required_app_anchors if anchor not in app]
    version_ok = 'APP_VERSION = "v19.13.0"' in version
    return {
        "ok": not missing and version_ok,
        "version_ok": version_ok,
        "missing_anchors": missing,
        "checked_anchors": required_app_anchors,
    }
