from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

import streamlit as st

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

from forecast_store import load_learning_stats
from strategy_engine import optimize_strategy, run_strategy, strategy_stats
from strategy_test_pro import render_strategy_test_pro


def _fetch_history(ticker: str, period: str = "1y"):
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return None, "yfinance er ikke tilgjengelig."
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None, f"Fant ingen historikk for {ticker}."
        if "Close" not in df and hasattr(df, "columns"):
            return None, f"Mangler Close-kolonne for {ticker}."
        return df, None
    except Exception as exc:
        return None, f"Klarte ikke hente historikk: {exc}"


def _collect_known_tickers(default: str = "AAPL", limit: int = 12) -> List[str]:
    tickers: List[str] = []

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            for part in value.split(","):
                t = part.strip().upper()
                if t and t not in tickers:
                    tickers.append(t)
        elif isinstance(value, Mapping):
            t = str(value.get("ticker") or value.get("symbol") or "").strip().upper()
            if t and t not in tickers:
                tickers.append(t)
        elif isinstance(value, Iterable):
            for item in value:
                add(item)

    add(default)
    try:
        add(st.session_state.get("latest_watchlist_tickers_v156", []))
        rankings = st.session_state.get("latest_rankings_v148", {}) or {}
        if isinstance(rankings, Mapping):
            for rows in rankings.values():
                add(rows)
        smart = st.session_state.get("smart_universe_result") or st.session_state.get("ai_analysis_universe_smart_result_v1859") or {}
        if isinstance(smart, Mapping):
            add(smart.get("top_picks") or smart.get("candidates") or [])
    except Exception:
        pass
    return tickers[:limit] or [default]


def _score_rows_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    ticker = ticker.upper()
    rows: List[Dict[str, Any]] = []
    try:
        rankings = st.session_state.get("latest_rankings_v148", {}) or {}
        if isinstance(rankings, Mapping):
            for source, items in rankings.items():
                if not isinstance(items, Iterable) or isinstance(items, (str, bytes)):
                    continue
                for item in items:
                    if not isinstance(item, Mapping):
                        continue
                    if str(item.get("ticker") or item.get("symbol") or "").upper() != ticker:
                        continue
                    rows.append({
                        "Kilde": source,
                        "Ticker": ticker,
                        "AI-score": item.get("ai_score", item.get("score")),
                        "Smart-score": item.get("smart_score"),
                        "Strength": item.get("strength"),
                        "Risiko": item.get("risk"),
                        "Forklaring": item.get("reason") or item.get("note") or "-",
                    })
        smart = st.session_state.get("smart_universe_result") or st.session_state.get("ai_analysis_universe_smart_result_v1859") or {}
        if isinstance(smart, Mapping):
            for item in smart.get("candidates", []) or []:
                if isinstance(item, Mapping) and str(item.get("ticker", "")).upper() == ticker:
                    rows.append({
                        "Kilde": "Smart AI-univers",
                        "Ticker": ticker,
                        "AI-score": item.get("ai_score"),
                        "Smart-score": item.get("smart_score"),
                        "Strength": item.get("strength"),
                        "Risiko": item.get("risk"),
                        "Forklaring": item.get("reason") or "-",
                    })
    except Exception:
        pass
    return rows


