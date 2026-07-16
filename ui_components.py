"""Legacy compatibility facade for shared UI components.

New code should import from :mod:`ui_library`. Existing imports remain valid.
"""

import streamlit as st

from ui_library import empty_state, kpi_row, page_header, render_table, section_header


def market_pulse(data):
    if not data:
        empty_state(st, "Ingen markedsdata", "Market Pulse vises når kursendringer er tilgjengelige.")
        return
    avg = sum(float(x.get("change_pct", 0) or 0) for x in data) / len(data)
    if avg > 1:
        txt, tone = "Bullish", "success"
    elif avg < -1:
        txt, tone = "Bearish", "danger"
    else:
        txt, tone = "Neutral", "warning"
    from ui_library import info_banner
    info_banner(st, f"Market Pulse: {txt}", f"Gjennomsnittlig markedsendring: {avg:.2f} %", tone)


def top_movers(data):
    rows = list(data or [])
    if not rows:
        empty_state(st, "Ingen bevegelser", "Topplisten fylles når markedsdata er tilgjengelige.")
        return
    gain = sorted(rows, key=lambda x: float(x.get("change_pct", 0) or 0), reverse=True)[:5]
    loss = sorted(rows, key=lambda x: float(x.get("change_pct", 0) or 0))[:5]
    c1, c2 = st.columns(2)
    with c1:
        section_header(st, "Største oppganger")
        render_table(st, [{"Ticker": x.get("ticker", "-"), "Endring %": round(float(x.get("change_pct", 0) or 0), 2)} for x in gain])
    with c2:
        section_header(st, "Største nedganger")
        render_table(st, [{"Ticker": x.get("ticker", "-"), "Endring %": round(float(x.get("change_pct", 0) or 0), 2)} for x in loss])
