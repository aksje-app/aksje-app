"""Fail-closed transition detection for future verified quality alerts.

Manual Yahoo screening does not qualify for automatic investment alerts.
Receipt writing is deliberately separate from candidate evaluation, allowing
the existing notifier to record successful delivery before a state transition
can be acknowledged.
"""
from __future__ import annotations

from typing import Any, Mapping

from quality_valuation import GROUPS


def _verified_attractive(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if result.get("state") != "COMPLETED" or not result.get("shadow_only"):
        return {}
    return {
        str(item.get("ticker")): dict(item)
        for item in (result.get("groups") or {}).get(GROUPS[0], [])
        if item.get("evidence_ready") and item.get("valuation_basis_verified")
        and item.get("filings_verified") and item.get("market_drivers_verified")
    }


def transition_messages(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, str]]:
    """Only first entry or lost eligibility; never broadcast an unchanged list."""
    old = _verified_attractive(previous)
    new = _verified_attractive(current)
    events = []
    for ticker in sorted(new.keys() - old.keys()):
        events.append({"ticker": ticker, "kind": "NEW", "title": f"{ticker} · ny attraktiv kandidat",
                       "text": f"{ticker}: dokumentert verdsettelsesendring. Les vurdering og forutsetninger i programmet."})
    for ticker in sorted(old.keys() - new.keys()):
        events.append({"ticker": ticker, "kind": "LOST", "title": f"{ticker} · vurdering endret",
                       "text": f"{ticker}: oppfyller ikke lenger vilkårene for attraktiv kandidat. Kontroller ny vurdering."})
    return events
