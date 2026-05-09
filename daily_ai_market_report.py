"""
daily_ai_market_report.py

Daily AI Market Report:
- daglig rapport basert på AI Market Intelligence Center, varsler, regime og prognoselogg
- ingen auto-trading-kobling
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import load_forecast_log, load_learning_stats, summarize_alerts


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_forecast_rows(limit: int = 300) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for payload in load_forecast_log(limit=limit):
            ticker = payload.get("ticker", "")
            saved_at = payload.get("saved_at") or payload.get("generated_at", "")
            for horizon, item in payload.get("horizons", {}).items():
                summary = item.get("summary", {})
                if not summary:
                    continue
                rows.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "saved_at": saved_at,
                    "base_pct": float(summary.get("base_pct", 0)),
                    "bull_pct": float(summary.get("bull_pct", 0)),
                    "bear_pct": float(summary.get("bear_pct", 0)),
                    "confidence": int(summary.get("confidence", 0)),
                    "strength": int(summary.get("forecast_strength", 0)),
                    "risk": summary.get("risk", ""),
                    "label": summary.get("forecast_strength_label", ""),
                })
    except Exception:
        return []

    latest: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        latest[(row["ticker"], row["horizon"])] = row
    return list(latest.values())


def _top(rows: List[Dict[str, Any]], reverse: bool = True, limit: int = 5) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (r.get("strength", 0), r.get("confidence", 0), r.get("base_pct", 0)),
        reverse=reverse,
    )[:limit]


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "0.00%"


def build_daily_market_report() -> Dict[str, Any]:
    alerts = collect_common_alerts(limit=100)
    alert_summary = summarize_alerts(alerts) if alerts else {
        "counts": {"red": 0, "yellow": 0, "green": 0},
        "total": 0,
    }
    forecasts = _extract_forecast_rows(limit=300)
    learning = load_learning_stats()

    try:
        auto_regime = st.session_state.get("market_regime_result_v1840")
    except Exception:
        auto_regime = None

    if isinstance(auto_regime, dict):
        regime_label = auto_regime.get("label", "Ukjent")
        regime_score = auto_regime.get("score", None)
        regime_confidence = auto_regime.get("confidence", None)
    else:
        regime_label = "Ikke oppdatert"
        regime_score = None
        regime_confidence = None

    counts = alert_summary.get("counts", {})
    try:
        macro_payload = st.session_state.get("macro_rates_breadth_result_v1844")
    except Exception:
        macro_payload = None

    return {
        "date": _today_key(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regime": {
            "label": regime_label,
            "score": regime_score,
            "confidence": regime_confidence,
        },
        "alerts": {
            "total": int(alert_summary.get("total", len(alerts))),
            "red": int(counts.get("red", 0)),
            "yellow": int(counts.get("yellow", 0)),
            "green": int(counts.get("green", 0)),
            "top": alerts[:10],
        },
        "forecasts": {
            "count": len(forecasts),
            "strongest": _top(forecasts, reverse=True, limit=5),
            "weakest": _top(forecasts, reverse=False, limit=5),
        },
        "learning": {
            "samples": int(learning.get("global", {}).get("count", 0)),
            "direction_accuracy": learning.get("global", {}).get("direction_accuracy"),
            "inside_band_accuracy": learning.get("global", {}).get("inside_band_accuracy"),
            "avg_abs_error_pct": learning.get("global", {}).get("avg_abs_error_pct"),
        },
        "macro": macro_payload if isinstance(macro_payload, dict) else {},
    }


def _rows_for_display(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        out.append({
            "Ticker": r.get("ticker", ""),
            "Horisont": r.get("horizon", ""),
            "Base": _fmt_pct(r.get("base_pct")),
            "Bull": _fmt_pct(r.get("bull_pct")),
            "Bear": _fmt_pct(r.get("bear_pct")),
            "Confidence": f"{r.get('confidence', 0)}%",
            "Strength": f"{r.get('strength', 0)}/100",
            "Risiko": r.get("risk", ""),
        })
    return out


def render_daily_ai_market_report() -> None:
    report_key = f"daily_ai_market_report::{_today_key()}"

    if report_key not in st.session_state:
        st.session_state[report_key] = build_daily_market_report()

    report = st.session_state[report_key]

    with st.expander("📈 Daily AI Market Report", expanded=False):
        st.caption("Daglig samlet AI-rapport. Oppdateres når appen åpnes eller når du trykker oppdater. Ingen auto-trading-kobling.")

        if st.button("Oppdater Daily AI Report", key="daily_ai_report_refresh_v1841", use_container_width=True):
            report = build_daily_market_report()
            st.session_state[report_key] = report

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Dato", report.get("date", ""))
        c2.metric("Regime", report.get("regime", {}).get("label", "Ukjent"))
        c3.metric("Varsler", report.get("alerts", {}).get("total", 0), f"🔴 {report.get('alerts', {}).get('red', 0)} · 🟡 {report.get('alerts', {}).get('yellow', 0)} · 🟢 {report.get('alerts', {}).get('green', 0)}")
        c4.metric("Prognoser", report.get("forecasts", {}).get("count", 0))
        c5.metric("Learning samples", report.get("learning", {}).get("samples", 0))

        st.markdown("### Dagens korte status")
        regime = report.get("regime", {})
        alerts = report.get("alerts", {})
        learning = report.get("learning", {})
        macro = report.get("macro", {})
        macro_txt = f" Makro: **{macro.get('label')}** ({macro.get('combined_score')}/100)." if macro else ""
        st.write(
            f"Marked: **{regime.get('label', 'Ukjent')}**." + macro_txt + " "
            f"Varsler: **{alerts.get('red', 0)} røde**, **{alerts.get('yellow', 0)} gule**, **{alerts.get('green', 0)} grønne**. "
            f"Læringsgrunnlag: **{learning.get('samples', 0)}** evaluerte punkter."
        )

        st.markdown("### Topp bullish / sterkeste prognoser")
        strongest = _rows_for_display(report.get("forecasts", {}).get("strongest", []))
        if strongest:
            st.dataframe(strongest, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen prognoser i loggen ennå.")

        st.markdown("### Topp risiko / svakeste prognoser")
        weakest = _rows_for_display(report.get("forecasts", {}).get("weakest", []))
        if weakest:
            st.dataframe(weakest, use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen risikopunkter tilgjengelig ennå.")

        st.markdown("### Viktigste varsler")
        top_alerts = report.get("alerts", {}).get("top", [])
        if top_alerts:
            rows = []
            for a in top_alerts:
                rows.append({
                    "Nivå": a.get("level", "").upper(),
                    "Kilde": a.get("source", ""),
                    "Ticker": a.get("ticker", ""),
                    "Horisont": a.get("horizon", ""),
                    "Kategori": a.get("category", ""),
                    "Melding": a.get("message", ""),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("Ingen viktige varsler akkurat nå.")

        st.markdown("### Hvordan bruke rapporten")
        st.markdown(
            """
            - Start med røde varsler.
            - Sjekk svakeste prognoser før nye kjøp.
            - Bruk sterkeste prognoser som kandidatliste, ikke fasit.
            - Se på regime før du tolker bull/base/bear.
            - Ikke koble dette direkte til auto trading uten backtest.
            """
        )
