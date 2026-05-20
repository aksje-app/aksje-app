"""
forecast_backtest_ui.py

UI for ekte backtest-læring.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

from forecast_backtest_engine import run_backtest_learning_batch, summarize_backtest_learning
from forecast_store import load_forecast_log


def _is_demo_ticker_v1863ad(ticker: str) -> bool:
    text = str(ticker or "").strip().upper()
    return text.startswith("TEST") or text in {"DEMO", "DUMMY", "SAMPLE"}


def _learning_quality_message_v1863ad(global_stats: Dict[str, float]) -> tuple[str, str]:
    count = int(global_stats.get("count", 0) or 0)
    direction = float(global_stats.get("direction_accuracy", 0) or 0)
    inside = float(global_stats.get("inside_band_accuracy", 0) or 0)
    error = float(global_stats.get("avg_abs_error_pct", 0) or 0)
    if count < 30:
        return "Lavt datagrunnlag", "For få samples til å stole på mønsteret. Bruk dette som teknisk kontroll, ikke konklusjon."
    if direction >= 90 and inside < 25:
        return "Retning treffer, bånd må kalibreres", "Modellen har truffet opp/ned historisk, men prognoseintervallet er for smalt eller feilplassert."
    if inside >= 60 and error <= 5:
        return "God kalibrering", "Både retning og forventet intervall ser brukbart kalibrert ut på historikken."
    return "Blandet kvalitet", "Se spesielt på snittfeil og om faktisk kurs havner innen prognosebåndet."


def _fetch_prices(ticker: str, period: str = "1y") -> Tuple[List[Dict[str, float]], Optional[str]]:
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
        for idx, x in zip(list(close.index), list(close)):
            try:
                day = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
                prices.append({"date": day, "close": float(x)})
            except Exception:
                continue

        if len(prices) < 30:
            return [], f"For lite data for {ticker}."
        return prices, None
    except Exception as exc:
        return [], f"Klarte ikke hente {ticker}: {exc}"


def _tickers_from_forecast_log(limit: int = 500) -> List[str]:
    tickers = []
    for row in load_forecast_log(limit=limit):
        ticker = str(row.get("ticker", "")).upper()
        if ticker and not _is_demo_ticker_v1863ad(ticker) and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def render_backtest_learning_panel() -> None:
    with st.expander("🧪 Ekte backtest-læring", expanded=False):
        st.caption("Evaluerer lagrede prognoser mot faktisk kurs og oppdaterer lærende confidence. Ingen auto-trading-kobling.")

        all_log_tickers = [
            str(row.get("ticker", "")).upper()
            for row in load_forecast_log(limit=500)
            if str(row.get("ticker", "")).strip()
        ]
        demo_tickers = sorted({t for t in all_log_tickers if _is_demo_ticker_v1863ad(t)})
        tickers = _tickers_from_forecast_log(limit=500)
        c1, c2 = st.columns([2, 1])
        with c1:
            if tickers:
                selected = st.multiselect(
                    "Tickere å evaluere",
                    options=tickers,
                    default=tickers[:10],
                    key="backtest_learning_tickers_v1842",
                    help="Hentes fra lagrede prognoser.",
                )
            else:
                st.info("Ingen lagrede prognoser funnet ennå. Lag prognoser først, eller bruk manuell ticker-fallback.")
                manual_raw = st.text_input(
                    "Manuelle tickere",
                    value="AAPL,NVDA,MSFT",
                    key="backtest_learning_manual_tickers_v1848",
                    help="Kommaseparert fallback når prognoseloggen er tom.",
                )
                selected = [x.strip().upper() for x in manual_raw.split(",") if x.strip()]
            if demo_tickers:
                st.caption("Demo-/testtickere er skjult fra listen: " + ", ".join(demo_tickers[:6]))
        with c2:
            max_eval = st.number_input("Maks evalueringer", min_value=1, max_value=500, value=100, step=10, key="backtest_learning_max_v1842")

        if st.button("Kjør backtest-læring nå", key="run_backtest_learning_v1842", use_container_width=True):
            if not selected:
                st.warning("Ingen tickere valgt.")
                return

            actual_lookup: Dict[str, List[float]] = {}
            errors = []
            for ticker in selected:
                prices, err = _fetch_prices(ticker, period="2y")
                if err:
                    errors.append(err)
                else:
                    actual_lookup[ticker] = prices

            if not actual_lookup:
                st.warning("Kunne ikke hente faktisk kursdata for valgte tickere.")
                if errors:
                    st.caption(" | ".join(errors[:5]))
                return

            result = run_backtest_learning_batch(actual_lookup, max_evaluations=int(max_eval))
            st.success(f"Evaluert: {result['evaluated_count']} · Skippet: {result['skipped_count']} · Feil: {result['error_count']}")

            if result["evaluated"]:
                rows = []
                for e in result["evaluated"][:50]:
                    rows.append({
                        "Ticker": e.get("ticker"),
                        "Horisont": e.get("horizon"),
                        "Prognosedato": e.get("forecast_date"),
                        "Måldato": e.get("target_date"),
                        "Faktisk dato": e.get("actual_date"),
                        "Dato-presis": "Ja" if e.get("date_precision") else "Legacy",
                        "Feil %": e.get("error_pct"),
                        "Retning traff": "Ja" if e.get("direction_hit") else "Nei",
                        "Innen bull/bear": "Ja" if e.get("inside_bull_bear_range") else "Nei",
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)

            if result["errors"]:
                st.warning("Noen evalueringer feilet.")
                st.json(result["errors"][:10])

        st.markdown("### Læringsstatus")
        summary = summarize_backtest_learning()
        g = summary.get("global", {})
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Samples", int(g.get("count", 0)))
        s2.metric("Retning accuracy", f"{g.get('direction_accuracy', 0)}%")
        s3.metric("Innen bånd", f"{g.get('inside_band_accuracy', 0)}%")
        s4.metric("Snittfeil", f"{g.get('avg_abs_error_pct', 0)}%")
        quality_title, quality_text = _learning_quality_message_v1863ad(g)
        st.markdown(
            f"""
            <div class='v18-dark-row' style='border-color:rgba(56,189,248,.55);background:linear-gradient(135deg,rgba(8,47,73,.60),rgba(15,23,42,.92));'>
              <b>{quality_title}</b><br>
              Retning betyr om modellen traff opp/ned. Innen b?nd betyr om faktisk kurs landet i prognoseintervallet.
              Snittfeil er gjennomsnittlig bom i prosent. {quality_text}
            </div>
            """,
            unsafe_allow_html=True,
        )


        if summary.get("horizons"):
            st.markdown("### Accuracy per horisont")
            rows = []
            for horizon, data in summary["horizons"].items():
                rows.append({
                    "Horisont": horizon,
                    "Samples": data.get("count", 0),
                    "Retning accuracy": f"{data.get('direction_accuracy', 0)}%",
                    "Innen bånd": f"{data.get('inside_band_accuracy', 0)}%",
                    "Snittfeil": f"{data.get('avg_abs_error_pct', 0)}%",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

        if summary.get("best_tickers"):
            st.markdown("### Beste tickere historisk")
            rows = []
            for r in summary["best_tickers"][:8]:
                rows.append({
                    "Ticker": r.get("ticker"),
                    "Samples": r.get("count", 0),
                    "Retning accuracy": f"{r.get('direction_accuracy', 0)}%",
                    "Snittfeil": f"{r.get('avg_abs_error_pct', 0)}%",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
