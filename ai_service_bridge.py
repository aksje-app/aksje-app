"""
ai_service_bridge.py

v18.5.11 UI bridge for service migration status and Smart Universe Picker.
"""

from __future__ import annotations

import streamlit as st

from core_models import UniverseRequest
from services.service_registry import get_service_registry


def render_service_migration_status() -> None:
    reg = get_service_registry()
    st.markdown("### 🧩 Service Layer Status")
    checks = [
        ("UniverseService", reg.universe is not None),
        ("WatchlistService", reg.watchlist is not None),
        ("TopPicksService", reg.top_picks is not None),
        ("PaperTradingService", reg.paper_trading is not None),
        ("PortfolioService", reg.portfolio is not None),
        ("ForecastService", reg.forecast is not None),
        ("StorageService", reg.storage is not None),
        ("StateService", reg.state is not None),
    ]
    rows = [{"Service": name, "Status": "✅ Aktiv" if ok else "❌ Mangler"} for name, ok in checks]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_smart_universe_picker() -> None:
    reg = get_service_registry()
    st.markdown("### 🎯 Smart Universe Picker")
    st.caption("Felles valg av aksjeunivers via services. Brukes av Smart AI, Top Picks, Watchlist, Forecast, Paper og Portfolio.")

    c1, c2, c3 = st.columns(3)
    with c1:
        mode = st.selectbox(
            "Kilde",
            ["top_picks", "watchlist", "paper_trading", "portfolio", "market", "manual"],
            index=0,
            key="service_universe_mode_v18511",
        )
    with c2:
        market = st.selectbox(
            "Marked",
            ["all", "usa", "norway", "sweden", "denmark"],
            index=0,
            key="service_universe_market_v18511",
        )
    with c3:
        limit = st.number_input("Antall", min_value=1, max_value=50, value=10, step=1, key="service_universe_limit_v18511")

    manual = ""
    if mode == "manual":
        manual = st.text_input("Manuelle tickere", value="AAPL,NVDA,MSFT", key="service_universe_manual_v18511")

    request = UniverseRequest(
        mode=mode,
        market=market,
        tickers=[x.strip().upper() for x in manual.split(",") if x.strip()],
        limit=int(limit),
    )
    result = reg.universe.resolve(request)
    if not result.ok:
        st.warning(result.error or "Klarte ikke hente univers.")
        return

    candidates = result.data.candidates
    rows = [
        {
            "Ticker": c.ticker,
            "Market": c.market,
            "Score": round(c.score, 2),
            "Source": c.source,
        }
        for c in candidates
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.session_state["smart_universe_candidates_v18511"] = [c.ticker for c in candidates]


def render_service_workspace() -> None:
    with st.expander("🧩 Services / Smart Universe", expanded=False):
        render_service_migration_status()
        render_smart_universe_picker()
