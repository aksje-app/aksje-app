"""
daily_ai_market_report.py

v18.6.2:
- Daily Report is input-driven instead of forecast-cache-driven.
- Candidate resolver reads ranking/watchlist/portfolio/manual sources from session_state.
- Forecast cache is used only after candidates are resolved and is filtered to those candidates.
- Alerts can be marked reviewed so the badge/report stops showing already handled items.
"""
from __future__ import annotations
import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Iterable, Tuple
import hashlib

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import load_forecast_log, load_learning_stats, summarize_alerts
from security_metadata import infer_security_listing, resolve_security_metadata, standard_market_options
from universe_engine import resolve_universe_tickers

VERSION_MARKER = "v18.6.2-daily-report-resolver"

LEGACY_MANUAL_DEFAULTS_V1863AL = {"AAPL,MSFT,NVDA", "AAPL,NVDA,MSFT", "AAPL", "STB.OL"}


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _norm_ticker(value: Any) -> str:
    raw = str(value or "").strip().upper()
    for sep in [",", ";", "|", "/"]:
        if sep in raw:
            raw = raw.split(sep)[0].strip()
            break
    return raw


def _alert_id(a: Dict[str, Any]) -> str:
    basis = "|".join(str(a.get(k, "")) for k in ["level", "source", "ticker", "horizon", "category", "message"])
    return hashlib.sha1(basis.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _filter_reviewed_alerts(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reviewed = st.session_state.setdefault("daily_report_reviewed_alert_ids_v1862", set())
    if not isinstance(reviewed, set):
        reviewed = set(reviewed or [])
        st.session_state["daily_report_reviewed_alert_ids_v1862"] = reviewed
    return [a for a in alerts if _alert_id(a) not in reviewed]


def _mark_alerts_reviewed(alerts: List[Dict[str, Any]]) -> None:
    reviewed = st.session_state.setdefault("daily_report_reviewed_alert_ids_v1862", set())
    if not isinstance(reviewed, set):
        reviewed = set(reviewed or [])
    reviewed.update(_alert_id(a) for a in alerts)
    st.session_state["daily_report_reviewed_alert_ids_v1862"] = reviewed


def _as_candidate(row: Any, source: str) -> Dict[str, Any] | None:
    if isinstance(row, dict):
        ticker = _norm_ticker(row.get("ticker") or row.get("Ticker") or row.get("symbol") or row.get("Symbol"))
        if not ticker:
            return None
        return {
            "ticker": ticker,
            "source": source or row.get("source", ""),
            "score": row.get("score", row.get("Score", row.get("ai_score", ""))),
            "confidence": row.get("confidence", row.get("Confidence", "")),
            "recommendation": row.get("recommendation", row.get("Recommendation", row.get("action", ""))),
            "market": row.get("market", row.get("Market", "")),
        }
    ticker = _norm_ticker(row)
    if ticker:
        return {"ticker": ticker, "source": source, "score": "", "confidence": "", "recommendation": "", "market": ""}
    return None


def _dedupe(candidates: Iterable[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for c in candidates:
        ticker = _norm_ticker(c.get("ticker"))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        c = dict(c)
        c["ticker"] = ticker
        out.append(c)
        if len(out) >= int(limit or 20):
            break
    return out


def _manual_tickers(raw: str) -> List[str]:
    vals = []
    for part in str(raw or "").replace(";", ",").replace("/", ",").replace("|", ",").split(","):
        t = _norm_ticker(part)
        if t:
            vals.append(t)
    return vals


def _session_candidates_from_latest(markets: List[str], top_n: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    latest = st.session_state.get("latest_rankings_v148", {}) or {}
    diagnostics: List[str] = []
    keys: List[str] = []
    if "Alle" in markets:
        keys = ["USA", "Norge", "Sverige", "TopPicks_USA", "TopPicks_Norge", "TopPicks_Sverige", "TopPicks_Alle", "Dynamisk watchlist / best rangerte", "Smart Universe Picker"]
    else:
        for m in markets:
            if m == "USA":
                keys += ["USA", "TopPicks_USA"]
            elif m == "Norge":
                keys += ["Norge", "TopPicks_Norge"]
            elif m == "Sverige":
                keys += ["Sverige", "TopPicks_Sverige"]
            elif m == "Norden":
                keys += ["Norge", "Sverige", "TopPicks_Norge", "TopPicks_Sverige"]
            elif m == "Top Picks":
                keys += ["TopPicks_USA", "TopPicks_Norge", "TopPicks_Sverige", "TopPicks_Alle"]
            elif m in {"Watchlist", "Paper trading", "Portefølje"}:
                keys += [m, "Dynamisk watchlist / best rangerte", "Smart Universe Picker"]
    rows: List[Dict[str, Any]] = []
    for key in keys:
        data = latest.get(key) or []
        diagnostics.append(f"{key}: {len(data) if hasattr(data, '__len__') else 0}")
        for r in data:
            c = _as_candidate(r, key)
            if c:
                rows.append(c)
    return _dedupe(rows, top_n), diagnostics


def resolve_report_candidates(focus: str, market: str, top_n: int, manual: str = "") -> Tuple[List[Dict[str, Any]], List[str]]:
    """Resolve candidate tickers for the report. Never silently falls back to STB.OL forecast cache."""
    focus = str(focus or "Ranking toppkandidater")
    market = str(market or "Alle")
    markets = [market] if market != "Alle" else ["Alle"]
    diagnostics: List[str] = []

    if focus == "Manuelle tickere":
        return _dedupe((_as_candidate(t, "Manuell") for t in _manual_tickers(manual)), top_n), ["Manuell input"]

    if focus == "Min portefølje":
        rows: List[Dict[str, Any]] = []
        # Streamlit tables used in this app often live in session_state after paper/portfolio render.
        for key in ["positions", "portfolio_positions", "paper_positions_v15", "paper_positions", "current_positions_v15"]:
            data = st.session_state.get(key)
            if isinstance(data, list):
                for r in data:
                    c = _as_candidate(r, key)
                    if c:
                        rows.append(c)
            elif hasattr(data, "to_dict"):
                try:
                    for r in data.to_dict("records"):
                        c = _as_candidate(r, key)
                        if c:
                            rows.append(c)
                except Exception as e:
                    logging.warning("Silenced exception restored in v18.6.3: %s", e)
        if rows:
            return _dedupe(rows, top_n), ["Portefølje fra session_state"]
        diagnostics.append("Ingen portefølje funnet i session_state")

    if focus == "Watchlist":
        rows: List[Dict[str, Any]] = []
        for key in ["watchlist_tickers", "dynamic_watchlist", "watchlist", "selected_watchlist_tickers_v15"]:
            data = st.session_state.get(key)
            if isinstance(data, (list, tuple, set)):
                for r in data:
                    c = _as_candidate(r, key)
                    if c:
                        rows.append(c)
        if rows:
            return _dedupe(rows, top_n), ["Watchlist fra session_state"]
        diagnostics.append("Ingen watchlist funnet i session_state")

    # Ranking and whole-market focus read latest rankings first.
    ranking_candidates, rank_diag = _session_candidates_from_latest(markets, top_n)
    diagnostics.extend(rank_diag)
    if ranking_candidates:
        return ranking_candidates, diagnostics

    if focus == "Hele markedet":
        market_scopes = ["Alle"] if market == "Alle" else [market]
        universe_rows = _dedupe((_as_candidate(t, f"Markedsunivers: {market}") for t in resolve_universe_tickers(market_scopes, max_count=top_n)), top_n)
        if universe_rows:
            diagnostics.append(f"Bruker markedsunivers for {market}")
            return universe_rows, diagnostics

    diagnostics.append("Ingen kandidater funnet fra valgt kilde. Manuelle tickere brukes bare naar fokus er Manuelle tickere.")

    return [], diagnostics


def _extract_forecast_rows(limit: int = 300) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for payload in load_forecast_log(limit=limit):
            ticker = _norm_ticker(payload.get("ticker", ""))
            saved_at = payload.get("saved_at") or payload.get("generated_at", "")
            for horizon, item in payload.get("horizons", {}).items():
                summary = item.get("summary", {}) if isinstance(item, dict) else {}
                if not summary:
                    continue
                rows.append({
                    "ticker": ticker,
                    "horizon": str(horizon),
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


def _filter_forecasts(rows: List[Dict[str, Any]], candidates: List[Dict[str, Any]], horizons: List[str], unique: bool) -> List[Dict[str, Any]]:
    allowed = {_norm_ticker(c.get("ticker")) for c in candidates if c.get("ticker")}
    h_allowed = {str(h).strip() for h in horizons if str(h).strip()}
    out = [r for r in rows if _norm_ticker(r.get("ticker")) in allowed and (not h_allowed or str(r.get("horizon")) in h_allowed)]
    out = sorted(out, key=lambda r: (r.get("strength", 0), r.get("confidence", 0), r.get("base_pct", 0)), reverse=True)
    if unique:
        seen = set()
        uniq = []
        for r in out:
            t = _norm_ticker(r.get("ticker"))
            if t in seen:
                continue
            seen.add(t)
            uniq.append(r)
        out = uniq
    return out


def _top(rows: List[Dict[str, Any]], reverse: bool = True, limit: int = 5) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: (r.get("strength", 0), r.get("confidence", 0), r.get("base_pct", 0)), reverse=reverse)[:limit]


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "0.00%"


def build_daily_market_report(focus: str = "Ranking toppkandidater", market: str = "Alle", top_n: int = 20, horizons: List[str] | None = None, unique: bool = True, manual: str = "") -> Dict[str, Any]:
    all_alerts = collect_common_alerts(limit=100)
    alerts = _filter_reviewed_alerts(all_alerts)
    alert_summary = summarize_alerts(alerts) if alerts else {"counts": {"red": 0, "yellow": 0, "green": 0}, "total": 0}
    candidates, diagnostics = resolve_report_candidates(focus, market, top_n, manual)
    all_forecasts = _extract_forecast_rows(limit=400)
    filtered_forecasts = _filter_forecasts(all_forecasts, candidates, horizons or [], unique)
    learning = load_learning_stats()

    auto_regime = st.session_state.get("market_regime_result_v1840")
    if isinstance(auto_regime, dict):
        regime_label = auto_regime.get("label", "Ukjent")
        regime_score = auto_regime.get("score", None)
        regime_confidence = auto_regime.get("confidence", None)
    else:
        regime_label = "Ikke oppdatert"
        regime_score = None
        regime_confidence = None
    counts = alert_summary.get("counts", {})
    macro_payload = st.session_state.get("macro_rates_breadth_result_v1844")

    return {
        "date": _today_key(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {"focus": focus, "market": market, "top_n": top_n, "horizons": horizons or [], "unique": unique, "manual": manual},
        "diagnostics": diagnostics,
        "candidates": candidates,
        "regime": {"label": regime_label, "score": regime_score, "confidence": regime_confidence},
        "alerts": {"total": int(alert_summary.get("total", len(alerts))), "red": int(counts.get("red", 0)), "yellow": int(counts.get("yellow", 0)), "green": int(counts.get("green", 0)), "top": alerts[:10]},
        "forecasts": {"count": len(filtered_forecasts), "strongest": _top(filtered_forecasts, True, 10), "weakest": _top(filtered_forecasts, False, 10), "all": filtered_forecasts},
        "learning": {"samples": int(learning.get("global", {}).get("count", 0)), "direction_accuracy": learning.get("global", {}).get("direction_accuracy"), "inside_band_accuracy": learning.get("global", {}).get("inside_band_accuracy"), "avg_abs_error_pct": learning.get("global", {}).get("avg_abs_error_pct")},
        "macro": macro_payload if isinstance(macro_payload, dict) else {},
    }


def _rows_for_display(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        meta = resolve_security_metadata(r.get("ticker"), r)
        listing = infer_security_listing(r.get("ticker"), r)
        out.append({"Ticker": r.get("ticker", ""), "Navn": meta.get("name", ""), "Land": listing.get("country", ""), "Børs": listing.get("exchange", ""), "Horisont": r.get("horizon", ""), "Base": _fmt_pct(r.get("base_pct")), "Bull": _fmt_pct(r.get("bull_pct")), "Bear": _fmt_pct(r.get("bear_pct")), "Confidence": f"{r.get('confidence', 0)}%", "Strength": f"{r.get('strength', 0)}/100", "Risiko": r.get("risk", "")})
    return out


def _candidate_rows(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in candidates:
        meta = resolve_security_metadata(c.get("ticker"), c)
        listing = infer_security_listing(c.get("ticker"), c)
        out.append({"Ticker": c.get("ticker", ""), "Navn": meta.get("name", ""), "Land": listing.get("country", ""), "Børs": listing.get("exchange", ""), "Kilde": c.get("source", ""), "Score": c.get("score", ""), "Confidence": c.get("confidence", ""), "Anbefaling": c.get("recommendation", ""), "Marked": listing.get("market") or c.get("market", "")})
    return out


def render_daily_ai_market_report() -> None:
    st.markdown("### 📈 AI Market Briefing")
    with st.expander("⚙️ Rapportoppsett", expanded=True):
        c1, c2, c3, c4 = st.columns([1.35, .9, .7, .9])
        with c1:
            focus = st.selectbox("Fokus", ["Ranking toppkandidater", "Hele markedet", "Min portefølje", "Watchlist", "Manuelle tickere", "Risiko/advarsler"], key="daily_report_focus_v1862")
        with c2:
            market = st.selectbox("Marked", standard_market_options(include_sources=True), key="daily_report_market_v1862")
        with c3:
            top_n = st.number_input("Topp N", min_value=3, max_value=100, value=20, step=1, key="daily_report_topn_v1862")
        with c4:
            unique = st.checkbox("Unike tickere", value=True, key="daily_report_unique_v1862")
        horizons = st.multiselect("Horisontfilter", ["1d", "1w", "1m", "3m", "6m"], default=["1m", "3m", "6m"], key="daily_report_horizons_v1862")
        if str(st.session_state.get("daily_report_manual_v1862", "") or "").strip().upper() in LEGACY_MANUAL_DEFAULTS_V1863AL:
            st.session_state["daily_report_manual_v1862"] = ""
        manual = st.text_input(
            "Manuelle tickere (brukes kun ved fokus Manuelle tickere)",
            value="",
            key="daily_report_manual_v1862",
            placeholder="Valgfritt: EQNR.OL, VOLV-B.ST, NOKIA.HE",
        )
        run = st.button("Oppdater AI Market Briefing", key="daily_ai_report_refresh_v1862", use_container_width=True, type="primary")

    params = (focus, market, int(top_n), tuple(horizons), bool(unique), manual)
    report_key = f"daily_ai_market_report::{_today_key()}::{hash(params)}"
    last_key = st.session_state.get("daily_ai_market_report_last_key_v1862")
    if run:
        st.session_state[report_key] = build_daily_market_report(focus, market, int(top_n), list(horizons), bool(unique), manual)
        st.session_state["daily_ai_market_report_last_key_v1862"] = report_key
        last_key = report_key

    report = st.session_state.get(last_key) if last_key else None
    if not report:
        st.info("Velg oppsett og trykk «Oppdater AI Market Briefing». Rapporten kjøres ikke automatisk når panelet åpnes.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Dato", report.get("date", ""))
    c2.metric("Regime", report.get("regime", {}).get("label", "Ukjent"))
    c3.metric("Varsler", report.get("alerts", {}).get("total", 0), f"🔴 {report.get('alerts', {}).get('red', 0)} · 🟡 {report.get('alerts', {}).get('yellow', 0)} · 🟢 {report.get('alerts', {}).get('green', 0)}")
    c4.metric("Kandidater", len(report.get("candidates", [])))
    c5.metric("Prognoser", report.get("forecasts", {}).get("count", 0))

    st.markdown("### Kandidatgrunnlag")
    candidates = report.get("candidates", [])
    if candidates:
        st.dataframe(_candidate_rows(candidates), use_container_width=True, hide_index=True)
    else:
        st.error("Ingen kandidater funnet for valgt fokus/marked. Kjør rangering/global oppdatering, velg Watchlist/Portefølje, eller bruk manuelle tickere.")
        with st.expander("Diagnostikk kandidatkilder", expanded=False):
            for d in report.get("diagnostics", []):
                st.write("- " + str(d))

    st.markdown("### Dagens korte status")
    regime = report.get("regime", {})
    alerts = report.get("alerts", {})
    learning = report.get("learning", {})
    macro = report.get("macro", {})
    macro_txt = f" Makro: **{macro.get('label')}** ({macro.get('combined_score')}/100)." if macro else ""
    st.write(f"Marked: **{regime.get('label', 'Ukjent')}**." + macro_txt + f" Varsler: **{alerts.get('red', 0)} røde**, **{alerts.get('yellow', 0)} gule**, **{alerts.get('green', 0)} grønne**. Læringsgrunnlag: **{learning.get('samples', 0)}** evaluerte punkter.")

    st.markdown("### Topp bullish / sterkeste prognoser")
    strongest = _rows_for_display(report.get("forecasts", {}).get("strongest", []))
    if strongest:
        st.dataframe(strongest, use_container_width=True, hide_index=True)
    else:
        st.info("Ingen prognoser for valgte kandidater/horisonter. Rapporten viser likevel kandidatgrunnlaget over.")

    st.markdown("### Topp risiko / svakeste prognoser")
    weakest = _rows_for_display(report.get("forecasts", {}).get("weakest", []))
    if weakest:
        st.dataframe(weakest, use_container_width=True, hide_index=True)
    else:
        st.caption("Ingen filtrerte risikoprognoser tilgjengelig.")

    st.markdown("### Viktigste varsler")
    top_alerts = report.get("alerts", {}).get("top", [])
    if top_alerts:
        rows = [{"Nivå": a.get("level", "").upper(), "Kilde": a.get("source", ""), "Ticker": a.get("ticker", ""), "Horisont": a.get("horizon", ""), "Kategori": a.get("category", ""), "Melding": a.get("message", "")} for a in top_alerts]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if st.button("✓ Marker viste varsler som gjennomgått", key="daily_report_mark_alerts_reviewed_v1862"):
            _mark_alerts_reviewed(top_alerts)
            st.rerun()
    else:
        st.success("Ingen aktive / ikke-gjennomgåtte varsler akkurat nå.")

    st.markdown("### Hvordan bruke rapporten")
    st.markdown("""
- Start med røde varsler.
- Sjekk svakeste prognoser før nye kjøp.
- Bruk kandidatlisten som grunnlag, ikke fasit.
- Se på regime før du tolker bull/base/bear.
- Ikke koble dette direkte til auto trading uten backtest.
""")
