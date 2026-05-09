"""
alert_center.py

Felles varselsenter:
- prognosevarsler
- porteføljevarsler
- paper trading/watchlist/ranking-varsler hvis data finnes
- ingen auto-trading-kobling
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from forecast_store import load_alerts, summarize_alerts


def _level_icon(level: str) -> str:
    level = (level or "").lower()
    if level == "red":
        return "🔴"
    if level == "yellow":
        return "🟡"
    if level == "green":
        return "🟢"
    return "⚪"


def _normalize_alert(alert: Dict[str, Any], source: str = "Prognose") -> Dict[str, Any]:
    row = dict(alert)
    row.setdefault("source", source)
    row.setdefault("level", "yellow")
    row.setdefault("category", "varsel")
    row.setdefault("ticker", "")
    row.setdefault("horizon", "")
    row.setdefault("message", "")
    return row


def collect_common_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    """Collect alerts from forecast log and simple app-state sources."""
    alerts: List[Dict[str, Any]] = []

    try:
        for alert in load_alerts(limit=limit):
            alerts.append(_normalize_alert(alert, source="Prognose"))
    except Exception:
        pass

    try:
        for key, source in [
            ("paper_portfolio", "Paper trading"),
            ("portfolio", "Portefølje"),
            ("holdings", "Portefølje"),
            ("positions", "Portefølje"),
            ("watchlist", "Watchlist"),
            ("top_picks", "AI-ranking"),
            ("ai_ranking", "AI-ranking"),
        ]:
            if key not in st.session_state:
                continue
            value = st.session_state.get(key)
            blob = str(value)
            if not blob or blob in ("{}", "[]", "None"):
                continue
            alerts.append(_normalize_alert({
                "level": "green",
                "category": "source_active",
                "ticker": "",
                "horizon": "",
                "message": f"{source} er tilgjengelig for prognose-/risikovarsler.",
            }, source=source))
    except Exception:
        pass

    seen = set()
    deduped: List[Dict[str, Any]] = []
    priority = {"red": 3, "yellow": 2, "green": 1}
    for alert in alerts:
        key = (
            alert.get("source"),
            alert.get("level"),
            alert.get("ticker"),
            alert.get("horizon"),
            alert.get("category"),
            alert.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)

    deduped.sort(key=lambda a: priority.get((a.get("level") or "").lower(), 0), reverse=True)
    return deduped[:limit]


def render_common_alert_center(location: str = "top") -> None:
    """Render one common alert center for the whole app."""
    alerts = collect_common_alerts(limit=100)
    summary = summarize_alerts(alerts) if alerts else {
        "counts": {"red": 0, "yellow": 0, "green": 0},
        "total": 0,
        "top_level": "green",
    }

    counts = summary.get("counts", {})
    red = int(counts.get("red", 0))
    yellow = int(counts.get("yellow", 0))
    green = int(counts.get("green", 0))
    total = int(summary.get("total", len(alerts)))

    if total == 0:
        st.info("🟢 Varselsenter: Ingen aktive prognose-/porteføljevarsler.")
        return

    headline = f"🚨 Varselsenter · 🔴 {red} · 🟡 {yellow} · 🟢 {green}"

    with st.expander(headline, expanded=(red > 0)):
        st.caption("Felles varsler fra prognose, portefølje, paper trading, watchlist og ranking der data finnes. Dette er beslutningsstøtte, ikke ordre.")

        by_source: Dict[str, int] = {}
        for alert in alerts:
            src = alert.get("source", "Ukjent")
            by_source[src] = by_source.get(src, 0) + 1

        if by_source:
            st.write("Kilder:")
            st.write(" · ".join([f"{src}: {count}" for src, count in sorted(by_source.items())]))

        rows = []
        for alert in alerts[:50]:
            rows.append({
                "Nivå": f"{_level_icon(alert.get('level'))} {alert.get('level', '').upper()}",
                "Kilde": alert.get("source", ""),
                "Ticker": alert.get("ticker", ""),
                "Horisont": alert.get("horizon", ""),
                "Kategori": alert.get("category", ""),
                "Melding": alert.get("message", ""),
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)
