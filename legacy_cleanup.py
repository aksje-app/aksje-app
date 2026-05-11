"""Legacy cleanup registry for Professional Trading Workspace.

v18.5.33 keeps AI Kontrollsenter as the single place for modules that used
 to appear in multiple standalone sections. The lists below are intentionally
small and explicit so smoke tests can verify that duplicate UI blocks stay
removed in future packages.
"""

from __future__ import annotations

REMOVED_MAIN_PANELS = [
    "🧪 Backtesting",
]

REMOVED_ANALYSIS_CARD_ACTIONS = [
    "Kjør strategi-test for {ticker}",
    "Strategi-optimalisering i per-ticker analyse",
]

AI_CONTROL_CENTER_SINGLE_SOURCES = {
    "Strategi-test": "AI Kontrollsenter → Testing & Learning",
    "Strategi-test Pro": "AI Kontrollsenter → Testing & Learning",
    "Prognose": "AI Kontrollsenter → Prognose",
    "Analyseunivers": "AI Kontrollsenter → Analyseunivers",
    "Varsler": "AI Kontrollsenter → Varsler",
}


def legacy_cleanup_status() -> dict:
    """Return a compact status payload for tests and Services smoke checks."""
    return {
        "version": "v18.5.33",
        "removed_main_panels": list(REMOVED_MAIN_PANELS),
        "removed_analysis_card_actions": list(REMOVED_ANALYSIS_CARD_ACTIONS),
        "single_sources": dict(AI_CONTROL_CENTER_SINGLE_SOURCES),
    }
