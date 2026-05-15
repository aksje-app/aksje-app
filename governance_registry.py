"""v18.5.89 Governance registry.

Low-risk metadata for protected zones, feature status and in-app changelog.
This module must not import Streamlit or analysemotorer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ProtectedZone:
    key: str
    label: str
    owner_area: str
    file: str
    anchor: str
    rule: str


@dataclass(frozen=True)
class ChangelogItem:
    version: str
    title: str
    category: str
    note: str


PROTECTED_ZONES: List[ProtectedZone] = [
    ProtectedZone(
        "global_update_topbar",
        "Global oppdatering / toppkontroll",
        "UI/state",
        "app.py",
        "render_global_update_bar_v18548",
        "Kun minimal patch. Ikke flytt global-knappen uten regression anchor/test.",
    ),
    ProtectedZone(
        "paper_capital_controls",
        "Paper capital/cash/kjøpekraft",
        "Paper Trading",
        "app.py",
        "Juster Paper Trading startverdier / porteføljeverdi",
        "Behold skillet mellom startkapital, cash, posisjonsverdi og porteføljeverdi.",
    ),
    ProtectedZone(
        "pushover_alert_controls",
        "Pushover verifisering/test",
        "Alerts",
        "app.py/notifier.py",
        "Pushover-verifisering",
        "Ikke vis umaskerte token/user-key i UI eller audit-logg.",
    ),
    ProtectedZone(
        "safety_mode_guardrail",
        "Sikkerhetsmodus / auto-buy guardrail",
        "Trading guardrails",
        "app.py/settings_store.py",
        "auto_buy_safety_mode",
        "Toggle skal enten ha effekt eller være tydelig merket som deaktivert/partial.",
    ),
    ProtectedZone(
        "ui_data_trust_panel",
        "UI/data trust og blokkforklaringer",
        "UI/data",
        "app.py/ui_trust.py",
        "UI/data trust",
        "Vis datakvalitet og blokkårsaker uten å endre analysemotorenes beslutningslogikk.",
    ),
]


CHANGELOG: List[ChangelogItem] = [
    ChangelogItem("v18.5.89", "UI/data trust", "Batch G", "Consistent UI tokens, data-quality indicators and clearer blocked-action explanations."),
    ChangelogItem("v18.5.88", "State & audit", "Batch F", "Central state snapshots, audit transitions and safer BUY validation around paper trading."),
    ChangelogItem("v18.5.87", "Governance hardening", "Batch E", "Protected zones, governance registry and clearer in-app changelog/build identity."),
    ChangelogItem("v18.5.86", "Safe infrastructure", "Batch D", "Regression smoke checks, audit log and initial feature-status panel."),
    ChangelogItem("v18.5.85", "Operational alert safety", "Batch C", "Pushover verification/test response and safer credential masking."),
    ChangelogItem("v18.5.84", "UX stability", "Batch B", "Global update responsive behavior and status/toast cleanup."),
    ChangelogItem("v18.5.83", "Critical stability", "Batch A", "Capital/cash semantics and safety-mode guardrails."),
]


def get_protected_zones() -> List[Dict[str, str]]:
    return [asdict(item) for item in PROTECTED_ZONES]


def get_changelog() -> List[Dict[str, str]]:
    return [asdict(item) for item in CHANGELOG]
