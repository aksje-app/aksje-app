"""
macro_rates_breadth_ui.py

UI for Macro/Rates/Breadth Engine.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import streamlit as st

from macro_rates_breadth_engine import analyze_macro_rates_breadth, macro_adjustment_for_forecast


def _fetch_prices(ticker: str, period: str = "1y") -> Tuple[List[float], Optional[str]]:
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


def render_macro_rates_breadth_panel() -> None:
    with st.expander("🌐 Makro, renter og breadth", expanded=False):
        st.caption("Analyserer makro/rente/breadth-proxyer. Brukes som ekstra støtte til regime, prognoser og varsler.")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            spy = st.text_input("SPY", value="SPY", key="macro_spy_v1844")
            qqq = st.text_input("QQQ", value="QQQ", key="macro_qqq_v1844")
        with c2:
            iwm = st.text_input("IWM", value="IWM", key="macro_iwm_v1844")
            dia = st.text_input("DIA", value="DIA", key="macro_dia_v1844")
        with c3:
            tnx = st.text_input("10Y yield", value="^TNX", key="macro_tnx_v1844")
            dollar = st.text_input("Dollar proxy", value="UUP", key="macro_dollar_v1844")
        with c4:
            oil = st.text_input("Olje proxy", value="USO", key="macro_oil_v1844")
            vix = st.text_input("VIX", value="^VIX", key="macro_vix_v1844")

        run = st.button("Oppdater makro/rente/breadth", key="macro_run_v1844", width="stretch")
        if not run:
            existing = st.session_state.get("macro_rates_breadth_result_v1844")
            if existing:
                st.info(f"Siste makrostatus: {existing.get('label')} · score {existing.get('combined_score')}/100")
            return

        data = {}
        errors = []
        for name, ticker in [("spy", spy), ("qqq", qqq), ("iwm", iwm), ("dia", dia), ("tnx", tnx), ("dollar", dollar), ("oil", oil), ("vix", vix)]:
            prices, err = _fetch_prices(ticker, period="1y")
            if err and name == "spy":
                st.warning(err)
                return
            if err:
                errors.append(err)
                data[name] = []
            else:
                data[name] = prices

        result = analyze_macro_rates_breadth(
            spy_prices=data.get("spy", []),
            qqq_prices=data.get("qqq", []),
            iwm_prices=data.get("iwm", []),
            dia_prices=data.get("dia", []),
            tnx_prices=data.get("tnx", []),
            dollar_prices=data.get("dollar", []),
            oil_prices=data.get("oil", []),
            vix_prices=data.get("vix", []),
        )
        payload = result.to_dict()
        payload["forecast_adjustment"] = macro_adjustment_for_forecast(result)
        st.session_state["macro_rates_breadth_result_v1844"] = payload

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Makro", f"{result.macro_score}/100")
        m2.metric("Renter", f"{result.rate_score}/100")
        m3.metric("Breadth", f"{result.breadth_score}/100")
        m4.metric("Risiko", f"{result.risk_score}/100")
        m5.metric("Samlet", f"{result.combined_score}/100", result.risk_level)

        st.write(result.explanation)
        with st.expander('Avansert detaljdata', expanded=False):
            st.json(result.components)

        if errors:
            st.caption("Noen proxyer manglet: " + " | ".join(errors[:4]))
