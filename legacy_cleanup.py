"""Legacy cleanup registry for Professional Trading Workspace.

This module is a visible contract for UI consolidation. It tells tests and
future cleanup work which old standalone panels are hidden, where the active
entry point now lives, and which old code paths are only cleanup candidates.
"""

from __future__ import annotations

from app_version import get_app_version

REMOVED_MAIN_PANELS = [
    "Backtesting",
    "Markedsklima",
    "IPO",
    "Nyheter",
    "Marked/rangering",
    "Watchlist/signaler",
    "Valutavarsler",
    "Intelligence",
    "Heatmaps",
    "Regime",
    "Makro/renter",
    "Services",
]

REMOVED_ANALYSIS_CARD_ACTIONS = [
    "Kjor strategi-test for {ticker}",
    "Strategi-optimalisering i per-ticker analyse",
]

AI_CONTROL_CENTER_SINGLE_SOURCES = {
    "Strategi-test": "AI Kontrollsenter -> Testing & Learning",
    "Strategi-test Pro": "AI Kontrollsenter -> Testing & Learning",
    "Prognose": "AI Kontrollsenter -> Prognose",
    "Analyseunivers": "AI Kontrollsenter -> Analyseunivers",
    "Varsler": "AI Kontrollsenter -> Varsler og watchlist -> Varselsenter",
    "Watchlist/signaler": "AI Kontrollsenter -> Varsler og watchlist -> Watchlist / signaler",
    "Valutavarsler": "AI Kontrollsenter -> Varsler og watchlist -> Valutavarsler",
    "Marked/rangering": "AI Kontrollsenter -> Marked -> Rangering",
    "Heatmaps": "AI Kontrollsenter -> Marked -> Heatmap",
    "Intelligence": "AI Kontrollsenter -> Marked -> Lagrede signaler",
    "Markedsklima": "AI Kontrollsenter -> Marked -> Markedsklima",
    "Regime": "AI Kontrollsenter -> Marked -> Regime",
    "Makro/renter": "AI Kontrollsenter -> Marked -> Makro",
    "Nyheter": "AI Kontrollsenter -> Marked -> Nyheter",
    "IPO": "AI Kontrollsenter -> Marked -> IPO",
    "Services": "Skjult teknisk status; beholdes for utviklerkontroll til cleanup-runden",
}

LEGACY_CLEANUP_CANDIDATES = [
    {
        "file": "workspace_layout.py",
        "area": "inactive control center renderers",
        "status": "prepare only",
        "why": "Older render_ai_control_center variants are no longer active but remain as rollback reference until full smoke coverage is stable.",
    },
    {
        "file": "app.py",
        "area": "duplicate currency-alert renderers",
        "status": "prepare only",
        "why": "render_currency_alerts_control_center_v1863af has older definitions before the final active definition. Remove only after targeted Pushover/currency tests.",
    },
    {
        "file": "app.py / workspace_layout.py",
        "area": "old standalone market panels",
        "status": "hidden from UI",
        "why": "Markedsklima, IPO, Nyheter, Market ranking, Heatmaps, Regime and Makro are now reached through Marked.",
    },
    {
        "file": "legacy pipeline modules",
        "area": "old Test 1-10 workflow labels",
        "status": "prepare only",
        "why": "Keep code until AI Kandidattest, Paper Trading and report/export flows have regression coverage across current use cases.",
    },
]


def legacy_cleanup_status() -> dict:
    """Return a compact status payload for tests and Services smoke checks."""
    return {
        "version": get_app_version(),
        "removed_main_panels": list(REMOVED_MAIN_PANELS),
        "removed_analysis_card_actions": list(REMOVED_ANALYSIS_CARD_ACTIONS),
        "single_sources": dict(AI_CONTROL_CENTER_SINGLE_SOURCES),
        "cleanup_candidates": list(LEGACY_CLEANUP_CANDIDATES),
    }
