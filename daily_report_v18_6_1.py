"""
v18.6.1 — Input-driven Daily Report / AI Market Briefing.
Prevents single-ticker cache reports by preferring selected universe/market inputs.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence
import pandas as pd
import streamlit as st

APP_VERSION = "v18.6.1"


@dataclass
class DailyReportConfig:
    focus: str = "Ranking toppkandidater"
    market: str = "USA"
    candidate_count: int = 20
    horizon: str = "1m"
    report_type: str = "AI Market Briefing"
    unique_tickers: bool = True
    mode: str = "Neutral"


def normalize_ticker(ticker: object) -> str:
    return str(ticker or "").strip().upper()


def unique_by_ticker(df: pd.DataFrame, score_col: str = "score") -> pd.DataFrame:
    if df is None or df.empty or "ticker" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["ticker"] = out["ticker"].map(normalize_ticker)
    out = out[out["ticker"] != ""]
    if score_col in out.columns:
        out = out.sort_values(score_col, ascending=False)
    return out.drop_duplicates("ticker", keep="first").reset_index(drop=True)


def build_market_universe(
    market: str,
    ranking_df: pd.DataFrame | None,
    watchlist: Sequence[str] | None = None,
    positions_df: pd.DataFrame | None = None,
    candidate_count: int = 20,
    focus: str = "Ranking toppkandidater",
) -> pd.DataFrame:
    """Return the tickers Daily Report should analyze.

    Priority:
      1. Portfolio/positions when focus asks for portfolio and positions exist
      2. Watchlist when focus asks for watchlist and watchlist exists
      3. Ranking filtered by selected market
      4. Empty frame, so host app can show a clear warning instead of cache dump
    """
    focus_l = (focus or "").lower()

    if "portef" in focus_l and positions_df is not None and not positions_df.empty and "ticker" in positions_df.columns:
        df = positions_df.copy()
        df["source"] = "portfolio"
        return unique_by_ticker(df).head(candidate_count)

    if "watch" in focus_l and watchlist:
        return pd.DataFrame({"ticker": [normalize_ticker(t) for t in watchlist], "source": "watchlist"}).pipe(unique_by_ticker).head(candidate_count)

    if ranking_df is None or ranking_df.empty:
        return pd.DataFrame(columns=["ticker", "source"])

    df = ranking_df.copy()
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["ticker", "source"])

    if market and market != "Multi-market" and "market" in df.columns:
        df = df[df["market"].astype(str).str.upper() == market.upper()]

    df["source"] = "ranking"
    return unique_by_ticker(df).head(candidate_count)


def render_daily_report_controls() -> DailyReportConfig:
    st.subheader("📈 AI Market Briefing")
    c1, c2, c3, c4 = st.columns([1.25, 1, 0.75, 0.75])
    with c1:
        focus = st.selectbox(
            "Fokus",
            ["Ranking toppkandidater", "Min portefølje", "Watchlist", "ETF/Fond", "Risiko/advarsler", "Momentum", "Defensive aksjer"],
            key="daily_report_focus_v1861",
        )
    with c2:
        market = st.selectbox("Marked", ["USA", "Norge", "Sverige", "Europa", "ETF", "Crypto", "Multi-market"], key="daily_report_market_v1861")
    with c3:
        candidate_count = st.selectbox("Kandidater", [10, 20, 30, 50], index=1, key="daily_report_candidates_v1861")
    with c4:
        horizon = st.selectbox("Horisont", ["1d", "1w", "1m", "3m", "6m"], index=2, key="daily_report_horizon_v1861")

    c5, c6, c7 = st.columns([1.2, 1, 0.8])
    with c5:
        report_type = st.selectbox(
            "Rapporttype",
            ["AI Market Briefing", "Bullish opportunities", "Risiko / advarsler", "Regimeskifte", "Porteføljehelse", "Auto-trading readiness"],
            key="daily_report_type_v1861",
        )
    with c6:
        mode = st.selectbox("Prognosemodus", ["Conservative", "Neutral", "Aggressive"], index=1, key="daily_report_mode_v1861")
    with c7:
        unique_tickers = st.checkbox("Kun unike tickere", value=True, key="daily_report_unique_v1861")

    return DailyReportConfig(focus, market, int(candidate_count), horizon, report_type, bool(unique_tickers), mode)


def render_ai_market_briefing(
    ranking_df: pd.DataFrame | None = None,
    forecast_fn: Callable[[str, str], dict] | None = None,
    watchlist: Sequence[str] | None = None,
    positions_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Render input-driven report and return the candidate/forecast table.

    forecast_fn(ticker, horizon) should return fields like base/bull/bear/confidence.
    If no forecast_fn is supplied, the function still renders candidate universe.
    """
    cfg = render_daily_report_controls()

    universe = build_market_universe(cfg.market, ranking_df, watchlist, positions_df, cfg.candidate_count, cfg.focus)
    if universe.empty:
        st.warning("Ingen kandidater funnet for valgt fokus/marked. Kjør rangering eller legg inn watchlist/portefølje først.")
        return universe

    rows = []
    for _, row in universe.iterrows():
        ticker = normalize_ticker(row.get("ticker"))
        result = {"ticker": ticker, "market": row.get("market", cfg.market), "horizon": cfg.horizon, "source": row.get("source", "ranking")}
        if callable(forecast_fn):
            try:
                result.update(forecast_fn(ticker, cfg.horizon) or {})
            except Exception as exc:
                result.update({"error": str(exc)})
        else:
            for col in ["score", "strength", "risk", "confidence"]:
                if col in universe.columns:
                    result[col] = row.get(col)
        rows.append(result)

    report_df = pd.DataFrame(rows)
    if cfg.unique_tickers:
        report_df = unique_by_ticker(report_df, "confidence" if "confidence" in report_df.columns else "score")

    st.markdown("### Dagens korte status")
    st.write(f"Fokus: **{cfg.focus}** • Marked: **{cfg.market}** • Horisont: **{cfg.horizon}** • Kandidater: **{len(report_df)}**")

    st.markdown("### Topp kandidater")
    st.dataframe(report_df, use_container_width=True, hide_index=True)

    st.markdown("### Hvordan bruke rapporten")
    st.markdown("- Start med røde/gule varsler.\n- Bruk sterkeste kandidater som arbeidsliste, ikke fasit.\n- Se regime og risiko før bull/base/bear tolkes.\n- Ikke koble direkte til auto-trading uten backtest.")
    return report_df
