"""
market_regime_ui.py

UI for automatisk markedsregime-deteksjon.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import streamlit as st

from market_regime_engine import detect_market_regime, regime_to_forecast_inputs

REGIME_PRESETS = {
    "USA": ("SPY", "QQQ", "^VIX"),
    "Norge": ("OBX.OL", "EQNR.OL", ""),
    "Sverige": ("^OMX", "VOLV-B.ST", ""),
    "Danmark": ("NOVO-B.CO", "OMXC25.CO", ""),
    "Finland": ("NOKIA.HE", "SAMPO.HE", ""),
    "Brasil": ("EWZ", "^BVSP", ""),
    "Norden": ("OBX.OL", "NOVO-B.CO", ""),
    "Egendefinert": ("SPY", "QQQ", "^VIX"),
}


def _fetch_prices(ticker: str, period: str = "6mo") -> Tuple[List[float], Optional[str]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return [], "yfinance er ikke tilgjengelig."

    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return [], f"Fant ingen data for {ticker}."

        close = df["Close"]
        if hasattr(close, "columns"):
            if ticker in close.columns:
                close = close[ticker]
            elif len(close.columns) == 1:
                close = close.iloc[:, 0]
            else:
                close = close.select_dtypes(include="number").iloc[:, 0]
        if hasattr(close, "dropna"):
            close = close.dropna()

        prices = []
        for x in list(close):
            try:
                prices.append(float(x))
            except Exception:
                continue
        if len(prices) < 40:
            return [], f"For lite data for {ticker}."
        return prices, None
    except Exception as exc:
        return [], f"Klarte ikke hente {ticker}: {exc}"


def render_market_regime_widget() -> None:
    """Render automatic market regime widget."""
    with st.expander("🌍 Automatisk markedsregime", expanded=False):
        st.caption("Analyserer markedsklima for valgt marked. Brukes som beslutningsstotte for prognoser og varsler.")

        market_scope = st.selectbox("Marked/regimeomraade", list(REGIME_PRESETS.keys()), key="regime_market_scope_v1863ae")
        default_spy, default_qqq, default_vix = REGIME_PRESETS.get(market_scope, REGIME_PRESETS["USA"])
        c1, c2, c3 = st.columns(3)
        with c1:
            spy_ticker = st.text_input("Markedsproxy", value=default_spy, key=f"regime_spy_v1863ae_{market_scope}")
        with c2:
            qqq_ticker = st.text_input("Momentum/sekundaer proxy", value=default_qqq, key=f"regime_qqq_v1863ae_{market_scope}")
        with c3:
            vix_ticker = st.text_input("Volatilitet", value=default_vix, key=f"regime_vix_v1863ae_{market_scope}", help="Tomt felt betyr at regime beregnes uten volatilitetsproxy.")

        run = st.button("Oppdater markedsregime", key="regime_run_v1840", width="stretch")
        if not run:
            existing = st.session_state.get("market_regime_result_v1840")
            if existing:
                st.info(f"Siste regime: {existing.get('label')} · score {existing.get('score')}/100")
            return

        spy, err_spy = _fetch_prices(spy_ticker, period="1y")
        qqq, err_qqq = _fetch_prices(qqq_ticker, period="1y")
        vix, err_vix = _fetch_prices(vix_ticker, period="6mo") if str(vix_ticker or "").strip() else ([], None)

        if err_spy:
            st.warning(err_spy)
            return
        if err_qqq:
            st.caption(err_qqq + " Bruker SPY som fallback.")
            qqq = spy
        if err_vix:
            st.caption(err_vix + " Fortsetter uten VIX.")
            vix = []

        try:
            result = detect_market_regime(spy, qqq, vix)
        except Exception as exc:
            st.warning(f"Klarte ikke beregne markedsregime: {exc}")
            return

        payload = result.to_dict()
        payload.update(regime_to_forecast_inputs(result))
        payload["market_scope"] = market_scope
        payload["market_proxy"] = spy_ticker
        payload["momentum_proxy"] = qqq_ticker
        payload["volatility_proxy"] = vix_ticker
        st.session_state["market_regime_result_v1840"] = payload
        st.session_state["auto_market_regime_v1840"] = payload.get("market_regime", "neutral")
        st.session_state["auto_event_risk_v1840"] = payload.get("event_risk", False)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Regime", result.label)
        m2.metric("Score", f"{result.score}/100")
        m3.metric("Confidence", f"{result.confidence}%")
        m4.metric("Risiko", result.risk_level)
        m5.metric("VIX", f"{result.vix_level}" if result.vix_level is not None else "N/A")

        st.write(f"{market_scope}: {result.explanation}")
        with st.expander("Avansert detaljdata (lukket)", expanded=False):
            rows = [
                ("SPY 1 måned", f"{result.components.get('spy_1m_pct', 0):+.2f}%", "Kort trend i bredt USA-marked."),
                ("SPY 3 måneder", f"{result.components.get('spy_3m_pct', 0):+.2f}%", "Mellomlang trend i bredt USA-marked."),
                ("QQQ 1 måned", f"{result.components.get('qqq_1m_pct', 0):+.2f}%", "Kort trend i teknologi/momentum."),
                ("QQQ 3 måneder", f"{result.components.get('qqq_3m_pct', 0):+.2f}%", "Mellomlang trend i teknologi/momentum."),
                ("VIX 1 måned", f"{result.components.get('vix_1m_pct', 0):+.2f}%", "Endring i frykt/volatilitet. Høyere VIX trekker risiko opp."),
            ]
            for label, value, explanation in rows:
                st.markdown(
                    f"""
                    <div style="border:1px solid rgba(125,211,252,.22);border-radius:10px;padding:.55rem .70rem;margin:.35rem 0;background:rgba(8,20,42,.58);">
                        <div style="font-weight:950;color:#f8fafc;">{label}: {value}</div>
                        <div style="font-size:.84rem;color:#cbd5e1;line-height:1.28;">{explanation}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
