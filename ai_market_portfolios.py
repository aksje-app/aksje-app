"""
v18.6.0 — Market Portfolio Forecast Patch

Purpose:
- Build market portfolios from ranking/universe data when real positions are missing.
- Prevent Daily Report from using only stale/single-ticker forecast cache such as STB.OL.
- Return unique ticker candidates with equal weights by default.

Drop this file into the app root and import from Daily Report / Forecast modules.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping, Sequence
import math
import pandas as pd

VERSION = "v18.6.0"

DEFAULT_MARKET_LIMITS = {
    "USA": 20,
    "US": 20,
    "NORGE": 20,
    "OSE": 20,
    "OSLO": 20,
    "SVERIGE": 20,
    "SWEDEN": 20,
    "ETF": 15,
    "FOND": 15,
    "CRYPTO": 15,
}

MARKET_ALIASES = {
    "usa": "USA",
    "us": "USA",
    "s&p 500": "USA",
    "sp500": "USA",
    "norge": "NORGE",
    "norway": "NORGE",
    "ose": "NORGE",
    "oslo": "NORGE",
    "oslobørs": "NORGE",
    "oslo børs": "NORGE",
    "sverige": "SVERIGE",
    "sweden": "SVERIGE",
    "stockholm": "SVERIGE",
    "etf": "ETF",
    "fond": "FOND",
    "fund": "FOND",
    "crypto": "CRYPTO",
    "krypto": "CRYPTO",
}

TICKER_COLS = ("ticker", "Ticker", "symbol", "Symbol", "Kode", "kode")
SCORE_COLS = ("score", "Score", "total_score", "Total score", "strength", "Strength", "rank_score", "RankScore")
MARKET_COLS = ("market", "Market", "marked", "Marked", "exchange", "Exchange")
NAME_COLS = ("name", "Name", "navn", "Navn", "company", "Company")


@dataclass(frozen=True)
class PortfolioCandidate:
    ticker: str
    weight: float
    source: str
    market: str
    score: float | None = None
    name: str | None = None


def normalize_market_key(market: str | None) -> str:
    if not market:
        return "USA"
    raw = str(market).strip()
    return MARKET_ALIASES.get(raw.lower(), raw.upper())


def _first_existing_col(df: pd.DataFrame, names: Sequence[str]) -> str | None:
    for col in names:
        if col in df.columns:
            return col
    lower_map = {str(c).lower(): c for c in df.columns}
    for col in names:
        hit = lower_map.get(col.lower())
        if hit is not None:
            return hit
    return None


def _clean_ticker(value: Any) -> str | None:
    if value is None:
        return None
    ticker = str(value).strip().upper()
    if not ticker or ticker in {"NAN", "NONE", "NULL", "CASH"}:
        return None
    return ticker


def _finite_float(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _market_matches(row_market: Any, selected_market: str) -> bool:
    if row_market is None or str(row_market).strip() == "":
        # Some ranking tables are already market-specific and have no market column.
        return True
    return normalize_market_key(str(row_market)) == normalize_market_key(selected_market)


def dataframe_to_market_candidates(
    ranking_df: pd.DataFrame | None,
    market: str,
    max_candidates: int | None = None,
    weighting: str = "equal",
) -> list[PortfolioCandidate]:
    """Build a unique market portfolio from a ranking DataFrame.

    Rules:
    - Use only rows matching selected market when a market/exchange column exists.
    - Remove invalid/duplicate tickers.
    - Sort by score descending when score exists.
    - Equal-weight by default for easier debugging and predictable behavior.
    """
    if ranking_df is None or ranking_df.empty:
        return []

    df = ranking_df.copy()
    selected_market = normalize_market_key(market)
    max_candidates = int(max_candidates or DEFAULT_MARKET_LIMITS.get(selected_market, 20))

    ticker_col = _first_existing_col(df, TICKER_COLS)
    score_col = _first_existing_col(df, SCORE_COLS)
    market_col = _first_existing_col(df, MARKET_COLS)
    name_col = _first_existing_col(df, NAME_COLS)
    if not ticker_col:
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for _, row in df.iterrows():
        ticker = _clean_ticker(row.get(ticker_col))
        if not ticker or ticker in seen:
            continue
        row_market = row.get(market_col) if market_col else selected_market
        if not _market_matches(row_market, selected_market):
            continue
        score = _finite_float(row.get(score_col)) if score_col else None
        name = str(row.get(name_col)).strip() if name_col and pd.notna(row.get(name_col)) else None
        rows.append({"ticker": ticker, "score": score, "name": name})
        seen.add(ticker)

    if score_col:
        rows.sort(key=lambda r: (r["score"] is not None, r["score"] or -999999), reverse=True)
    rows = rows[:max_candidates]
    if not rows:
        return []

    if weighting == "score" and any((r["score"] or 0) > 0 for r in rows):
        total = sum(max(r["score"] or 0, 0) for r in rows)
        weights = [(max(r["score"] or 0, 0) / total) if total else 1 / len(rows) for r in rows]
    else:
        weights = [1 / len(rows)] * len(rows)

    return [
        PortfolioCandidate(
            ticker=r["ticker"],
            weight=round(w, 6),
            source="market_portfolio",
            market=selected_market,
            score=r["score"],
            name=r["name"],
        )
        for r, w in zip(rows, weights)
    ]


def parse_manual_tickers(raw: str | Sequence[str] | None, market: str = "MANUAL") -> list[PortfolioCandidate]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace(";", ",").replace("\n", ",").split(",")
    else:
        parts = list(raw)
    tickers: list[str] = []
    seen: set[str] = set()
    for part in parts:
        t = _clean_ticker(part)
        if t and t not in seen:
            tickers.append(t)
            seen.add(t)
    if not tickers:
        return []
    w = round(1 / len(tickers), 6)
    return [PortfolioCandidate(ticker=t, weight=w, source="manual", market=market) for t in tickers]


def positions_to_candidates(positions: Any, market: str = "PORTFOLIO") -> list[PortfolioCandidate]:
    """Convert existing positions/portfolio data to candidates.

    Supports DataFrame or list of dicts. Uses weight column if available, otherwise equal weight.
    """
    if positions is None:
        return []
    if isinstance(positions, pd.DataFrame):
        df = positions.copy()
    else:
        try:
            df = pd.DataFrame(list(positions))
        except Exception:
            return []
    if df.empty:
        return []
    ticker_col = _first_existing_col(df, TICKER_COLS)
    weight_col = _first_existing_col(df, ("weight", "Weight", "vekt", "Vekt", "allocation", "Allocation"))
    if not ticker_col:
        return []

    rows = []
    seen = set()
    for _, row in df.iterrows():
        ticker = _clean_ticker(row.get(ticker_col))
        if not ticker or ticker in seen:
            continue
        weight = _finite_float(row.get(weight_col)) if weight_col else None
        rows.append({"ticker": ticker, "weight": weight})
        seen.add(ticker)
    if not rows:
        return []

    if any(r["weight"] is not None and r["weight"] > 0 for r in rows):
        total = sum(max(r["weight"] or 0, 0) for r in rows)
        weights = [(max(r["weight"] or 0, 0) / total) if total else 1 / len(rows) for r in rows]
    else:
        weights = [1 / len(rows)] * len(rows)
    return [PortfolioCandidate(ticker=r["ticker"], weight=round(w, 6), source="portfolio", market=market) for r, w in zip(rows, weights)]


def build_daily_report_universe(
    *,
    market: str,
    positions: Any = None,
    ranking_df: pd.DataFrame | None = None,
    watchlist: Sequence[str] | None = None,
    manual_tickers: str | Sequence[str] | None = None,
    max_candidates: int | None = None,
    weighting: str = "equal",
) -> tuple[list[PortfolioCandidate], str]:
    """Daily Report fallback order.

    1) Real portfolio positions
    2) Market portfolio from ranking data
    3) Watchlist
    4) Manual tickers
    5) Empty list; caller may choose old cache only as last-resort display
    """
    selected_market = normalize_market_key(market)

    candidates = positions_to_candidates(positions, market="PORTFOLIO")
    if candidates:
        return candidates, "portfolio"

    candidates = dataframe_to_market_candidates(
        ranking_df=ranking_df,
        market=selected_market,
        max_candidates=max_candidates,
        weighting=weighting,
    )
    if candidates:
        return candidates, "market_portfolio"

    candidates = parse_manual_tickers(watchlist, market="WATCHLIST")
    if candidates:
        return candidates, "watchlist"

    candidates = parse_manual_tickers(manual_tickers, market="MANUAL")
    if candidates:
        return candidates, "manual"

    return [], "empty"


def candidates_to_frame(candidates: Sequence[PortfolioCandidate]) -> pd.DataFrame:
    return pd.DataFrame([asdict(c) for c in candidates])


def collapse_forecasts_to_unique_tickers(
    forecast_rows: Iterable[Mapping[str, Any]],
    preferred_horizon: str | None = "1m",
    max_rows: int = 20,
) -> list[dict[str, Any]]:
    """Avoid Daily Report tables showing the same ticker five times.

    Keeps one best row per ticker. Preferred horizon wins when present; otherwise highest confidence wins.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in forecast_rows or []:
        ticker = _clean_ticker(row.get("ticker") or row.get("Ticker"))
        if not ticker:
            continue
        item = dict(row)
        item["ticker"] = ticker
        grouped.setdefault(ticker, []).append(item)

    selected: list[dict[str, Any]] = []
    for ticker, rows in grouped.items():
        def rank_key(r: Mapping[str, Any]) -> tuple[int, float]:
            h = str(r.get("horizon") or r.get("Horisont") or "").lower()
            conf = _finite_float(r.get("confidence") or r.get("Confidence")) or 0.0
            return (1 if preferred_horizon and h == preferred_horizon.lower() else 0, conf)
        selected.append(max(rows, key=rank_key))

    selected.sort(key=lambda r: (_finite_float(r.get("confidence") or r.get("Confidence")) or 0.0), reverse=True)
    return selected[:max_rows]
