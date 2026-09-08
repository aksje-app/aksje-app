"""Real market-data enrichment for Investment Pipeline v18.6.92b.

The module turns a bare ticker candidate into traceable technical,
fundamental, liquidity and risk inputs. Missing data is reported explicitly;
no synthetic company metrics are invented.
"""
from __future__ import annotations

import json
import math
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from storage_architecture import runtime_data_path
from investment_pipeline import canonical_market_ticker
from ticker_health import quarantine_status, record_ticker_failure, record_ticker_success

VERSION = "v18.6.93e"
CACHE_DIR = runtime_data_path("market_intelligence") / "enrichment_cache"
CACHE_TTL_SECONDS = 6 * 60 * 60


def _env_float(name: str, default: float, minimum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = float(default)
    return max(float(minimum), value)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), min(int(maximum), value))


FETCH_TIMEOUT_SECONDS = _env_float("MARKET_DATA_FETCH_TIMEOUT_SECONDS", 8.0, 3.0)
INFO_TIMEOUT_SECONDS = _env_float("MARKET_DATA_INFO_TIMEOUT_SECONDS", 4.0, 1.0)
MARKET_ENRICH_TIMEOUT_SECONDS = _env_float("MARKET_DATA_MARKET_TIMEOUT_SECONDS", 180.0, 30.0)
FETCH_ATTEMPTS = _env_int("MARKET_DATA_FETCH_ATTEMPTS", 2, 1, 3)


def _call_with_timeout(func: Callable[[], Any], timeout_seconds: float) -> tuple[Any, str]:
    """Run one optional metadata call without letting it block the market run.

    The helper thread is daemonised; timed-out metadata is omitted while price
    history and the remaining candidates continue.
    """
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, func()), block=False)
        except Exception as exc:  # pragma: no cover - exercised through caller
            try:
                result_queue.put((False, exc), block=False)
            except queue.Full:
                pass

    thread = threading.Thread(target=runner, name="market-data-optional-call", daemon=True)
    thread.start()
    try:
        ok, value = result_queue.get(timeout=max(0.1, float(timeout_seconds)))
    except queue.Empty:
        return None, f"TIMEOUT_AFTER_{float(timeout_seconds):g}s"
    if ok:
        return value, ""
    return None, f"{type(value).__name__}: {value}"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _safe_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100.0 if abs(value) <= 3.0 else value


def _cache_path(ticker: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in ticker.upper())
    return CACHE_DIR / f"{safe}.json"


def _read_cache_snapshot(ticker: str) -> dict[str, Any]:
    """Read prior cache only for comparison/audit; never returns it as analysis input."""
    path = _cache_path(ticker)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = dict(payload.get("row") or {})
        return {
            "exists": True,
            "cached_epoch": payload.get("cached_epoch"),
            "last_price": row.get("last_price"),
            "latest_trade_date": row.get("latest_trade_date"),
            "enriched_at": row.get("enriched_at"),
        }
    except Exception:
        return {"exists": False}


def _read_cache(ticker: str) -> dict[str, Any] | None:
    path = _cache_path(ticker)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cached_epoch = float(payload.get("cached_epoch", 0))
        age_seconds = max(0.0, time.time() - cached_epoch)
        if age_seconds <= CACHE_TTL_SECONDS:
            row = dict(payload.get("row") or {})
            row["cache_hit"] = True
            row["cache_age_seconds"] = round(age_seconds, 1)
            row["cache_age_minutes"] = round(age_seconds / 60.0, 1)
            row["cache_ttl_seconds"] = CACHE_TTL_SECONDS
            row["cache_path"] = str(path)
            row["data_source"] = "yfinance-cache"
            return row
    except Exception:
        return None
    return None


def _write_cache(ticker: str, row: Mapping[str, Any]) -> None:
    path = _cache_path(ticker)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cached_epoch": time.time(), "row": dict(row)}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def _series_value(series: Any, offset: int) -> float | None:
    try:
        return _finite(series.iloc[offset])
    except Exception:
        return None


