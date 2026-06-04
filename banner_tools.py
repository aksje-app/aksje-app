"""
Small, side-effect free helpers for ticker-banner lists.

These functions are intentionally independent of Streamlit so tests can verify
manual ticker parsing and CSV import without importing the full app.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping


def parse_ticker_text(value) -> list[str]:
    """Parse one manual ticker field into de-duplicated uppercase tickers."""
    if value is None:
        return []
    parts = str(value).replace(";", ",").replace("|", ",").replace("\n", ",").split(",")
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        ticker = str(part).strip().upper().replace(" ", "")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def parse_banner_settings(
    settings: Mapping | None,
    markets: list[str],
    defaults: Mapping[str, str],
    labels: Mapping[str, str],
) -> tuple[tuple[str, str, str], ...]:
    """Return banner tuples from settings while preserving deliberate empty fields."""
    settings = settings or {}
    raw = settings.get("live_banner_tickers", {}) or {}
    visible_markets = settings.get("live_banner_markets_visible", ["USA", "Norge", "Sverige"])
    if isinstance(visible_markets, str):
        visible_markets = [m.strip() for m in visible_markets.replace(";", ",").split(",") if m.strip()]
    visible = set(visible_markets or [])
    out: list[tuple[str, str, str]] = []
    for market in markets:
        if market not in visible:
            continue
        if isinstance(raw, Mapping) and market in raw:
            text_value = raw.get(market, "")
        else:
            text_value = defaults.get(market, "")
        for ticker in parse_ticker_text(text_value):
            out.append((market, ticker, labels.get(ticker, ticker)))
    return tuple(out)


def parse_banner_csv_text(text: str, default_market: str = "Norge") -> dict[str, list[str]]:
    """
    Parse CSV with columns like ticker/symbol and market/marked.

    A plain one-column CSV also works and uses default_market.
    """
    text = str(text or "").strip()
    if not text:
        return {}
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows: list[dict[str, str]]
    if reader.fieldnames and any((name or "").strip().lower() in {"ticker", "symbol", "aksje", "isin", "marked", "market", "børs", "bors"} for name in reader.fieldnames):
        rows = [dict(row) for row in reader]
    else:
        rows = []
        raw_reader = csv.reader(io.StringIO(text), dialect=dialect)
        for row in raw_reader:
            if not row:
                continue
            rows.append({"ticker": row[0], "market": row[1] if len(row) > 1 else default_market})

    by_market: dict[str, list[str]] = {}
    for row in rows:
        normalized = {str(k or "").strip().lower(): v for k, v in row.items()}
        ticker = (
            normalized.get("ticker")
            or normalized.get("symbol")
            or normalized.get("aksje")
            or normalized.get("isin")
            or ""
        )
        market = normalized.get("market") or normalized.get("marked") or normalized.get("børs") or normalized.get("bors") or default_market
        ticker = str(ticker or "").strip().upper().replace(" ", "")
        market = str(market or default_market).strip() or default_market
        if not ticker or ticker.lower() in {"ticker", "symbol", "aksje"}:
            continue
        bucket = by_market.setdefault(market, [])
        if ticker not in bucket:
            bucket.append(ticker)
    return by_market


def merge_ticker_maps(current: Mapping[str, str], imported: Mapping[str, list[str]], mode: str = "add") -> dict[str, str]:
    """Merge imported ticker lists into text-field mapping."""
    replace = str(mode or "").lower().startswith(("erstatt", "replace"))
    result = {str(k): str(v or "") for k, v in (current or {}).items()}
    for market, tickers in (imported or {}).items():
        incoming = parse_ticker_text(",".join(tickers or []))
        if replace:
            result[market] = ", ".join(incoming)
            continue
        existing = parse_ticker_text(result.get(market, ""))
        seen = set(existing)
        for ticker in incoming:
            if ticker not in seen:
                existing.append(ticker)
                seen.add(ticker)
        result[market] = ", ".join(existing)
    return result
