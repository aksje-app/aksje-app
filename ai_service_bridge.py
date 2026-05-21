"""
ai_service_bridge.py

v18.5.15 UI bridge for service migration status and Smart Universe Picker.
"""

from __future__ import annotations

import streamlit as st

try:
    from services.service_registry import build_service_registry, get_service_registry
except ModuleNotFoundError as _svc_exc:  # pragma: no cover
    build_service_registry = None  # type: ignore
    get_service_registry = None  # type: ignore
    _SERVICE_IMPORT_ERROR = _svc_exc


PICKER_MODES = {
    "Enkeltaksje": ["Manuell liste"],
    "Top Picks": ["Top Picks"],
    "Watchlist": ["Watchlist"],
    "Portefølje": ["Portefølje"],
    "Paper trading": ["Paper trading"],
    "Marked": ["USA"],
    "Multi-marked": ["USA", "Norge", "Sverige"],
    "Manuell liste": ["Manuell liste"],
}


def _registry():
    if build_service_registry is not None:
        return build_service_registry(st.session_state)
    return get_service_registry()  # type: ignore[misc]


def render_service_migration_status() -> None:
    if globals().get("_SERVICE_IMPORT_ERROR") is not None:
        st.warning("Service-laget mangler: " + str(_SERVICE_IMPORT_ERROR))
        return
    reg = _registry()
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
    reg = _registry()
    st.markdown("### 🎯 Smart Universe Picker")
    st.caption(
        "Felles universvalg for enkeltaksje, Top Picks, Watchlist, portefølje, paper trading, marked, multi-marked og manuell liste."
    )

    c1, c2, c3 = st.columns([1.4, 1.4, 1.0])
    with c1:
        mode = st.selectbox(
            "Kilde",
            list(PICKER_MODES.keys()),
            index=5,
            key="service_universe_mode_v18515",
        )
    with c2:
        market = st.selectbox(
            "Marked / scope",
            ["USA", "Norge", "Sverige", "Alle"],
            index=0,
            key="service_universe_market_v18515",
            disabled=mode not in {"Marked"},
        )
    with c3:
        limit = st.number_input("Antall", min_value=1, max_value=250, value=30, step=1, key="service_universe_limit_v18515")

    manual_raw = ""
    if mode in {"Enkeltaksje", "Manuell liste"}:
        if str(st.session_state.get("service_universe_manual_v18515", "") or "").strip().upper() in {"AAPL", "AAPL,NVDA,MSFT", "AAPL,MSFT,NVDA", "STB.OL"}:
            st.session_state["service_universe_manual_v18515"] = ""
        manual_raw = st.text_input("Ticker(e)", value="", key="service_universe_manual_v18515", placeholder="Skriv ticker(e) ved behov")

    scopes = PICKER_MODES.get(mode, ["USA"])
    if mode == "Marked":
        scopes = [market]
    elif mode == "Enkeltaksje":
        scopes = ["Manuell liste"]
        manual_raw = manual_raw.split(",")[0] if manual_raw else ""

    config = {
        "mode": f"Smart Universe Picker: {mode}",
        "scopes": scopes,
        "manual_ticker": manual_raw if mode == "Enkeltaksje" else "",
        "max_count": int(limit),
        "metadata": {"manual_list": manual_raw if mode == "Manuell liste" else []},
    }
    result = reg.universe.resolve(config)
    if not result.ok:
        st.warning(result.message or "Klarte ikke hente univers.")
        return

    universe = result.data
    candidates = getattr(universe, "candidates", []) or []
    rows = [
        {
            "Rank": c.rank,
            "Ticker": c.ticker,
            "Kilde": c.source,
            "Forklaring": c.reason,
        }
        for c in candidates
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.session_state["smart_universe_candidates_v18515"] = [c.ticker for c in candidates]

    st.caption("Valgt univers er nå tilgjengelig for moduler som henter `smart_universe_candidates_v18515`.")


def render_service_workspace() -> None:
    with st.expander("🧩 Services / Smart Universe", expanded=False):
        render_service_migration_status()
        render_smart_universe_picker()
