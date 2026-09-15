"""Renderer-independent overview page model (v19.2.0)."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from daily_user_experience import build_attention_items

def build_overview_page(archive: Iterable[Mapping[str, Any]] | None, *, pending_approvals: int = 0, scheduler_ok: bool | None = None) -> dict[str, Any]:
    attention = build_attention_items(archive, pending_approvals=pending_approvals, scheduler_ok=scheduler_ok, max_items=7)
    priority = {"danger": 0, "critical": 0, "warning": 1, "info": 2, "success": 3, "ok": 3}
    normalized = []
    for item in attention:
        row = dict(item)
        severity = str(row.get("severity") or "info").lower()
        row["tone"] = "danger" if severity == "critical" else "success" if severity == "ok" else severity
        normalized.append(row)
    normalized.sort(key=lambda row: priority.get(str(row.get("tone")), 2))
    # An empty archive during a healthy scheduler bootstrap is an EMPTY state,
    # not an operational alarm. The report workspace still offers creation.
    if not list(archive or []) and scheduler_ok is True and pending_approvals == 0:
        normalized = []
    healthy = scheduler_ok is not False and pending_approvals == 0 and not any(row.get("tone") in {"danger", "warning"} for row in normalized)
    return {
        "page": "overview",
        "title": "Hva trenger oppmerksomhet nå?",
        "hero": {"title": "Systemet er klart" if healthy else "Noe trenger oppmerksomhet", "body": "Beslutninger og neste hendelse samlet på ett sted.", "tone": "success" if healthy else "warning"},
        "metrics": [{"label": "Ventende godkjenninger", "value": str(pending_approvals), "tone": "warning" if pending_approvals else "neutral"}, {"label": "Scheduler", "value": "OK" if scheduler_ok is not False else "Stoppet", "tone": "success" if scheduler_ok is not False else "danger"}],
        "attention_items": normalized,
        "recent_changes": list(archive or [])[:5],
        "next_event": {"label": "Neste planlagte rapport", "value": "Se rapporttidslinjen"},
        "actions": [
            {"label": "Kjør rapport", "nav": "reports"},
            {"label": "Åpne siste rapport", "nav": "reports"},
            {"label": "Se endringer", "nav": "reports"},
            {"label": "Behandle godkjenninger", "nav": "approvals"},
            {"label": "Åpne drift", "nav": "operations"},
        ],
    }

def render_overview(st_module, model: Mapping[str, Any]) -> None:
    from ui_library.components import action_bar, decision_cards, hero_status, metric_cards, page_state
    from ui_library.models import PageStateView
    hero = model.get("hero") or {}
    hero_status(st_module, title=str(hero.get("title") or model.get("title") or "Oversikt"), body=str(hero.get("body") or ""), module="overview", tone=str(hero.get("tone") or "neutral"))
    metric_cards(st_module, model.get("metrics") or [])
    attention = model.get("attention_items") or []
    if attention:
        decision_cards(st_module, [{"ticker": row.get("title") or "Oppgave", "decision": "REPLACE_REVIEW" if row.get("tone") == "warning" else "REJECTED" if row.get("tone") == "danger" else "HOLD", "reason": row.get("detail") or row.get("message") or "Se detaljer"} for row in attention])
    else:
        page_state(st_module, PageStateView.empty("Ingen oppgaver krever oppmerksomhet nå."))
    action_bar(st_module, [{"id": str(i), **dict(action)} for i, action in enumerate(model.get("actions") or [])])
