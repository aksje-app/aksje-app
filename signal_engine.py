"""Compatibility facade for the v19.6.0 TechnicalSignalService.

Existing imports keep working, while the calculation now has one pure owner.
No signal thresholds or scoring rules changed in v19.6.0.
"""
from __future__ import annotations

from services.technical_signal_service import get_technical_signal_service


def score_signal(item, technical_context=None, insider=None, analyst=None, earnings=None):
    return get_technical_signal_service().evaluate(
        item or {}, technical_context or {}, insider=insider, analyst=analyst, earnings=earnings
    )


def calculate_signal_intelligence(item, technical_context=None, insider=None, analyst=None, earnings=None):
    return score_signal(item, technical_context, insider, analyst, earnings)


def explain_decision(decision):
    if not isinstance(decision, dict):
        return [], []
    return decision.get("reasons", []), decision.get("warnings", [])


def build_trading_decision(item, technical_context=None):
    return score_signal(item, technical_context or {})


# INSIDER_WEIGHT_GUIDANCE_V1
# Insider remains a support signal, never a standalone BUY trigger.
