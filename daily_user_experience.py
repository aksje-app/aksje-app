"""Daily user-experience contracts for v19.0.22.

This module contains pure, renderer-independent contracts for the global
Simple/Advanced mode, navigation, Norwegian statuses, dashboard attention
items and candidate action metadata. It does not alter scoring, trading or
portfolio rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Any, Iterable, Mapping

UI_EXPERIENCE_SCHEMA_VERSION = "1.0"
SIMPLE_MODE = "Enkel"
ADVANCED_MODE = "Avansert"
VALID_MODES = (SIMPLE_MODE, ADVANCED_MODE)
DEFAULT_MODE = SIMPLE_MODE
SETTINGS_ROOT = "ui_experience_v19022"

PRIMARY_NAVIGATION = (
    ("🏠", "Oversikt", "dashboard"),
    ("📚", "Rapport", "reports"),
    ("📈", "Analyse", "analysis"),
    ("💼", "Portefølje", "portfolio"),
)
MORE_NAVIGATION = (
    ("🧠", "Autonomi", "autonomy"),
    ("🧾", "Paper Trading", "paper_trading"),
    ("✅", "Godkjenninger", "approvals"),
    ("⏱️", "Jobber", "jobs"),
    ("🔔", "Varsler", "operations"),
    ("💱", "Valuta", "fx_alerts"),
    ("🛠️", "Drift", "operations"),
    ("⚙️", "Innstillinger", "system"),
)
ADVANCED_NAVIGATION = (
    ("🏠", "Oversikt", "dashboard"),
    ("🧠", "Autonomi", "autonomy"),
    ("📚", "Rapporter", "reports"),
    ("⏱️", "Jobber / Planlegger", "jobs"),
    ("✅", "Godkjenninger", "approvals"),
    ("💼", "Portefølje", "portfolio"),
    ("🧾", "Paper Trading", "paper_trading"),
    ("🎯", "Top Picks", "top_picks"),
    ("📈", "Analyse", "analysis"),
    ("🚀", "Long Engine", "long_engine"),
    ("🤖", "AI-verktøy", "ai"),
    ("🔔", "Varsler / Drift", "operations"),
    ("💱", "Valuta", "fx_alerts"),
    ("⚙️", "System", "system"),
)

STATUS_LABELS = {
    "review": "Krever vurdering",
    "requires_review": "Krever vurdering",
    "ready": "Beslutningsklar",
    "decision_ready": "Beslutningsklar",
    "watch": "Overvåk",
    "blocked": "Blokkert",
    "expired": "Utløpt",
    "invalid": "Ugyldig",
    "draft": "Foreløpig",
    "preliminary": "Foreløpig",
    "final": "Endelig",
    "buy": "Kjøp",
    "sell": "Selg",
    "hold": "Vent",
    "wait": "Vent",
    "skip": "Ikke aktuell",
    "pending": "Venter",
    "running": "Pågår",
    "completed": "Utført",
    "resolved": "Utført",
    "still_problem": "Fortsatt problem",
    "not_relevant": "Ikke lenger relevant",
}


@dataclass(frozen=True)
class AttentionItem:
    severity: str
    title: str
    detail: str
    nav: str
    code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"avansert", "advanced", "expert", "full"}:
        return ADVANCED_MODE
    return SIMPLE_MODE


def user_identity(user: Mapping[str, Any] | str | None) -> str:
    if isinstance(user, Mapping):
        value = user.get("username") or user.get("email") or user.get("id")
    else:
        value = user
    return str(value or "default").strip().lower() or "default"


def get_user_mode(settings: Mapping[str, Any] | None, user: Mapping[str, Any] | str | None) -> str:
    root = dict((settings or {}).get(SETTINGS_ROOT) or {})
    users = dict(root.get("users") or {})
    entry = users.get(user_identity(user))
    if isinstance(entry, Mapping):
        return normalize_mode(entry.get("mode"))
    return normalize_mode(root.get("default_mode") or DEFAULT_MODE)


def set_user_mode(settings: Mapping[str, Any] | None, user: Mapping[str, Any] | str | None, mode: Any) -> dict[str, Any]:
    output = dict(settings or {})
    root = dict(output.get(SETTINGS_ROOT) or {})
    users = dict(root.get("users") or {})
    users[user_identity(user)] = {
        "mode": normalize_mode(mode),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    root.update({"schema_version": UI_EXPERIENCE_SCHEMA_VERSION, "default_mode": DEFAULT_MODE, "users": users})
    output[SETTINGS_ROOT] = root
    return output


def navigation_for_mode(mode: Any) -> dict[str, tuple[tuple[str, str, str], ...]]:
    if normalize_mode(mode) == ADVANCED_MODE:
        return {"primary": ADVANCED_NAVIGATION, "more": ()}
    return {"primary": PRIMARY_NAVIGATION, "more": MORE_NAVIGATION}


def status_label(value: Any, default: str | None = None) -> str:
    raw = str(value or "").strip()
    key = raw.lower().replace("-", "_").replace(" ", "_")
    if key in STATUS_LABELS:
        return STATUS_LABELS[key]
    upper = raw.upper()
    if "BUY" in upper or "KJØP" in upper:
        return "Kjøp"
    if "SELL" in upper or "AVOID" in upper or "UNNGÅ" in upper:
        return "Selg / unngå"
    if "HOLD" in upper or "WAIT" in upper or "VENT" in upper:
        return "Vent"
    if "REVIEW" in upper or "VURDER" in upper:
        return "Krever vurdering"
    return default if default is not None else raw


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return default


def build_attention_items(
    archive: Iterable[Mapping[str, Any]] | None,
    *,
    pending_approvals: int = 0,
    scheduler_ok: bool | None = None,
    max_items: int = 7,
) -> list[dict[str, Any]]:
    rows = [dict(x) for x in (archive or []) if isinstance(x, Mapping)]
    items: list[AttentionItem] = []
    if not rows:
        items.append(AttentionItem("critical", "Ingen rapport tilgjengelig", "Kjør en rapport for å etablere dagens beslutningsgrunnlag.", "reports", "REPORT_MISSING"))
    else:
        latest = rows[0]
        label = str(latest.get("report_label") or latest.get("report_type") or "Siste rapport")
        created = str(latest.get("created_at_local") or latest.get("created_at") or "ukjent tidspunkt")
        if bool(latest.get("has_errors")):
            items.append(AttentionItem("critical", f"{label} har feil", f"{_int(latest.get('error_count'))} feil registrert · {created}", "operations", "REPORT_ERRORS"))
        reliability = _int(latest.get("report_reliability"))
        if reliability and reliability < 65:
            items.append(AttentionItem("warning", "Lav rapportpålitelighet", f"{label}: {reliability}/100. Åpne rapporten og se hvilke datamangler som trekker ned.", "reports", "LOW_RELIABILITY"))
        if bool(latest.get("reserve_feed_used")):
            items.append(AttentionItem("warning", "Reserve-feed er i bruk", "Minst én finansmediekilde bruker reserve-feed. Kontroller kildegrunnlaget.", "operations", "RESERVE_FEED"))
        urgent = _int(latest.get("urgent_task_count"))
        tasks = _int(latest.get("next_task_count"))
        if urgent:
            items.append(AttentionItem("warning", f"{urgent} prioriterte oppgaver", f"Rapporten har {tasks} oppgaver til neste kjøring.", "reports", "URGENT_TASKS"))
        ready = _int(latest.get("decision_ready_count"))
        if ready:
            items.append(AttentionItem("info", f"{ready} beslutningsklare kandidater", "Åpne rapporten for begrunnelse, gyldighet og risikoforutsetninger.", "reports", "DECISION_READY"))
        if bool(latest.get("top3_changed")):
            items.append(AttentionItem("info", "Top 3 er endret", "Minst én kandidat er ny eller har falt ut siden forrige rapport.", "reports", "TOP3_CHANGED"))
    if _int(pending_approvals):
        items.append(AttentionItem("warning", f"{_int(pending_approvals)} ventende godkjenninger", "Forslag venter på et eksplisitt valg.", "approvals", "PENDING_APPROVALS"))
    if scheduler_ok is False:
        items.append(AttentionItem("critical", "Planlegger krever oppmerksomhet", "Automatiske kjøringer rapporterer ikke normal status.", "jobs", "SCHEDULER_ERROR"))
    if not items:
        items.append(AttentionItem("ok", "Ingen kritiske oppgaver", "Siste rapport, planlegger og godkjenningsflyt har ingen kjente avvik.", "dashboard", "ALL_CLEAR"))
    priority = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
    items.sort(key=lambda x: (priority.get(x.severity, 9), x.title))
    return [item.to_dict() for item in items[: max(1, int(max_items or 7))]]


def candidate_action_payload(item: Mapping[str, Any] | None, decision: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = dict(item or {})
    dec = dict(decision or {})
    ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
    blockers = row.get("decision_blockers") or row.get("blockers") or dec.get("blockers") or dec.get("warnings") or []
    conditions = row.get("decision_change_conditions") or row.get("change_conditions") or dec.get("change_conditions") or dec.get("reasons") or []
    sources = row.get("source_evidence") or row.get("news_sources") or row.get("sources") or row.get("news") or []
    events = row.get("critical_events") or row.get("events") or row.get("event_calendar") or []
    history = row.get("decision_history") or row.get("history") or row.get("observations") or []
    if isinstance(blockers, str): blockers = [blockers]
    if isinstance(conditions, str): conditions = [conditions]
    if isinstance(sources, Mapping): sources = [dict(sources)]
    if isinstance(events, Mapping): events = [dict(events)]
    if isinstance(history, Mapping): history = [dict(history)]
    return {
        "ticker": ticker,
        "status": status_label(row.get("candidate_state") or row.get("status") or dec.get("decision"), str(dec.get("decision") or "")),
        "blockers": list(blockers or []),
        "change_conditions": list(conditions or []),
        "sources": list(sources or []),
        "events": list(events or []),
        "history": list(history or []),
        "score_delta": row.get("score_delta_since_previous") if row.get("score_delta_since_previous") is not None else row.get("score_delta"),
        "previous_score": row.get("previous_score"),
        "current_score": row.get("investment_score") if row.get("investment_score") is not None else row.get("score"),
        "export_json": json.dumps(row, ensure_ascii=False, indent=2, default=str),
    }
