from __future__ import annotations

from typing import Sequence

import streamlit as st

from services.analysis_pipeline_service import PIPELINE_PENDING_NAV_KEY


def open_ai_candidate_test(
    *,
    source: str = "Kombiner kilder",
    tickers: Sequence[str] | None = None,
    market: str | None = None,
) -> None:
    """Queue navigation to AI Kandidattest with a source or explicit ticker list."""
    clean_tickers = [
        str(ticker or "").strip().upper()
        for ticker in (tickers or [])
        if str(ticker or "").strip()
    ]
    clean_tickers = list(dict.fromkeys(clean_tickers))
    defaults = {"ai_candidate_source_v1864l": str(source or "Kombiner kilder")}
    if clean_tickers:
        defaults["ai_candidate_source_v1864l"] = "Manuell liste"
        defaults["ai_candidate_manual_v1864l"] = ", ".join(clean_tickers)
        defaults["ai_candidate_limit_v1864l"] = max(5, min(100, len(clean_tickers)))
    if market:
        defaults["ai_candidate_market_v1864l"] = str(market)
    st.session_state[PIPELINE_PENDING_NAV_KEY] = {
        "stage_id": "",
        "group": "AI Kandidattest",
        "panel": "AI Kandidattest",
        "defaults": defaults,
        "auto_run": False,
    }
