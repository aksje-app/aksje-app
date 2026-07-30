from __future__ import annotations

import html
import io
from datetime import datetime
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from market_climate_engine import (
    DEFAULT_MARKET_CLIMATE_SYMBOLS,
    MARKET_CLIMATE_GRAPH_SOURCES,
    build_market_climate_snapshot,
    build_market_climate_graph_archive,
    load_latest_market_climate_snapshot,
    market_climate_graph_source_rows,
    market_climate_manual_indicator_rows,
    market_climate_report_html,
    market_climate_score_ranges,
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


def _graph_source_title(source_id: str) -> str:
    for item in MARKET_CLIMATE_GRAPH_SOURCES:
        if item.get("id") == source_id:
            return str(item.get("title") or source_id)
    return str(source_id)


def _table_records(df: pd.DataFrame, max_rows: int = 1000) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.copy()
    clean.columns = [str(col).strip() or f"kolonne_{idx + 1}" for idx, col in enumerate(clean.columns)]
    clean = clean.where(pd.notnull(clean), None)
    rows = clean.head(max_rows).to_dict(orient="records")
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({str(key): value for key, value in row.items()})
    return out


def _read_uploaded_graph_table(uploaded: Any) -> tuple[dict[str, Any] | None, str]:
    try:
        name = str(getattr(uploaded, "name", "") or "import")
        raw = uploaded.getvalue()
        suffix = name.lower().rsplit(".", 1)[-1] if "." in name else "csv"
        if suffix == "csv":
            df = pd.read_csv(io.BytesIO(raw))
        elif suffix in {"xlsx", "xls"}:
            df = pd.read_excel(io.BytesIO(raw))
        else:
            return None, "Støtter bare CSV, XLSX og XLS."
        rows = _table_records(df)
        if not rows:
            return None, "Filen ble lest, men ingen rader ble funnet."
        return {
            "filename": name,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
            "rows": rows,
            "columns": list(rows[0].keys()) if rows else [],
            "row_count": len(rows),
        }, ""
    except ImportError as exc:
        return None, f"Mangler Excel-bibliotek for denne filtypen: {exc}"
    except Exception as exc:
        return None, f"Klarte ikke lese filen: {exc}"


def _render_graph_source_links() -> None:
    st.markdown("**Hurtiglenker for manuelle/importerte grafer**")
    st.caption("Skjermbildene er bare referanser. Her åpner du stedet der underlaget bør hentes, og importerer CSV/XLSX eller legger inn siste verdi manuelt.")
    rows = market_climate_graph_source_rows()
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    link_lines: list[str] = []
    for item in MARKET_CLIMATE_GRAPH_SOURCES:
        links = [link for link in item.get("links") or [] if isinstance(link, Mapping)]
        if not links:
            continue
        joined = " | ".join(f"[{html.escape(str(link.get('label') or 'Kilde'))}]({link.get('url')})" for link in links)
        link_lines.append(f"- **{html.escape(str(item.get('title') or item.get('id')))}**: {joined}")
    if link_lines:
        st.markdown("\n".join(link_lines))


def _render_graph_import_controls() -> dict[str, Any]:
    st.markdown("**Importer graf-/tabellgrunnlag**")
    st.caption("Last opp CSV/XLSX/XLS og knytt filen til grafen den hører til. Importerte rader blir med i snapshot, CSV, JSON og Print/PDF HTML.")
    imports: dict[str, Any] = dict(st.session_state.get("market_climate_graph_imports_v1867") or {})
    source_ids = [str(item.get("id")) for item in MARKET_CLIMATE_GRAPH_SOURCES]
    uploads = st.file_uploader(
        "CSV/XLSX/XLS for grafarkiv",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key="market_climate_graph_archive_uploads_v1867",
    )
    for idx, uploaded in enumerate(uploads or []):
        source_id = st.selectbox(
            f"Knytt {getattr(uploaded, 'name', 'fil')} til",
            options=source_ids,
            format_func=_graph_source_title,
            key=f"market_climate_graph_archive_source_v1867_{idx}_{getattr(uploaded, 'name', 'fil')}",
        )
        payload, error = _read_uploaded_graph_table(uploaded)
        if error:
            st.warning(error)
            continue
        if payload:
            payload["source_id"] = source_id
            imports[source_id] = payload
            st.success(f"Importert {payload.get('row_count')} rader til {_graph_source_title(source_id)}.")
    if imports:
        summary = [
            {
                "Graf/tabell": _graph_source_title(source_id),
                "Fil": payload.get("filename"),
                "Rader": payload.get("row_count"),
                "Importert": payload.get("imported_at"),
            }
            for source_id, payload in imports.items()
            if isinstance(payload, Mapping)
        ]
        st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)
        if st.button("Tøm importerte grafdata", key="market_climate_clear_graph_imports_v1867"):
            imports = {}
            st.session_state["market_climate_graph_imports_v1867"] = {}
            st.info("Importerte grafdata er tømt fra denne økten.")
    st.session_state["market_climate_graph_imports_v1867"] = imports
    return imports


