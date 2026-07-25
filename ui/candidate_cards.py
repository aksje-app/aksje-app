"""Renderer-independent candidate-card model (v19.2.0)."""
from __future__ import annotations
from typing import Any, Mapping
from daily_user_experience import candidate_action_payload

def build_candidate_card(item: Mapping[str, Any], decision: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = candidate_action_payload(item, decision)
    payload["actions"] = (
        "analysis", "watchlist", "paper_trading", "refresh", "decision_diff", "counter_hypothesis", "sources", "events", "history", "export"
    )
    return payload
