"""Insider Intelligence Engine v18.7.1.

Uses public insider transaction data when available. Missing coverage is represented
as neutral/unknown and never fabricated. Results are cached to reduce provider load.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
import json, math, time

from storage_architecture import runtime_data_path

VERSION = "v18.7.1"
CACHE_PATH = runtime_data_path("insider_intelligence") / "cache.json"
CACHE_TTL_SECONDS = 24 * 3600

ROLE_WEIGHTS = {
    "chief executive": 1.00, "ceo": 1.00, "president": 0.85,
    "chief financial": 0.95, "cfo": 0.95, "chair": 0.90,
    "director": 0.70, "officer": 0.65, "vp": 0.55,
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    except Exception:
        return {}


def _save_cache(data: Mapping[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(dict(data), ensure_ascii=False, indent=2), encoding="utf-8")


def _role_weight(role: str) -> float:
    text = str(role or "").lower()
    return max((weight for token, weight in ROLE_WEIGHTS.items() if token in text), default=0.45)


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "reset_index") and hasattr(value, "to_dict"):
        try:
            return [dict(x) for x in value.reset_index().to_dict("records")]
        except Exception:
            pass
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(x) for x in value if isinstance(x, Mapping)]
    return []


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).lower().replace("_", " "): v for k, v in row.items()}
    for name in names:
        key = name.lower().replace("_", " ")
        if key in lowered:
            return lowered[key]
    return None


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        try: return value.to_pydatetime().replace(tzinfo=timezone.utc)
        except Exception: pass
    text = str(value).strip()
    for candidate in (text[:10], text):
        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return dt.replace(tzinfo=dt.tzinfo or timezone.utc)
        except Exception:
            continue
    return None


def _transaction_type(row: Mapping[str, Any]) -> str:
    text = " ".join(str(_pick(row, x) or "") for x in ("transaction", "text", "type", "transaction type")).lower()
    shares = _f(_pick(row, "shares", "shares traded", "position change"), 0.0)
    if any(x in text for x in ("sale", "sell", "disposed", "disposition")) or shares < 0:
        return "SELL"
    if any(x in text for x in ("purchase", "buy", "acquired", "acquisition")) or shares > 0:
        return "BUY"
    return "OTHER"


def score_transactions(ticker: str, rows: Sequence[Mapping[str, Any]], lookback_days: int = 90) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    evidence, weighted_buy, weighted_sell = [], 0.0, 0.0
    buyers, sellers, total_buy, total_sell = set(), set(), 0.0, 0.0
    for raw in rows:
        row = dict(raw)
        dt = _parse_date(_pick(row, "start date", "date", "transaction date", "filing date"))
        age = (now - dt).days if dt else lookback_days
        if age < 0 or age > lookback_days:
            continue
        kind = _transaction_type(row)
        if kind == "OTHER":
            continue
        insider = str(_pick(row, "insider", "insider name", "owner", "name") or "Ukjent insider")
        role = str(_pick(row, "position", "title", "relationship") or "")
        shares = abs(_f(_pick(row, "shares", "shares traded", "position change"), 0.0))
        value = abs(_f(_pick(row, "value", "transaction value", "total value"), 0.0))
        if not value:
            price = abs(_f(_pick(row, "value", "price", "transaction price"), 0.0))
            value = shares * price if shares and price else shares
        recency = max(0.15, 1.0 - age / max(1, lookback_days))
        importance = _role_weight(role)
        magnitude = min(1.0, math.log10(max(value, 1.0)) / 7.0)
        weighted = (0.45 * recency + 0.30 * importance + 0.25 * magnitude)
        if kind == "BUY":
            weighted_buy += weighted; total_buy += value; buyers.add(insider)
        else:
            weighted_sell += weighted; total_sell += value; sellers.add(insider)
        evidence.append({
            "date": dt.date().isoformat() if dt else "Ukjent", "type": kind,
            "insider": insider, "role": role or "Ukjent rolle", "shares": round(shares, 2),
            "value": round(value, 2), "age_days": age,
        })
    evidence.sort(key=lambda x: (x["date"], x["value"]), reverse=True)
    if not evidence:
        return {"ticker": ticker, "score": 50.0, "signal": "INGEN DATA", "coverage": "MISSING", "buy_count": 0, "sell_count": 0, "net_value": 0.0, "evidence": [], "reason": "Ingen dokumenterte insidertransaksjoner i tilgjengelig datakilde."}
    cluster_bonus = min(12.0, max(0, len(buyers) - 1) * 4.0)
    direction = (weighted_buy - weighted_sell) / max(0.8, weighted_buy + weighted_sell)
    score = max(0.0, min(100.0, 50.0 + direction * 34.0 + cluster_bonus))
    signal = "STERKT POSITIV" if score >= 78 else "POSITIV" if score >= 62 else "NØYTRAL" if score >= 42 else "NEGATIV" if score >= 25 else "STERKT NEGATIV"
    return {
        "ticker": ticker, "score": round(score, 2), "signal": signal, "coverage": "AVAILABLE",
        "buy_count": sum(1 for x in evidence if x["type"] == "BUY"),
        "sell_count": sum(1 for x in evidence if x["type"] == "SELL"),
        "unique_buyers": len(buyers), "unique_sellers": len(sellers),
        "buy_value": round(total_buy, 2), "sell_value": round(total_sell, 2),
        "net_value": round(total_buy - total_sell, 2), "evidence": evidence[:10],
        "reason": f"{len(buyers)} kjøper(e), {len(sellers)} selger(e) siste {lookback_days} dager.",
    }


def fetch_insider_intelligence(ticker: str, force_refresh: bool = False, lookback_days: int = 90) -> dict[str, Any]:
    ticker = str(ticker or "").upper().strip()
    cache = _load_cache(); cached = cache.get(ticker)
    if cached and not force_refresh and time.time() - _f(cached.get("cached_at"), 0) < CACHE_TTL_SECONDS:
        return dict(cached.get("result") or {})
    try:
        import yfinance as yf
        obj = yf.Ticker(ticker)
        value = None
        for attr in ("insider_transactions", "get_insider_transactions"):
            try:
                candidate = getattr(obj, attr)
                value = candidate() if callable(candidate) else candidate
                if value is not None: break
            except Exception:
                continue
        result = score_transactions(ticker, _records(value), lookback_days=lookback_days)
        result["source"] = "yfinance/public filings"
        result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        result = {"ticker": ticker, "score": 50.0, "signal": "KILDEFEIL", "coverage": "ERROR", "buy_count": 0, "sell_count": 0, "net_value": 0.0, "evidence": [], "reason": str(exc), "source": "unavailable"}
    cache[ticker] = {"cached_at": time.time(), "result": result}; _save_cache(cache)
    return result


def enrich_rows(rows: Sequence[Mapping[str, Any]], force_refresh: bool = False) -> list[dict[str, Any]]:
    enriched = []
    for row in rows:
        clean = dict(row); insider = fetch_insider_intelligence(str(clean.get("ticker") or ""), force_refresh=force_refresh)
        clean["insider_intelligence"] = insider
        clean["insider_score"] = insider.get("score", 50.0)
        clean["insider_signal"] = insider.get("signal", "INGEN DATA")
        enriched.append(clean)
    return enriched