def _render_basic_strategy_test(ticker: str) -> bool:
    st.markdown("#### Strategi-test")
    c1, c2 = st.columns([1, 1])
    with c1:
        period = st.selectbox("Historikk", ["6mo", "1y", "2y", "5y"], index=1, key="tl_strategy_period_v18515")
    with c2:
        run = st.button("Kjør enkel strategi-test", key="tl_strategy_run_v18515", use_container_width=True)
    if not run:
        st.caption("Kjører en enkel buy-and-hold/equity baseline via StrategyEngine når du trykker på knappen.")
        return True

    df, error = _fetch_history(ticker, period=period)
    if error:
        st.warning(error)
        return False
    value, trades, equity = run_strategy(df)
    stats = strategy_stats(equity, trades)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sluttverdi", f"{value:,.0f}")
    m2.metric("Total avkastning", f"{stats.get('total_return_pct', 0):+.2f}%")
    m3.metric("Maks drawdown", f"{stats.get('max_drawdown_pct', 0):+.2f}%")
    m4.metric("Trefferate", f"{stats.get('win_rate', 0):.1f}%")

    if pd is not None and equity is not None and not equity.empty:
        try:
            import plotly.graph_objects as go  # type: ignore

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=equity["date"], y=equity["value"], mode="lines", name="Strategi/equity"))
            fig.update_layout(title=f"{ticker} strategi/equity", height=330, margin=dict(l=10, r=10, t=45, b=10))
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(equity.tail(60), use_container_width=True)

    try:
        opt = optimize_strategy(df)
        st.markdown("#### Strategi-optimalisering")
        st.dataframe(opt, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.caption(f"Optimalisering ikke tilgjengelig: {exc}")
    return True


def _render_score_explanation(ticker: str) -> bool:
    st.markdown("#### Score-forklaring")
    rows = _score_rows_for_ticker(ticker)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        return True
    st.info("Ingen lagret scoreforklaring funnet for valgt ticker ennå. Kjør Smart AI-utvalg eller analyse først.")
    return False


def _render_learning_history_summary() -> bool:
    st.markdown("#### Trefferate / learning history")
    stats = load_learning_stats()
    g = stats.get("global", {}) or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Samples", int(g.get("count", 0) or 0))
    c2.metric("Retning", f"{g.get('direction_accuracy', 0)}%")
    c3.metric("Innen bånd", f"{g.get('inside_band_accuracy', 0)}%")
    c4.metric("Snittfeil", f"{g.get('avg_abs_error_pct', 0)}%")
    if stats.get("horizons"):
        rows = [{"Horisont": k, **v} for k, v in stats.get("horizons", {}).items()]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    return True


def render_strategy_testing_workspace(ticker: str = "AAPL") -> None:
    st.markdown("### 🧪 Testing & Learning")
    st.caption("Strategi-test, Strategi-test Pro, scoreforklaring og læringshistorikk samlet i AI Kontrollsenter. Ingen ordre eller auto-trading kobles her.")

    known = _collect_known_tickers(ticker)
    selected = st.selectbox("Ticker for testing", options=known, index=0, key="tl_selected_ticker_v18515")

    rendered: Dict[str, bool] = {}
    rendered["Strategi-test"] = _render_basic_strategy_test(selected)

    try:
        default_rules = {
            "rsi_buy": 35,
            "rsi_sell": 70,
            "stop_loss_pct": 8,
            "take_profit_pct": 15,
        }
        render_strategy_test_pro(
            default_ticker=selected,
            default_tickers=known,
            default_rules=default_rules,
            key_prefix="testing_learning_strategy_pro_v18515",
        )
        rendered["Strategi-test Pro"] = True
    except Exception as exc:
        rendered["Strategi-test Pro"] = False
        st.warning(f"Strategi-test Pro kunne ikke vises: {exc}")

    rendered["Score-forklaring"] = _render_score_explanation(selected)
    rendered["Trefferate / learning history"] = _render_learning_history_summary()

    st.markdown("#### Testing & Learning status")
    rows = [
        {"Område": "Strategi-test / historisk simulering", "Status": "✅ Aktiv" if rendered.get("Strategi-test") else "🔴 Ikke aktiv"},
        {"Område": "Strategi-test Pro / optimalisering", "Status": "✅ Aktiv" if rendered.get("Strategi-test Pro") else "🔴 Ikke aktiv"},
        {"Område": "Score-forklaring", "Status": "✅ Aktiv" if rendered.get("Score-forklaring") else "🟡 Venter på scoredata"},
        {"Område": "Prognose vs faktisk", "Status": "✅ Aktiv i Prognose-fanen + backtest-læring under"},
        {"Område": "Backtest-læring", "Status": "✅ Aktiv"},
        {"Område": "Trefferate og learning history", "Status": "✅ Aktiv"},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
