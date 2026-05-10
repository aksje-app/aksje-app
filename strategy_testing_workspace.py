from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional
from datetime import datetime, timezone
import time

import streamlit as st

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

from forecast_store import load_learning_stats
from score_explanation_store import capture_score_explanations, score_explanations_for_ui
from strategy_engine import optimize_strategy, run_strategy, strategy_stats
from strategy_test_pro import render_strategy_test_pro


def _safe_rerun() -> None:
    try:
        st.rerun()
    except AttributeError:  # pragma: no cover
        try:
            st.experimental_rerun()
        except Exception:
            pass
    except Exception:
        pass



def _render_tl_progress_step(holder: Any, progress: Any, *, title: str, step: int, total: int, text: str) -> None:
    pct = min(1.0, max(0.0, step / max(1, total)))
    holder.markdown(
        f'<div style="position:relative;z-index:50;display:flex;align-items:center;gap:.75rem;border:2px solid rgba(56,189,248,.75);background:linear-gradient(180deg,rgba(7,89,133,.72),rgba(15,23,42,.96));border-radius:16px;padding:.86rem .95rem;margin:.45rem 0 .60rem 0;color:#e5edf8;box-shadow:0 12px 28px rgba(14,165,233,.18);">'
        '<style>@keyframes tlSpin{to{transform:rotate(360deg)}}</style>'
        '<span style="width:16px;height:16px;border:3px solid rgba(125,211,252,.25);border-top-color:#38bdf8;border-radius:999px;display:inline-block;animation:tlSpin .8s linear infinite;flex:0 0 auto;"></span>'
        f'<span style="font-weight:950;color:#f8fafc;">{title}</span>'
        f'<span style="color:#bae6fd;font-weight:900;">{step}/{total}</span>'
        f'<span style="color:#cbd5e1;font-weight:750;">{text}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    try:
        progress.progress(pct)
    except Exception:
        pass
    try:
        time.sleep(0.22)
    except Exception:
        pass


def _finish_tl_progress(holder: Any, progress: Any, *, title: str, text: str, ok: bool = True) -> None:
    border = "rgba(34,197,94,.58)" if ok else "rgba(250,204,21,.62)"
    color = "#bbf7d0" if ok else "#fde68a"
    holder.markdown(
        f'<div style="border:1px solid {border};background:rgba(15,23,42,.88);border-radius:14px;padding:.55rem .72rem;margin:.35rem 0 .45rem 0;color:{color};font-weight:900;">✅ {title}: {text}</div>',
        unsafe_allow_html=True,
    )
    try:
        progress.empty()
    except Exception:
        pass


def _normalise_history_frame(df: Any, ticker: str):
    """Return a StrategyEngine-compatible OHLC frame.

    yfinance can return either normal columns or MultiIndex columns depending on
    version/download parameters. The simple strategy test only needs Close, but
    StrategyEngine expects a plain ``Close`` column.
    """
    if df is None or not hasattr(df, "empty") or df.empty:
        return None
    if pd is None:
        return df
    out = df.copy()
    try:
        # Single-ticker downloads may still come back as MultiIndex in newer
        # yfinance versions: (Price, Ticker) or (Ticker, Price).
        if getattr(out.columns, "nlevels", 1) > 1:
            close_col = None
            ticker_upper = str(ticker or "").upper()
            for col in out.columns:
                parts = [str(part) for part in (col if isinstance(col, tuple) else (col,))]
                if "Close" in parts and (ticker_upper in [p.upper() for p in parts] or close_col is None):
                    close_col = col
                    if ticker_upper in [p.upper() for p in parts]:
                        break
            if close_col is not None:
                close = out[close_col]
                out = pd.DataFrame({"Close": close})
            else:
                out.columns = ["_".join(str(part) for part in col if str(part)) for col in out.columns]
        if "Close" not in out.columns:
            for col in out.columns:
                if str(col).lower().endswith("close") or str(col).lower().startswith("close"):
                    out = out.rename(columns={col: "Close"})
                    break
        if "Close" not in out.columns:
            return None
        out = out.copy()
        out["Close"] = pd.to_numeric(out["Close"], errors="coerce")
        out = out.dropna(subset=["Close"])
        return out
    except Exception:
        return None


def _fetch_history(ticker: str, period: str = "1y"):
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return None, "yfinance er ikke tilgjengelig."
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        df = _normalise_history_frame(df, ticker)
        if df is None or df.empty:
            return None, f"Fant ingen brukbar historikk/Close-data for {ticker}."
        return df, None
    except Exception as exc:
        return None, f"Klarte ikke hente historikk: {exc}"


def _strategy_result_key() -> str:
    return "tl_basic_strategy_result_v18518"


def _run_basic_strategy_test(ticker: str, period: str) -> Dict[str, Any]:
    df, error = _fetch_history(ticker, period=period)
    if error:
        return {
            "ok": False,
            "ticker": ticker,
            "period": period,
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    value, trades, equity = run_strategy(df)
    stats = strategy_stats(equity, trades)
    result: Dict[str, Any] = {
        "ok": True,
        "ticker": ticker,
        "period": period,
        "value": value,
        "trades": trades,
        "equity": equity,
        "stats": stats,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        result["optimization"] = optimize_strategy(df)
    except Exception as exc:
        result["optimization_error"] = str(exc)
    return result


def _render_basic_strategy_result(result: Mapping[str, Any]) -> bool:
    if not result:
        return False
    ticker = str(result.get("ticker") or "-").upper()
    period = str(result.get("period") or "-")
    created_at = str(result.get("created_at") or "")
    if not result.get("ok"):
        st.warning(str(result.get("error") or "Strategi-test feilet."))
        return False

    st.success(f"Strategi-test kjørt for {ticker} ({period}).")
    if created_at:
        st.caption(f"Sist kjørt: {created_at}")
    stats = result.get("stats") if isinstance(result.get("stats"), Mapping) else {}
    value = float(result.get("value") or 0)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sluttverdi", f"{value:,.0f}")
    m2.metric("Total avkastning", f"{stats.get('total_return_pct', 0):+.2f}%")
    m3.metric("Maks drawdown", f"{stats.get('max_drawdown_pct', 0):+.2f}%")
    m4.metric("Trefferate", f"{stats.get('win_rate', 0):.1f}%")

    equity = result.get("equity")
    if pd is not None and equity is not None and hasattr(equity, "empty") and not equity.empty:
        try:
            import plotly.graph_objects as go  # type: ignore

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=equity["date"], y=equity["value"], mode="lines", name="Strategi/equity"))
            fig.update_layout(title=f"{ticker} strategi/equity", height=330, margin=dict(l=10, r=10, t=45, b=10))
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(equity.tail(60), use_container_width=True)

    opt = result.get("optimization")
    if opt is not None and hasattr(opt, "empty") and not opt.empty:
        st.markdown("#### Strategi-optimalisering")
        st.dataframe(opt, use_container_width=True, hide_index=True)
    elif result.get("optimization_error"):
        st.caption(f"Optimalisering ikke tilgjengelig: {result.get('optimization_error')}")
    return True


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
    """Return live + persisted score explanations for a ticker.

    v18.5.16: score explanation is no longer only session-state based.
    Any live Smart AI/ranking rows found in the current session are captured to
    StorageService, and the table also loads the persisted explanation history.
    """
    ticker = ticker.upper()
    rows: List[Dict[str, Any]] = []
    raw_rows_to_capture: List[Dict[str, Any]] = []
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
                    ui_row = {
                        "Kilde": source,
                        "Ticker": ticker,
                        "AI-score": item.get("ai_score", item.get("score")),
                        "Smart-score": item.get("smart_score"),
                        "Strength": item.get("strength"),
                        "Risiko": item.get("risk"),
                        "Confidence": item.get("confidence"),
                        "Anbefaling": item.get("action") or item.get("recommendation"),
                        "Forklaring": item.get("reason") or item.get("note") or "-",
                    }
                    rows.append(ui_row)
                    raw_rows_to_capture.append(dict(item, source=source))
        smart = st.session_state.get("smart_universe_result") or st.session_state.get("ai_analysis_universe_smart_result_v1859") or {}
        if isinstance(smart, Mapping):
            for item in smart.get("candidates", []) or []:
                if isinstance(item, Mapping) and str(item.get("ticker", "")).upper() == ticker:
                    ui_row = {
                        "Kilde": "Smart AI-univers",
                        "Ticker": ticker,
                        "AI-score": item.get("ai_score"),
                        "Smart-score": item.get("smart_score"),
                        "Strength": item.get("strength"),
                        "Risiko": item.get("risk"),
                        "Confidence": item.get("confidence"),
                        "Anbefaling": item.get("action") or item.get("recommendation"),
                        "Forklaring": item.get("reason") or "-",
                    }
                    rows.append(ui_row)
                    raw_rows_to_capture.append(dict(item, source="Smart AI-univers"))
    except Exception:
        pass

    try:
        if raw_rows_to_capture:
            capture_score_explanations(
                raw_rows_to_capture,
                source="AI Kontrollsenter",
                context={"origin": "Testing & Learning", "ticker": ticker},
            )
    except Exception:
        pass

    try:
        persisted = score_explanations_for_ui(ticker, limit=20)
    except Exception:
        persisted = []

    # Merge live and persisted rows without repeating identical explanations.
    merged: List[Dict[str, Any]] = []
    seen = set()
    for row in rows + persisted:
        key = (
            str(row.get("Kilde")),
            str(row.get("Ticker")),
            str(row.get("AI-score")),
            str(row.get("Smart-score")),
            str(row.get("Strength")),
            str(row.get("Risiko")),
            str(row.get("Forklaring")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _render_basic_strategy_test(ticker: str) -> bool:
    st.markdown("#### Strategi-test")
    c1, c2 = st.columns([1, 1])
    with c1:
        period = st.selectbox("Historikk", ["6mo", "1y", "2y", "5y"], index=1, key="tl_strategy_period_v18515")
    with c2:
        run = st.button("Kjør enkel strategi-test", key="tl_strategy_run_v18515", use_container_width=True)

    result_key = _strategy_result_key()
    pending_key = "tl_basic_strategy_run_pending_v18524"
    if run:
        st.session_state[pending_key] = {"ticker": ticker, "period": period}
        _safe_rerun()

    pending_run = st.session_state.pop(pending_key, None)
    if pending_run:
        run_ticker = str(pending_run.get("ticker") or ticker) if isinstance(pending_run, Mapping) else ticker
        run_period = str(pending_run.get("period") or period) if isinstance(pending_run, Mapping) else period
        progress_holder = st.empty()
        try:
            progress_bar = st.progress(0.0, text="Starter Strategi-test …")
        except TypeError:
            progress_bar = st.progress(0.0)
        _render_tl_progress_step(progress_holder, progress_bar, title="Strategi-test", step=1, total=4, text="Henter kursdata")
        _render_tl_progress_step(progress_holder, progress_bar, title="Strategi-test", step=2, total=4, text="Kjører baseline-regler")
        result = _run_basic_strategy_test(run_ticker, run_period)
        _render_tl_progress_step(progress_holder, progress_bar, title="Strategi-test", step=3, total=4, text="Beregner statistikk og drawdown")
        st.session_state[result_key] = result
        _render_tl_progress_step(progress_holder, progress_bar, title="Strategi-test", step=4, total=4, text="Lagrer resultat i session")
        _finish_tl_progress(progress_holder, progress_bar, title="Strategi-test ferdig", text=f"{run_ticker} ({run_period})", ok=bool(result.get("ok")))

    result = st.session_state.get(result_key)
    if result:
        return _render_basic_strategy_result(result)

    st.caption("Kjører en enkel buy-and-hold/equity baseline via StrategyEngine når du trykker på knappen.")
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
