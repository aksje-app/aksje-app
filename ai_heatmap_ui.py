"""
ai_heatmap_ui.py

UI for AI Heatmaps & Risk Visualization.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from ai_heatmap_engine import build_heatmap_rows, build_matrix_payload, build_sector_treemap_rows, extract_tickers_from_app_state, summarize_heatmap


def _level_icon(level: str) -> str:
    return {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(level, "⚪")


def _level_style(level: str) -> str:
    if level == "red":
        return "background:rgba(239,68,68,.22);border:1px solid rgba(239,68,68,.55);"
    if level == "yellow":
        return "background:rgba(245,158,11,.20);border:1px solid rgba(245,158,11,.55);"
    return "background:rgba(34,197,94,.18);border:1px solid rgba(34,197,94,.45);"


def _render_card(row: Dict[str, Any]) -> None:
    level = row.get("risk_level", "yellow")
    style = _level_style(level)
    icon = _level_icon(level)
    st.markdown(
        f"""
        <div style="{style} border-radius:12px; padding:.7rem .8rem; margin:.25rem 0;">
            <div style="font-weight:900;font-size:1.02rem;">{icon} {row.get('ticker','')} · {row.get('horizon','')}</div>
            <div>Strength: <b>{row.get('strength',0)}/100</b> · Confidence: <b>{row.get('confidence',0)}%</b></div>
            <div>Base: <b>{row.get('base_pct',0):+.2f}%</b> · Bear: <b>{row.get('bear_pct',0):+.2f}%</b></div>
            <div style="opacity:.85;">{row.get('risk_label','')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )




def _render_matrix_heatmap(rows: List[Dict[str, Any]]) -> None:
    st.markdown("### 🧩 Matrix Heatmap")
    payload = build_matrix_payload(rows)
    if not payload["tickers"] or not payload["horizons"]:
        st.caption("Ikke nok data for matrix heatmap.")
        return

    try:
        import plotly.graph_objects as go  # type: ignore

        fig = go.Figure(data=go.Heatmap(
            z=payload["z"],
            x=payload["horizons"],
            y=payload["tickers"],
            text=payload["text"],
            hoverinfo="text",
            colorscale=[
                [0.0, "rgba(239,68,68,0.95)"],
                [0.5, "rgba(245,158,11,0.95)"],
                [1.0, "rgba(34,197,94,0.95)"],
            ],
            zmin=0,
            zmax=100,
            colorbar=dict(title="Strength"),
        ))
        fig.update_layout(
            height=max(360, min(900, 38 * len(payload["tickers"]) + 120)),
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_title="Horisont",
            yaxis_title="Ticker",
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        # Fallback table
        table = []
        for r in rows:
            table.append({
                "Ticker": r.get("ticker"),
                "Horisont": r.get("horizon"),
                "Strength": r.get("strength"),
                "Risk": r.get("risk_label"),
            })
        st.dataframe(table, use_container_width=True, hide_index=True)


def _render_sector_treemap(rows: List[Dict[str, Any]]) -> None:
    st.markdown("### 🗺️ Sector / Group Treemap")
    sectors = build_sector_treemap_rows(rows)
    if not sectors:
        st.caption("Ikke nok data for sector treemap.")
        return

    try:
        import plotly.graph_objects as go  # type: ignore

        labels = [s["sector"] for s in sectors]
        values = [max(1, s["count"]) for s in sectors]
        colors = [s["avg_strength"] for s in sectors]
        custom = [
            f"Count: {s['count']}<br>Avg strength: {s['avg_strength']}/100<br>Avg confidence: {s['avg_confidence']}%<br>Avg bear: {s['avg_bear_pct']:+.2f}%<br>Red: {s['red']} · Yellow: {s['yellow']} · Green: {s['green']}"
            for s in sectors
        ]

        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=[""] * len(labels),
            values=values,
            marker=dict(
                colors=colors,
                colorscale=[
                    [0.0, "rgba(239,68,68,0.95)"],
                    [0.5, "rgba(245,158,11,0.95)"],
                    [1.0, "rgba(34,197,94,0.95)"],
                ],
                cmin=0,
                cmax=100,
                colorbar=dict(title="Avg strength"),
            ),
            textinfo="label+value",
            hovertext=custom,
            hoverinfo="text",
        ))
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.dataframe(sectors, use_container_width=True, hide_index=True)

def render_ai_heatmaps() -> None:
    """Render heatmap/risk visualization."""
    with st.expander("📊 AI Heatmaps & Risk Visualization", expanded=False):
        st.caption("Fargekodet oversikt over prognoser, risiko, confidence og strength. Ingen auto-trading-kobling.")

        all_tickers = extract_tickers_from_app_state(st.session_state)
        scope = st.selectbox(
            "Heatmap-kilde",
            options=["Alle lagrede prognoser", "Appdata: portefølje/watchlist/ranking"],
            index=0,
            key="ai_heatmap_scope_v1843",
        )

        source_filter = all_tickers if scope.startswith("Appdata") and all_tickers else None
        rows = build_heatmap_rows(source_tickers=source_filter, limit=300)
        summary = summarize_heatmap(rows)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Totalt", summary["total"])
        c2.metric("Røde", summary["counts"]["red"])
        c3.metric("Gule", summary["counts"]["yellow"])
        c4.metric("Grønne", summary["counts"]["green"])
        c5.metric("Avg strength", summary["avg_strength"])

        if not rows:
            st.info("Ingen heatmap-data ennå. Kjør noen prognoser først.")
            return

        view_mode = st.radio(
            "Visning",
            options=["Kort", "Matrix", "Sector treemap", "Alt"],
            horizontal=True,
            key="ai_heatmap_view_mode_v1845",
        )

        if view_mode in ("Matrix", "Alt"):
            _render_matrix_heatmap(rows)

        if view_mode in ("Sector treemap", "Alt"):
            _render_sector_treemap(rows)

        if view_mode in ("Kort", "Alt"):
            st.markdown("### Risikoheatmap")
        top_n = st.slider("Antall kort", 6, 40, 16, 2, key="ai_heatmap_topn_v1843")
        cols = st.columns(4)
        for i, row in enumerate(rows[:top_n]):
            with cols[i % 4]:
                _render_card(row)

        st.markdown("### Tabellvisning")
        table_rows = []
        for row in rows[:100]:
            table_rows.append({
                "Nivå": f"{_level_icon(row.get('risk_level'))} {row.get('risk_label')}",
                "Ticker": row.get("ticker"),
                "Horisont": row.get("horizon"),
                "Strength": f"{row.get('strength',0)}/100",
                "Confidence": f"{row.get('confidence',0)}%",
                "Base": f"{row.get('base_pct',0):+.2f}%",
                "Bull": f"{row.get('bull_pct',0):+.2f}%",
                "Bear": f"{row.get('bear_pct',0):+.2f}%",
                "Risiko": row.get("risk"),
                "Varselvekt": row.get("alert_weight", 0),
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        st.markdown("### Hvordan tolke fargene")
        st.markdown(
            """
            - 🟢 Grønn: sterk/lavere risiko, høyere strength/confidence.
            - 🟡 Gul: blandet signal eller moderat risiko.
            - 🔴 Rød: høy risiko, svak strength/confidence eller stort bear-scenario.
            """
        )
