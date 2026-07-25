"""Renderer-independent overview page model (v19.2.0)."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from daily_user_experience import build_attention_items

def build_overview_page(archive: Iterable[Mapping[str, Any]] | None, *, pending_approvals: int = 0, scheduler_ok: bool | None = None) -> dict[str, Any]:
    return {
        "page": "overview",
        "title": "Hva trenger oppmerksomhet nå?",
        "attention_items": build_attention_items(archive, pending_approvals=pending_approvals, scheduler_ok=scheduler_ok, max_items=7),
        "actions": [
            {"label": "Kjør rapport", "nav": "reports"},
            {"label": "Åpne siste rapport", "nav": "reports"},
            {"label": "Se endringer", "nav": "reports"},
            {"label": "Behandle godkjenninger", "nav": "approvals"},
            {"label": "Åpne drift", "nav": "operations"},
        ],
    }
