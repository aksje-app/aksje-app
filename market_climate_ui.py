from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st

from market_climate_engine import (
    DEFAULT_MARKET_CLIMATE_SYMBOLS,
    build_market_climate_snapshot,
    load_latest_market_climate_snapshot,
    market_climate_report_html,
    market_climate_to_csv,
    market_climate_to_json,
    save_market_climate_snapshot,
)


def _extract_column(df: Any, name: str, symbol: str) -> list[float]:
    try:
        column = df[name]
    except Exception:
        return []
    try:
        if hasattr(column, "columns"):
            if symbol in column.columns:
                column = column[symbol]
            elif len(column.columns) == 1:
                column = column.iloc[:, 0]
            else:
                column = column.select_dtypes(include="number").iloc[:, 0]
        if hasattr(column, "dropna"):
            column = column.dropna()
        out: list[float] = []
        for value in list(column):
            try:
                number = float(value)
                if number > 0:
                    out.append(number)
            except Exception:
                continue
        return out
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_market_series(symbol: str, period: str = "2y") -> tuple[dict[str, Any], str]:
    symbol = str(symbol or "").strip()
    if not symbol:
        return {}, "Mangler symbol"
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return {}, "yfinance er ikke tilgjengelig"
    try:
        df = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or getattr(df, "empty", True):
            return {}, f"Fant ingen data for {symbol}"
        close = _extract_column(df, "Close", symbol)
        volume = _extract_column(df, "Volume", symbol)
        dates = []
        try:
            dates = [getattr(idx, "strftime", lambda fmt: str(idx))("%Y-%m-%d") for idx in df.index][-len(close):]
        except Exception:
            dates = [str(i + 1) for i in range(len(close))]
        if len(close) < 40:
            return {"dates": dates, "close": close, "volume": volume}, f"For lite data for {symbol}"
        return {"dates": dates, "close": close, "volume": volume}, ""
    except Exception as exc:
        return {}, f"Klarte ikke hente {symbol}: {exc}"


def _text_float(label: str, key: str, placeholder: str) -> str:
    return st.text_input(label, key=key, placeholder=placeholder)