def _return_pct(close: Any, days: int) -> float | None:
    if close is None or len(close) <= days:
        return None
    latest = _series_value(close, -1)
    previous = _series_value(close, -(days + 1))
    if latest is None or previous in (None, 0):
        return None
    return (latest / previous - 1.0) * 100.0


def _rsi(close: Any, window: int = 14) -> float | None:
    try:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / loss.replace(0, float("nan"))
        value = float((100 - (100 / (1 + rs))).iloc[-1])
        return value if math.isfinite(value) else None
    except Exception:
        return None



def _rsi_series(close: Any, window: int = 14) -> Any:
    try:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / loss.replace(0, float("nan"))
        return 100 - (100 / (1 + rs))
    except Exception:
        return None


def _recent_cross_age(left: Any, right: Any, lookback: int = 80) -> int | None:
    try:
        aligned = left.to_frame("left").join(right.to_frame("right"), how="inner").dropna()
        if len(aligned) < 2:
            return None
        crossed = (aligned["left"] > aligned["right"]) & (aligned["left"].shift(1) <= aligned["right"].shift(1))
        hits = [i for i, flag in enumerate(crossed.tolist()) if bool(flag)]
        if not hits:
            return None
        age = len(aligned) - 1 - hits[-1]
        return int(age) if age <= lookback else None
    except Exception:
        return None


def _recent_level_cross_age(series: Any, level: float, lookback: int = 20) -> int | None:
    try:
        values = series.dropna()
        if len(values) < 2:
            return None
        crossed = (values > level) & (values.shift(1) <= level)
        hits = [i for i, flag in enumerate(crossed.tolist()) if bool(flag)]
        if not hits:
            return None
        age = len(values) - 1 - hits[-1]
        return int(age) if age <= lookback else None
    except Exception:
        return None

def _max_drawdown_pct(close: Any) -> float | None:
    try:
        running_max = close.cummax()
        drawdown = close / running_max - 1.0
        return abs(float(drawdown.min())) * 100.0
    except Exception:
        return None


