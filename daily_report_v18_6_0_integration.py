"""
Integration example for v18.6.0 Daily AI Market Report.

Use this as a drop-in reference in the existing Daily Report code. It assumes the app already has:
- a forecast function for a single ticker, e.g. make_forecast(ticker, horizon, market_regime)
- ranking DataFrame from Marked/rangering
- optional positions/watchlist/manual tickers
"""

from __future__ import annotations

from typing import Any, Callable, Sequence
import pandas as pd

from ai_market_portfolios import (
    VERSION,
    build_daily_report_universe,
    candidates_to_frame,
    collapse_forecasts_to_unique_tickers,
)


def build_v18_6_0_daily_report(
    *,
    market: str,
    ranking_df: pd.DataFrame | None,
    forecast_fn: Callable[..., dict[str, Any]],
    positions: Any = None,
    watchlist: Sequence[str] | None = None,
    manual_tickers: str | Sequence[str] | None = None,
    horizon: str = "1m",
    max_candidates: int = 20,
    market_regime: str | None = None,
) -> dict[str, Any]:
    """Build Daily Report data with market-portfolio fallback.

    Important behavior:
    - Does NOT start from old saved forecast cache.
    - Uses cache only outside this function if the caller explicitly wants a last-resort display.
    - Runs forecasts for unique market candidates.
    """
    candidates, source = build_daily_report_universe(
        market=market,
        positions=positions,
        ranking_df=ranking_df,
        watchlist=watchlist,
        manual_tickers=manual_tickers,
        max_candidates=max_candidates,
        weighting="equal",
    )

    forecast_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for c in candidates:
        try:
            row = forecast_fn(
                ticker=c.ticker,
                horizon=horizon,
                weight=c.weight,
                market=market,
                market_regime=market_regime,
            )
            if row:
                row.setdefault("ticker", c.ticker)
                row.setdefault("horizon", horizon)
                row.setdefault("weight", c.weight)
                row.setdefault("source", c.source)
                row.setdefault("market", c.market)
                forecast_rows.append(row)
        except Exception as exc:
            errors.append({"ticker": c.ticker, "error": str(exc)})

    unique_forecasts = collapse_forecasts_to_unique_tickers(
        forecast_rows,
        preferred_horizon=horizon,
        max_rows=max_candidates,
    )

    bullish = sorted(
        unique_forecasts,
        key=lambda r: float(r.get("bull", r.get("Bull", 0)) or 0),
        reverse=True,
    )
    risk = sorted(
        unique_forecasts,
        key=lambda r: float(r.get("bear", r.get("Bear", 0)) or 0),
    )

    return {
        "version": VERSION,
        "market": market,
        "source": source,
        "portfolio": candidates_to_frame(candidates),
        "forecasts": pd.DataFrame(unique_forecasts),
        "top_bullish": pd.DataFrame(bullish[:10]),
        "top_risk": pd.DataFrame(risk[:10]),
        "errors": pd.DataFrame(errors),
        "status_text": _status_text(source, market, len(candidates), len(unique_forecasts), len(errors)),
    }


def _status_text(source: str, market: str, candidates: int, forecasts: int, errors: int) -> str:
    if source == "portfolio":
        base = f"Bruker ekte portefølje: {candidates} kandidater."
    elif source == "market_portfolio":
        base = f"Bruker markedsportefølje for {market}: {candidates} rangerte kandidater."
    elif source == "watchlist":
        base = f"Bruker watchlist: {candidates} kandidater."
    elif source == "manual":
        base = f"Bruker manuelle tickere: {candidates} kandidater."
    else:
        base = "Fant ingen portefølje, rangering, watchlist eller manuelle tickere."
    return f"{base} Prognoser laget: {forecasts}. Feil: {errors}."