def _clean_manual_inputs(values: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in values.items():
        text = str(value or "").replace(",", ".").strip()
        if not text:
            continue
        try:
            out[key] = float(text)
        except Exception:
            out[key] = text
    return out


def _build_symbol_config_from_ui() -> list[dict[str, str]]:
    config = []
    st.caption("Symbolene kan justeres ved behov. Tomme symboler blir hoppet over.")
    cols = st.columns(4)
    for idx, item in enumerate(DEFAULT_MARKET_CLIMATE_SYMBOLS):
        with cols[idx % 4]:
            symbol = st.text_input(
                item["label"],
                value=item["symbol"],
                key=f"market_climate_symbol_v1864z_{item['key']}",
            )
        if str(symbol or "").strip():
            config.append({**item, "symbol": str(symbol).strip()})
    return config


def _run_market_climate_update(symbol_config: list[dict[str, str]], manual_inputs: Mapping[str, Any]) -> dict[str, Any]:
    series_map: dict[str, Any] = {}
    source_status = []
    for item in symbol_config:
        key = item.get("key", "")
        symbol = item.get("symbol", "")
        payload, error = _fetch_market_series(symbol, period="2y")
        series_map[key] = payload
        source_status.append(
            {
                "Kilde": item.get("label", key),
                "Symbol": symbol,
                "Status": "OK" if payload.get("close") and not error else ("Delvis" if payload.get("close") else "Mangler"),
                "Detalj": error or f"{len(payload.get('close') or [])} observasjoner",
            }
        )
    snapshot = build_market_climate_snapshot(
        series_map,
        manual_inputs=manual_inputs,
        symbol_config=symbol_config,
    )
    snapshot["source_status"] = source_status
    save_market_climate_snapshot(snapshot)
    st.session_state["market_climate_latest_v1864z"] = snapshot
    return snapshot


def _render_metric_row(snapshot: Mapping[str, Any]) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Markedsklima", f"{snapshot.get('climate_score', '-')}/100")
    m2.metric("Status", str(snapshot.get("label") or "-"))
    m3.metric("Confidence", f"{snapshot.get('confidence', '-')}%")
    m4.metric("Oppdatert", str(snapshot.get("created_at") or "-"))


def _render_factor_chart(snapshot: Mapping[str, Any]) -> None:
    rows = [row for row in snapshot.get("factor_rows") or [] if isinstance(row, Mapping)]
    if not rows:
        return
    try:
        import plotly.graph_objects as go

        names = [str(row.get("Faktor") or "") for row in rows]
        scores = [float(row.get("Score") or 0) for row in rows]
        colors = ["#16a34a" if score >= 70 else "#f59e0b" if score >= 45 else "#dc2626" for score in scores]
        fig = go.Figure(go.Bar(x=scores, y=names, orientation="h", marker_color=colors, text=[f"{s:.0f}" for s in scores], textposition="outside"))
        fig.update_layout(
            height=max(300, 42 * len(rows)),
            margin=dict(l=8, r=32, t=8, b=8),
            xaxis=dict(range=[0, 105], title="Score"),
            yaxis=dict(autorange="reversed"),
            template="plotly_white",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_market_chart(snapshot: Mapping[str, Any]) -> None:
    series = [row for row in snapshot.get("chart_series") or [] if isinstance(row, Mapping) and row.get("points")]
    if not series:
        st.caption("Ingen brede markedsserier klare for graf ennå.")
        return
    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        for row in series:
            points = [p for p in row.get("points") or [] if isinstance(p, Mapping)]
            fig.add_trace(
                go.Scatter(
                    x=[p.get("date") for p in points],
                    y=[p.get("value") for p in points],
                    mode="lines",
                    name=str(row.get("label") or row.get("key") or ""),
                )
            )
        fig.update_layout(
            height=340,
            margin=dict(l=8, r=8, t=28, b=8),
            title_text="Bredt marked normalisert til 100",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        st.caption("Graf kunne ikke vises, men dataene finnes i tabellen og eksporten.")


def _render_exports(snapshot: Mapping[str, Any]) -> None:
    basename = f"markedsklima_{str(snapshot.get('created_at') or 'snapshot').replace(':', '').replace('-', '')[:15]}"
    e1, e2, e3 = st.columns([0.22, 0.32, 0.28])
    with e1:
        st.download_button("CSV", data=market_climate_to_csv(snapshot), file_name=f"{basename}.csv", mime="text/csv")
    with e2:
        st.download_button("Print/PDF HTML", data=market_climate_report_html(snapshot), file_name=f"{basename}_rapport.html", mime="text/html")
    with e3:
        st.download_button("JSON snapshot", data=market_climate_to_json(snapshot), file_name=f"{basename}.json", mime="application/json")


def render_market_climate_panel() -> None:
    st.subheader("Markedsklima")
    st.caption("Makromodul for bred trend, volatilitet, renter, norsk klima, sentiment, IPO-trykk og verdsettelse. Runde 1 lagrer og rapporterer klima; Runde 2 kobler dette inn i AI Kandidattest-score.")

    with st.expander("Datakilder og manuelle klimaindikatorer", expanded=True):
        symbol_config = _build_symbol_config_from_ui()
        st.markdown("**Manuelle/importerte tall fra grafer eller eksterne kilder**")
        c1, c2, c3 = st.columns(3)
        with c1:
            us_ipo_count = _text_float("USA IPO-antall", "market_climate_us_ipo_count_v1864z", "f.eks. 260")
        with c2:
            osebx_pb = _text_float("OSEBX pris/bok", "market_climate_osebx_pb_v1864z", "f.eks. 2.35")
        with c3:
            bullish = _text_float("Bullish investorer %", "market_climate_bullish_pct_v1864z", "f.eks. 42")
        manual_inputs = _clean_manual_inputs(
            {
                "us_ipo_count": us_ipo_count,
                "osebx_price_book": osebx_pb,
                "aaii_bullish_pct": bullish,
            }
        )
        b1, b2 = st.columns([0.18, 0.82])
        with b1:
            run = st.button("Oppdater klima", key="market_climate_run_v1864z", type="primary")
        with b2:
            st.caption("Henter ferske proxyserier via yfinance når knappen trykkes. Manglende serier blir synlige som datamangler, ikke skjult.")
        if run:
            with st.spinner("Oppdaterer markedsklima..."):
                snapshot = _run_market_climate_update(symbol_config, manual_inputs)
            st.success(f"Markedsklima oppdatert: {snapshot.get('label')} ({snapshot.get('climate_score')}/100).")

    snapshot = st.session_state.get("market_climate_latest_v1864z") or load_latest_market_climate_snapshot()
    if not isinstance(snapshot, Mapping):
        st.info("Ingen markedsklima-snapshot er lagret ennå. Trykk Oppdater klima for å lage første rapport.")
        return

    _render_metric_row(snapshot)
    st.info(str(snapshot.get("action") or ""))
    st.caption(str(snapshot.get("round_note") or ""))

    tab1, tab2, tab3, tab4 = st.tabs(["Faktorer", "Markedsgrafer", "Datakilder", "Eksport"])
    with tab1:
        _render_factor_chart(snapshot)
        st.dataframe(pd.DataFrame(snapshot.get("factor_rows") or []), use_container_width=True, hide_index=True)
    with tab2:
        _render_market_chart(snapshot)
        st.dataframe(pd.DataFrame(snapshot.get("market_rows") or []), use_container_width=True, hide_index=True)
    with tab3:
        status_rows = snapshot.get("source_status") or []
        if status_rows:
            st.dataframe(pd.DataFrame(status_rows), use_container_width=True, hide_index=True)
        if snapshot.get("missing_factors"):
            st.warning("Mangler: " + ", ".join(str(x) for x in snapshot.get("missing_factors") or []))
        st.json(snapshot.get("manual_inputs") or {})
    with tab4:
        _render_exports(snapshot)