def _technical_fields(hist: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trace: list[dict[str, Any]] = []
    fields: dict[str, Any] = {}
    if hist is None or getattr(hist, "empty", True):
        return fields, [{"step": "price_history", "status": "MISSING", "detail": "Ingen prisserie mottatt"}]
    close = hist.get("Close")
    if close is None or len(close.dropna()) < 25:
        return fields, [{"step": "price_history", "status": "MISSING", "detail": "For få sluttkurser"}]
    close = close.dropna()
    volume = hist.get("Volume")
    fields["last_price"] = _series_value(close, -1)
    fields["return_1d"] = _return_pct(close, 1)
    fields["return_3d"] = _return_pct(close, 3)
    fields["return_5d"] = _return_pct(close, 5)
    fields["return_10d"] = _return_pct(close, 10)
    fields["return_15d"] = _return_pct(close, 15)
    fields["return_20d"] = _return_pct(close, 20)
    fields["return_60d"] = _return_pct(close, 60)
    fields["return_1m"] = _return_pct(close, 21)
    fields["return_3m"] = _return_pct(close, 63)
    fields["return_6m"] = _return_pct(close, 126)
    fields["rsi"] = _rsi(close)
    fields["rsi_score"] = None if fields["rsi"] is None else _clamp(100.0 - abs(fields["rsi"] - 60.0) * 2.0)
    sma20 = _finite(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    sma50 = _finite(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = _finite(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    fields["sma20"] = sma20
    fields["sma50"] = sma50
    fields["sma200"] = sma200
    last = fields.get("last_price")
    fields["price_vs_sma20_pct"] = ((float(last) / sma20) - 1.0) * 100.0 if last not in (None, 0) and sma20 not in (None, 0) else None
    fields["sma20_vs_sma50_pct"] = ((float(sma20) / sma50) - 1.0) * 100.0 if sma20 not in (None, 0) and sma50 not in (None, 0) else None
    fields["sma50_vs_sma200_pct"] = ((float(sma50) / sma200) - 1.0) * 100.0 if sma50 not in (None, 0) and sma200 not in (None, 0) else None
    try:
        sma20_series = close.rolling(20).mean()
        sma50_series = close.rolling(50).mean()
        sma200_series = close.rolling(200).mean()
        fields["golden_cross_active"] = bool(sma50 is not None and sma200 is not None and sma50 > sma200)
        fields["golden_cross_age_sessions"] = _recent_cross_age(sma50_series, sma200_series, 120)
        if len(sma20_series.dropna()) >= 6 and sma20 not in (None, 0):
            prev = _finite(sma20_series.dropna().iloc[-6])
            fields["sma20_slope_5d_pct"] = ((sma20 / prev) - 1.0) * 100.0 if prev not in (None, 0) else None
        if len(sma50_series.dropna()) >= 11 and sma50 not in (None, 0):
            prev = _finite(sma50_series.dropna().iloc[-11])
            fields["sma50_slope_10d_pct"] = ((sma50 / prev) - 1.0) * 100.0 if prev not in (None, 0) else None
        if sma50 not in (None, 0) and sma200 not in (None, 0):
            spread_now = (sma50 / sma200 - 1.0) * 100.0
            fields["golden_cross_spread_pct"] = spread_now
            if len(sma50_series.dropna()) >= 11 and len(sma200_series.dropna()) >= 11:
                old50 = _finite(sma50_series.iloc[-11]); old200 = _finite(sma200_series.iloc[-11])
                if old50 not in (None, 0) and old200 not in (None, 0):
                    old_spread = (old50 / old200 - 1.0) * 100.0
                    fields["golden_cross_spread_change_10d_pp"] = spread_now - old_spread
    except Exception:
        fields["golden_cross_active"] = False
        fields["golden_cross_age_sessions"] = None
    try:
        rsi_series = _rsi_series(close)
        fields["rsi_cross_50_age_sessions"] = _recent_level_cross_age(rsi_series, 50.0, 20) if rsi_series is not None else None
        fields["rsi_cross_60_age_sessions"] = _recent_level_cross_age(rsi_series, 60.0, 20) if rsi_series is not None else None
        fields["rsi_cross_70_age_sessions"] = _recent_level_cross_age(rsi_series, 70.0, 20) if rsi_series is not None else None
        if rsi_series is not None:
            rv = rsi_series.dropna()
            if len(rv) >= 12:
                prior_peak = _finite(rv.iloc[-11:-1].max())
                now_rsi = _finite(rv.iloc[-1])
                fields["rsi_10d_breakout"] = bool(now_rsi is not None and prior_peak is not None and now_rsi > prior_peak)
                fields["rsi_10d_breakout_margin"] = (now_rsi - prior_peak) if now_rsi is not None and prior_peak is not None else None
    except Exception:
        fields["rsi_cross_50_age_sessions"] = None
        fields["rsi_cross_70_age_sessions"] = None
    r1 = fields.get("return_1d")
    r3 = fields.get("return_3d")
    r5 = fields.get("return_5d")
    r10 = fields.get("return_10d")
    r20 = fields.get("return_20d")
    try:
        fields["momentum_acceleration_1v20"] = float(r1) - float(r20) / 20.0 if r1 is not None and r20 is not None else None
        fields["momentum_acceleration_3v20"] = float(r3) - float(r20) * 3.0 / 20.0 if r3 is not None and r20 is not None else None
        fields["momentum_acceleration_5v20"] = float(r5) - float(r20) / 4.0 if r5 is not None and r20 is not None else None
        fields["momentum_acceleration_10v20"] = float(r10) - float(r20) / 2.0 if r10 is not None and r20 is not None else None
    except Exception:
        fields["momentum_acceleration_5v20"] = None
        fields["momentum_acceleration_10v20"] = None
    if sma50 is not None and sma200 not in (None, 0):
        fields["trend_score"] = _clamp(50.0 + ((sma50 / sma200) - 1.0) * 500.0)
    elif sma50 is not None and fields["last_price"] not in (None, 0):
        fields["trend_score"] = _clamp(50.0 + ((fields["last_price"] / sma50) - 1.0) * 350.0)

    # RC16.31bf: compact, factual 60-session trend series for report charts and
    # discovery auditing. Values come only from the fetched market history.
    try:
        tail = close.tail(60)
        volume_aligned = volume.reindex(close.index) if volume is not None else None
        trend_rows = []
        for idx, value in tail.items():
            if _finite(value) is None:
                continue
            row = {
                "date": (idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]),
                "close": round(float(value), 6),
            }
            if volume_aligned is not None:
                try:
                    vv = _finite(volume_aligned.loc[idx])
                    if vv is not None:
                        row["volume"] = round(float(vv), 2)
                except Exception:
                    pass
            trend_rows.append(row)
        fields["price_trend_60d"] = trend_rows
    except Exception:
        fields["price_trend_60d"] = []
    try:
        high20 = _finite(close.tail(20).max()) if len(close) >= 20 else None
        high60 = _finite(close.tail(60).max()) if len(close) >= 60 else None
        prior20 = _finite(close.iloc[-21:-1].max()) if len(close) >= 21 else None
        prior60 = _finite(close.iloc[-61:-1].max()) if len(close) >= 61 else None
        low20 = _finite(close.tail(20).min()) if len(close) >= 20 else None
        low60 = _finite(close.tail(60).min()) if len(close) >= 60 else None
        last = fields.get("last_price")
        fields["high_20d"] = high20
        fields["high_60d"] = high60
        fields["prior_20d_high"] = prior20
        fields["prior_60d_high"] = prior60
        fields["low_20d"] = low20
        fields["low_60d"] = low60
        fields["distance_from_20d_high_pct"] = ((float(last) / high20) - 1.0) * 100.0 if last not in (None, 0) and high20 not in (None, 0) else None
        fields["distance_from_60d_high_pct"] = ((float(last) / high60) - 1.0) * 100.0 if last not in (None, 0) and high60 not in (None, 0) else None
        fields["breakout_20d_pct"] = ((float(last) / prior20) - 1.0) * 100.0 if last not in (None, 0) and prior20 not in (None, 0) else None
        fields["breakout_60d_pct"] = ((float(last) / prior60) - 1.0) * 100.0 if last not in (None, 0) and prior60 not in (None, 0) else None
        fields["breakout_20d"] = bool(fields.get("breakout_20d_pct") is not None and fields["breakout_20d_pct"] >= 0.0)
        fields["breakout_60d"] = bool(fields.get("breakout_60d_pct") is not None and fields["breakout_60d_pct"] >= 0.0)
    except Exception:
        pass
    if volume is not None:
        try:
            v = volume.reindex(close.index).fillna(0.0)
            avg20 = float(v.tail(20).mean()) if len(v) >= 20 else None
            latest_v = _finite(v.iloc[-1]) if len(v) else None
            if avg20 and latest_v is not None:
                fields["volume_ratio_20"] = latest_v / avg20
            direction = close.diff().fillna(0.0).map(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
            obv = (direction * v).cumsum()
            fields["obv"] = _finite(obv.iloc[-1]) if len(obv) else None
            if avg20 and avg20 > 0:
                for n in (5, 10, 20):
                    if len(obv) > n:
                        pressure = (float(obv.iloc[-1]) - float(obv.iloc[-1-n])) / (avg20 * n)
                        fields[f"obv_pressure_{n}d"] = max(-2.0, min(2.0, pressure))
        except Exception:
            pass

    # RC16.31bn: fresh-trend timing, compression/expansion and breakout quality.
    try:
        ret = close.pct_change()
        vol5 = float(ret.tail(5).std()) if len(ret.dropna()) >= 5 else None
        vol20 = float(ret.tail(20).std()) if len(ret.dropna()) >= 20 else None
        fields["volatility_expansion_5v20"] = (vol5 / vol20) if vol5 is not None and vol20 not in (None, 0) else None
        range10 = (float(close.tail(10).max()) / float(close.tail(10).min()) - 1.0) * 100.0 if len(close) >= 10 and float(close.tail(10).min()) > 0 else None
        prior40 = close.iloc[-50:-10] if len(close) >= 50 else close.iloc[:-10]
        range40 = (float(prior40.max()) / float(prior40.min()) - 1.0) * 100.0 if len(prior40) >= 10 and float(prior40.min()) > 0 else None
        fields["range_10d_pct"] = range10
        fields["prior_range_40d_pct"] = range40
        fields["compression_ratio_10v40"] = (range10 / range40) if range10 is not None and range40 not in (None, 0) else None
    except Exception:
        pass
    try:
        rolling20_prev = close.shift(1).rolling(20).max()
        breakout_mask = close >= rolling20_prev
        recent_hits = [i for i, flag in enumerate(breakout_mask.tail(15).tolist()) if bool(flag)]
        if recent_hits:
            age = len(breakout_mask.tail(15)) - 1 - recent_hits[-1]
            fields["breakout_20d_age_sessions"] = int(age)
            idx = breakout_mask.tail(15).index[recent_hits[-1]]
            level = _finite(rolling20_prev.loc[idx])
            fields["breakout_20d_event_level"] = level
            if level not in (None, 0):
                after = close.loc[idx:]
                fields["breakout_hold_sessions"] = int(sum(float(x) >= float(level) for x in after.tail(5)))
                fields["breakout_holding"] = bool(float(close.iloc[-1]) >= float(level))
        else:
            fields["breakout_20d_age_sessions"] = None
            fields["breakout_hold_sessions"] = 0
            fields["breakout_holding"] = False
    except Exception:
        pass
    try:
        high = hist.get("High"); low = hist.get("Low")
        if high is not None and low is not None:
            h = high.reindex(close.index).dropna(); l = low.reindex(close.index).dropna()
            if len(h) and len(l):
                hh = _finite(h.iloc[-1]); ll = _finite(l.iloc[-1]); cc = _finite(close.iloc[-1])
                if hh is not None and ll is not None and cc is not None and hh > ll:
                    fields["close_location_in_day"] = (cc - ll) / (hh - ll)
                    fields["daily_range_pct"] = (hh / ll - 1.0) * 100.0 if ll > 0 else None
    except Exception:
        pass
    try:
        # Compact support/resistance ladder from recent closing-price pivots.
        vals = [float(x) for x in close.tail(60).tolist() if _finite(x) is not None]
        lastv = float(close.iloc[-1])
        pivots = []
        for i in range(2, len(vals)-2):
            v = vals[i]
            if v >= max(vals[i-2:i] + vals[i+1:i+3]) or v <= min(vals[i-2:i] + vals[i+1:i+3]):
                pivots.append(v)
        def cluster(levels):
            out=[]
            for v in sorted(levels):
                if not out or abs(v/out[-1]-1.0) > 0.012:
                    out.append(v)
                else:
                    out[-1]=(out[-1]+v)/2.0
            return out
        cl=cluster(pivots)
        fields["support_levels"] = [round(v,4) for v in sorted([v for v in cl if v < lastv], reverse=True)[:4]]
        fields["resistance_levels"] = [round(v,4) for v in sorted([v for v in cl if v > lastv])[:4]]
    except Exception:
        fields["support_levels"] = []
        fields["resistance_levels"] = []

    returns = close.pct_change().dropna()
    if len(returns) >= 20:
        fields["volatility_pct"] = float(returns.std() * math.sqrt(252) * 100.0)
        mean = float(returns.mean() * 252)
        std = float(returns.std() * math.sqrt(252))
        fields["sharpe_ratio"] = mean / std if std > 0 else None
    fields["max_drawdown_pct"] = _max_drawdown_pct(close)
    if volume is not None:
        try:
            avg_volume = float(volume.dropna().tail(60).mean())
            if math.isfinite(avg_volume) and avg_volume > 0:
                fields["average_volume"] = avg_volume
        except Exception:
            pass
    momentum_parts = [x for x in (fields.get("return_1m"), fields.get("return_3m"), fields.get("trend_score")) if x is not None]
    if momentum_parts:
        components = []
        if fields.get("return_1m") is not None:
            components.append(_clamp(50 + fields["return_1m"] * 2.5))
        if fields.get("return_3m") is not None:
            components.append(_clamp(50 + fields["return_3m"] * 1.5))
        if fields.get("trend_score") is not None:
            components.append(fields["trend_score"])
        if fields.get("rsi_score") is not None:
            components.append(fields["rsi_score"])
        fields["momentum_score"] = sum(components) / len(components)
    trace.append({"step": "price_history", "status": "OK", "detail": f"{len(close)} sluttkurser"})
    for key in ("return_1m", "return_3m", "rsi", "trend_score", "volatility_pct", "max_drawdown_pct", "average_volume"):
        trace.append({"step": key, "status": "OK" if fields.get(key) is not None else "MISSING", "value": fields.get(key)})
    return fields, trace


def _fundamental_fields(info: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mapping = {
        "trailing_pe": ("trailingPE", "forwardPE"),
        "roe": ("returnOnEquity",),
        "debt_to_equity": ("debtToEquity",),
        "earnings_growth": ("earningsGrowth",),
        "revenue_growth": ("revenueGrowth",),
        "beta": ("beta",),
        "target_mean_price": ("targetMeanPrice",),
        "recommendation_mean": ("recommendationMean",),
        "market_cap": ("marketCap",),
        "sector": ("sector",),
        "industry": ("industry",),
        "shortName": ("shortName", "longName"),
        "currency": ("currency",),
    }
    fields: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    for target, names in mapping.items():
        value = None
        for name in names:
            if info.get(name) not in (None, ""):
                value = info.get(name)
                break
        if target in {"roe", "earnings_growth", "revenue_growth"}:
            value = _safe_pct(_finite(value))
        elif target not in {"sector", "industry", "shortName", "currency"}:
            value = _finite(value)
        if value not in (None, ""):
            fields[target] = value
        trace.append({"step": target, "status": "OK" if value not in (None, "") else "MISSING", "value": value})
    last_price = None
    target = _finite(fields.get("target_mean_price"))
    if target is not None:
        fields["target_mean_price"] = target
    return fields, trace


def enrich_candidate_row(row: Mapping[str, Any], use_cache: bool = True, force_refresh: bool = False) -> dict[str, Any]:
    base = dict(row)
    original_ticker = str(base.get("ticker") or base.get("symbol") or "").strip().upper()
    ticker = canonical_market_ticker(original_ticker, str(base.get("market") or base.get("source_market") or ""))
    base["ticker"] = ticker
    base["symbol"] = ticker
    if original_ticker and original_ticker != ticker:
        base["ticker_normalization"] = {
            "input": original_ticker,
            "canonical": ticker,
            "market": str(base.get("market") or base.get("source_market") or ""),
            "reason": "MARKET_SUFFIX_ADDED",
        }
    if not ticker:
        base.update({"data_fetch_status": "ERROR", "data_fetch_error": "Mangler ticker", "analysis_trace": []})
        return base
    request_started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prior_snapshot = _read_cache_snapshot(ticker)
    if use_cache and not force_refresh:
        cached = _read_cache(ticker)
        if cached:
            cached.update({k: v for k, v in base.items() if v not in (None, "")})
            cached["data_fetch_status"] = "CACHE"
            cached["force_refresh"] = False
            cached["force_refresh_requested"] = False
            cached["cache_bypass_applied"] = False
            cached["fetch_started_at"] = request_started
            cached["fetch_completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cached["refresh_proof"] = "CACHE_USED"
            return cached
    quarantine = quarantine_status(ticker)
    if quarantine.get("active") and not force_refresh:
        base.update({
            "data_fetch_status": "QUARANTINED",
            "data_fetch_error": str(quarantine.get("last_error") or "REPEATED_NO_MARKET_DATA"),
            "analysis_trace": [{
                "step": "ticker_health", "status": "QUARANTINED",
                "detail": str(quarantine.get("quarantine_reason") or "REPEATED_NO_MARKET_DATA"),
                "quarantined_until": quarantine.get("quarantined_until"),
            }],
            "ticker_health": quarantine,
            "fetch_started_at": request_started,
            "fetch_completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "refresh_proof": "LIVE_SKIPPED_QUARANTINE",
        })
        return base
    trace: list[dict[str, Any]] = [{
        "step": "cache_policy",
        "status": "BYPASSED" if force_refresh else "MISS",
        "detail": "Cache ble eksplisitt ignorert" if force_refresh else "Ingen gyldig cache; live innhenting startet",
        "force_refresh_requested": bool(force_refresh),
    }]
    try:
        import yfinance as yf
        yf_ticker = yf.Ticker(ticker)
        hist = yf_ticker.history(
            period="1y", interval="1d", auto_adjust=True, actions=False,
            timeout=FETCH_TIMEOUT_SECONDS,
        )
        latest_trade_date = None
        latest_trade_timestamp = None
        try:
            if hist is not None and not hist.empty:
                idx = hist.index[-1]
                latest_trade_timestamp = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
                latest_trade_date = str(getattr(idx, "date", lambda: idx)())
        except Exception:
            pass
        technical, technical_trace = _technical_fields(hist)
        trace.extend(technical_trace)
        info: dict[str, Any] = {}
        info_value, info_error = _call_with_timeout(lambda: dict(yf_ticker.info or {}), INFO_TIMEOUT_SECONDS)
        if isinstance(info_value, Mapping):
            info = dict(info_value)
        elif info_error:
            status = "TIMEOUT" if info_error.startswith("TIMEOUT_AFTER_") else "ERROR"
            trace.append({"step": "company_info", "status": status, "detail": info_error})
        fundamental, fundamental_trace = _fundamental_fields(info)
        trace.extend(fundamental_trace)
        enriched = dict(base)
        enriched.update({k: v for k, v in technical.items() if v is not None})
        enriched.update({k: v for k, v in fundamental.items() if v not in (None, "")})
        last_price = _finite(enriched.get("last_price"))
        target = _finite(enriched.get("target_mean_price"))
        if last_price not in (None, 0) and target is not None:
            enriched["target_upside"] = (target / last_price - 1.0) * 100.0
        rec = _finite(enriched.get("recommendation_mean"))
        if rec is not None:
            enriched["recommendation_score"] = _clamp((5.0 - rec) / 4.0 * 100.0)
        observed = [k for k in ("return_1m", "return_3m", "rsi", "volatility_pct", "max_drawdown_pct", "average_volume", "trailing_pe", "roe", "debt_to_equity", "earnings_growth", "revenue_growth", "beta", "target_upside") if enriched.get(k) is not None]
        enriched["raw_fields_available"] = observed
        enriched["analysis_trace"] = trace
        enriched["data_fetch_status"] = "OK" if observed else "NO_DATA"
        enriched["data_fetch_error"] = "" if observed else "Ingen individuelle markeds- eller selskapsdata funnet"
        enriched["enriched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        enriched["cache_hit"] = False
        enriched["cache_age_seconds"] = 0.0
        enriched["cache_age_minutes"] = 0.0
        enriched["cache_ttl_seconds"] = CACHE_TTL_SECONDS
        enriched["cache_path"] = str(_cache_path(ticker))
        enriched["data_source"] = "yfinance-live"
        enriched["force_refresh"] = bool(force_refresh)
        enriched["force_refresh_requested"] = bool(force_refresh)
        enriched["cache_bypass_applied"] = bool(force_refresh)
        enriched["fetch_started_at"] = request_started
        enriched["fetch_completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        enriched["latest_trade_date"] = latest_trade_date
        enriched["latest_trade_timestamp"] = latest_trade_timestamp
        enriched["prior_cache_snapshot"] = prior_snapshot
        old_price = _finite(prior_snapshot.get("last_price"))
        new_price = _finite(enriched.get("last_price"))
        enriched["market_data_changed"] = (abs(old_price-new_price) > 1e-10) if old_price is not None and new_price is not None else None
        enriched["refresh_proof"] = "LIVE_CACHE_BYPASSED" if force_refresh else "LIVE_CACHE_MISS"
        trace.append({"step": "refresh_proof", "status": "OK", "detail": enriched["refresh_proof"], "latest_trade_date": latest_trade_date, "market_data_changed": enriched["market_data_changed"]})
        _write_cache(ticker, enriched)
        if observed:
            record_ticker_success(ticker)
        else:
            enriched["ticker_health"] = record_ticker_failure(ticker, "NO_MARKET_DATA")
        return enriched
    except Exception as exc:
        base.update({
            "data_fetch_status": "ERROR", "data_fetch_error": str(exc),
            "analysis_trace": trace + [{"step": "enrichment", "status": "ERROR", "detail": str(exc)}],
            "force_refresh": bool(force_refresh), "force_refresh_requested": bool(force_refresh),
            "cache_bypass_applied": bool(force_refresh), "fetch_started_at": request_started,
            "fetch_completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "refresh_proof": "LIVE_ATTEMPT_FAILED" if force_refresh else "FETCH_FAILED",
        })
        base["ticker_health"] = record_ticker_failure(ticker, f"{type(exc).__name__}: {str(exc)[:180]}")
        return base



def _enrich_with_retry(row: Mapping[str, Any], force_refresh: bool, attempts: int = FETCH_ATTEMPTS) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(1, max(1, attempts) + 1):
        last = enrich_candidate_row(row, use_cache=True, force_refresh=force_refresh)
        fetch_status = str(last.get("data_fetch_status") or "").upper()
        if fetch_status not in {"ERROR", "NO_DATA"}:
            last["fetch_attempts"] = attempt
            return last
        # A clean Yahoo response with no usable fields is not improved by an
        # immediate identical retry. Preserve the failure and move on.
        if fetch_status == "NO_DATA":
            last["fetch_attempts"] = attempt
            return last
        if attempt < attempts:
            time.sleep(0.75 * attempt)
    last["fetch_attempts"] = max(1, attempts)
    return last

def enrich_candidate_rows(rows: Sequence[Mapping[str, Any]], max_workers: int = 6, progress_callback: Callable[[int, int, str], None] | None = None, force_refresh: bool = False) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        unique.append(dict(row))
    total = len(unique)
    if not total:
        return []
    output: dict[str, dict[str, Any]] = {}
    pool = ThreadPoolExecutor(max_workers=max(1, min(max_workers, total)))
    futures = {}
    try:
        futures = {pool.submit(_enrich_with_retry, row, force_refresh, FETCH_ATTEMPTS): str(row.get("ticker") or row.get("symbol") or "").upper() for row in unique}
        completed = 0
        try:
            for future in as_completed(futures, timeout=MARKET_ENRICH_TIMEOUT_SECONDS):
                ticker = futures[future]
                try:
                    output[ticker] = future.result()
                except Exception as exc:
                    output[ticker] = {"ticker": ticker, "data_fetch_status": "ERROR", "data_fetch_error": str(exc), "analysis_trace": []}
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, ticker)
        except FuturesTimeoutError:
            for future, ticker in futures.items():
                if ticker in output:
                    continue
                future.cancel()
                output[ticker] = {
                    "ticker": ticker,
                    "data_fetch_status": "ERROR",
                    "data_fetch_error": f"MARKET_DATA_TIMEOUT_AFTER_{MARKET_ENRICH_TIMEOUT_SECONDS:g}s",
                    "analysis_trace": [{"step": "enrichment", "status": "TIMEOUT", "detail": "Markedsfristen ble nådd"}],
                    "fetch_completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, ticker)
    except Exception:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=False, cancel_futures=True)
    return [output.get(str(row.get("ticker") or row.get("symbol") or "").strip().upper(), dict(row)) for row in unique]