def _color_for_level(level: str) -> str:
    text = str(level or "").lower()
    if "rød" in text or "stress" in text or "høyt" in text or "svak" in text:
        return "#dc2626"
    if "oransje" in text or "press" in text or "strukket" in text:
        return "#f97316"
    if "gul" in text or "normal" in text or "blandet" in text or "ok" in text:
        return "#f59e0b"
    if "grønn" in text or "støtt" in text or "balansert" in text or "lavt" in text:
        return "#16a34a"
    return "#64748b"


def _level_table_html(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return "<p class='mc-muted'>Ingen nivådata.</p>"
    headers = ["Faktor", "Målt verdi", "Lavt nivå", "Normalt nivå", "Høyt nivå", "Nivå", "Score", "Tolkning"]
    head = "".join(f"<th>{html.escape(col)}</th>" for col in headers)
    body = []
    for row in rows:
        level = str(row.get("Nivå") or row.get("Status") or "-")
        color = _color_for_level(str(row.get("Farge") or level))
        cells = []
        for col in headers:
            value = row.get(col, "")
            if col == "Nivå":
                value_html = f"<span class='mc-pill' style='background:{color}'>{html.escape(level)}</span>"
            else:
                value_html = html.escape(str(value if value not in (None, "") else "-"))
            cells.append(f"<td>{value_html}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return "<table class='mc-level-table'><thead><tr>" + head + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"


def _render_level_style() -> None:
    st.markdown(
        """
        <style>
        .mc-summary-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin:.35rem 0 .7rem 0;}
        .mc-summary-card {border:1px solid rgba(148,163,184,.35);border-radius:10px;padding:.65rem .75rem;background:rgba(15,23,42,.36);}
        .mc-summary-label {font-size:.78rem;color:#cbd5e1;font-weight:800;margin-bottom:.15rem;}
        .mc-summary-value {font-size:1.08rem;color:#f8fafc;font-weight:950;}
        .mc-pill {display:inline-block;border-radius:999px;padding:.18rem .52rem;color:white;font-weight:900;white-space:nowrap;}
        .mc-level-table {border-collapse:collapse;width:100%;font-size:.86rem;margin:.4rem 0 1rem 0;background:#fff;color:#0f172a;border-radius:8px;overflow:hidden;}
        .mc-level-table th,.mc-level-table td {border:1px solid #d7dee8;padding:.46rem .55rem;text-align:left;vertical-align:top;}
        .mc-level-table th {background:#f3f6fa;color:#64748b;font-weight:850;}
        .mc-muted {color:#94a3b8;}
        @media(max-width:900px){.mc-summary-grid{grid-template-columns:1fr 1fr}.mc-level-table{font-size:.78rem}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_level_table(rows: list[Mapping[str, Any]], title: str | None = None) -> None:
    if title:
        st.markdown(f"**{title}**")
    st.markdown(_level_table_html(rows), unsafe_allow_html=True)


def _render_score_ranges() -> None:
    rows = [
        {
            "Faktor": "Samlet markedsklima",
            "Målt verdi": row.get("Score"),
            "Lavt nivå": "Rød/oransje = strengere motor",
            "Normalt nivå": "Gul = aksjesignalene må bære caset",
            "Høyt nivå": "Grønn = mer rom for vekst/momentum",
            "Nivå": row.get("Nivå"),
            "Score": row.get("Score"),
            "Tolkning": row.get("Tolkning"),
            "Farge": row.get("Nivå"),
        }
        for row in market_climate_score_ranges()
    ]
    _render_level_table(rows, "Samlet nivåskala")


def _render_manual_preview(manual_inputs: Mapping[str, Any]) -> None:
    rows = market_climate_manual_indicator_rows(manual_inputs)
    st.markdown("**Direkte tolkning av manuelle tall**")
    st.caption("Disse tre radene endrer seg med en gang du skriver i boksene. Trykk Oppdater klima for å lagre dem i snapshot og rapport.")
    _render_level_table(rows)


def _render_summary_cards(snapshot: Mapping[str, Any]) -> None:
    level = snapshot.get("climate_level") if isinstance(snapshot.get("climate_level"), Mapping) else {}
    color = str(level.get("Farge") or "#64748b")
    badge = str(level.get("Fargekode") or "-")
    cards = [
        ("Markedsklima", f"{snapshot.get('climate_score', '-')}/100"),
        ("Nivå", f"<span class='mc-pill' style='background:{color}'>{html.escape(badge)} - {html.escape(str(level.get('Nivå') or snapshot.get('label') or '-'))}</span>"),
        ("Confidence", f"{snapshot.get('confidence', '-')}%"),
        ("Oppdatert", html.escape(str(snapshot.get("created_at") or "-"))),
    ]
    html_cards = "".join(
        f"<div class='mc-summary-card'><div class='mc-summary-label'>{html.escape(label)}</div><div class='mc-summary-value'>{value}</div></div>"
        for label, value in cards
    )
    st.markdown(f"<div class='mc-summary-grid'>{html_cards}</div>", unsafe_allow_html=True)


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


def _run_market_climate_update(
    symbol_config: list[dict[str, str]],
    manual_inputs: Mapping[str, Any],
    graph_imports: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
        graph_imports=graph_imports or {},
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
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


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
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.caption("Graf kunne ikke vises, men dataene finnes i tabellen og eksporten.")


def _render_indicator_chart(snapshot: Mapping[str, Any]) -> None:
    series = [row for row in snapshot.get("indicator_chart_series") or [] if isinstance(row, Mapping) and row.get("points")]
    if not series:
        st.caption("Ingen klimaindikator-serier klare for graf ennå.")
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
            height=330,
            margin=dict(l=8, r=8, t=28, b=8),
            title_text="Volatilitet, renter, olje og valuta",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.caption("Indikatorgraf kunne ikke vises, men dataene finnes i tabellen og eksporten.")


def _render_imported_graph(entry: Mapping[str, Any]) -> None:
    rows = [dict(row) for row in entry.get("table_rows") or [] if isinstance(row, Mapping)]
    if not rows:
        st.caption("Ingen importert eller manuell tabell for denne grafen ennå.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)
    try:
        import plotly.graph_objects as go

        numeric_cols: list[str] = []
        for col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().sum() >= 1:
                numeric_cols.append(str(col))
        x_candidates = [col for col in df.columns if str(col).lower() in {"date", "dato", "year", "år", "month", "måned", "month_offset"}]
        x_col = str(x_candidates[0]) if x_candidates else str(df.columns[0])
        y_cols = [col for col in numeric_cols if col != x_col]
        if not y_cols:
            return
        fig = go.Figure()
        source_id = str(entry.get("id") or "")
        if source_id in {"us_ipo_count", "hormuz_oil_adjustment"} and len(y_cols) >= 1:
            for col in y_cols[:8]:
                fig.add_trace(go.Bar(x=df[x_col], y=pd.to_numeric(df[col], errors="coerce"), name=col))
            if source_id == "hormuz_oil_adjustment":
                fig.update_layout(barmode="stack")
        else:
            for col in y_cols[:6]:
                fig.add_trace(go.Scatter(x=df[x_col], y=pd.to_numeric(df[col], errors="coerce"), mode="lines+markers", name=col))
        fig.update_layout(
            height=300,
            margin=dict(l=8, r=8, t=28, b=8),
            title_text=str(entry.get("Graf/tabell") or "Importert graf"),
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except Exception:
        st.caption("Graf kunne ikke tegnes automatisk, men tabellen er importert og blir med i rapporten.")


def _render_graph_archive(snapshot: Mapping[str, Any]) -> None:
    archive = snapshot.get("graph_archive") or build_market_climate_graph_archive(snapshot)
    rows = []
    for item in archive:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Graf/tabell": item.get("Graf/tabell"),
                "Status": item.get("Status"),
                "Detalj": item.get("Detalj"),
                "Kildetype": item.get("Kildetype"),
                "Brukes til": item.get("Brukes til"),
                "Lavt nivå": item.get("Lavt nivå"),
                "Normalt nivå": item.get("Normalt nivå"),
                "Høyt nivå": item.get("Høyt nivå"),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    source_map = {str(item.get("id")): item for item in archive if isinstance(item, Mapping)}
    source_id = st.selectbox(
        "Vis graf/tabell",
        options=[str(item.get("id")) for item in archive if isinstance(item, Mapping)],
        format_func=_graph_source_title,
        key="market_climate_graph_archive_view_v1867",
    )
    entry = source_map.get(source_id, {})
    if not entry:
        return
    st.markdown(f"**{entry.get('Graf/tabell')}**")
    st.caption(str(entry.get("Hva skal hentes") or ""))
    st.caption(f"Forventet format: {entry.get('Forventet format') or '-'}")
    st.caption(f"Lavt: {entry.get('Lavt nivå') or '-'} | Normalt: {entry.get('Normalt nivå') or '-'} | Høyt: {entry.get('Høyt nivå') or '-'}")
    links = [link for link in entry.get("links") or [] if isinstance(link, Mapping)]
    if links:
        st.markdown(" | ".join(f"[{html.escape(str(link.get('label') or 'Kilde'))}]({link.get('url')})" for link in links))
    if entry.get("chart_series"):
        if source_id == "broad_market_normalized":
            _render_market_chart({"chart_series": entry.get("chart_series")})
        elif source_id == "volatility_rates_oil_currency":
            _render_indicator_chart({"indicator_chart_series": entry.get("chart_series")})
    _render_imported_graph(entry)


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
    _render_level_style()
    st.subheader("Markedsklima")
    st.caption("Makromodul for bred trend, volatilitet, renter, norsk klima, sentiment, IPO-trykk og verdsettelse. Snapshotet kan brukes som info eller scoreeffekt i AI Kandidattest.")

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
        _render_manual_preview(manual_inputs)
        _render_graph_source_links()
        graph_imports = _render_graph_import_controls()
        b1, b2 = st.columns([0.18, 0.82])
        with b1:
            run = st.button("Oppdater klima", key="market_climate_run_v1864z", type="primary")
        with b2:
            st.caption("Henter ferske proxyserier via yfinance når knappen trykkes. Manglende serier blir synlige som datamangler, ikke skjult.")
        if run:
            with st.spinner("Oppdaterer markedsklima..."):
                snapshot = _run_market_climate_update(symbol_config, manual_inputs, graph_imports)
            st.success(f"Markedsklima oppdatert: {snapshot.get('label')} ({snapshot.get('climate_score')}/100).")

    snapshot = st.session_state.get("market_climate_latest_v1864z") or load_latest_market_climate_snapshot()
    if not isinstance(snapshot, Mapping):
        st.info("Ingen markedsklima-snapshot er lagret ennå. Trykk Oppdater klima for å lage første rapport.")
        return
    if not snapshot.get("graph_archive"):
        snapshot = dict(snapshot)
        snapshot["graph_archive"] = build_market_climate_graph_archive(snapshot)

    _render_summary_cards(snapshot)
    st.info(str(snapshot.get("action") or ""))
    st.caption(str(snapshot.get("round_note") or ""))

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Nivåer", "Faktorer", "Grafer", "Grafarkiv", "Datakilder", "Eksport"])
    with tab1:
        _render_score_ranges()
        _render_level_table([row for row in snapshot.get("level_rows") or [] if isinstance(row, Mapping)], "Lavt / normalt / høyt per faktor")
        _render_level_table([row for row in snapshot.get("manual_indicator_rows") or [] if isinstance(row, Mapping)], "Manuelle/importerte indikatorer i snapshot")
    with tab2:
        _render_factor_chart(snapshot)
        st.dataframe(pd.DataFrame(snapshot.get("factor_rows") or []), width="stretch", hide_index=True)
    with tab3:
        _render_market_chart(snapshot)
        _render_indicator_chart(snapshot)
        st.dataframe(pd.DataFrame(snapshot.get("market_rows") or []), width="stretch", hide_index=True)
    with tab4:
        _render_graph_archive(snapshot)
    with tab5:
        status_rows = snapshot.get("source_status") or []
        if status_rows:
            st.dataframe(pd.DataFrame(status_rows), width="stretch", hide_index=True)
        if snapshot.get("missing_factors"):
            st.warning("Mangler: " + ", ".join(str(x) for x in snapshot.get("missing_factors") or []))
        st.json(snapshot.get("manual_inputs") or {})
    with tab6:
        _render_exports(snapshot)
