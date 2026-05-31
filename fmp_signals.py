from __future__ import annotations

import datetime as dt
import os
from typing import Any

import requests

from runtime_env import data_source_env_status, env_value, has_configured_key, load_app_env, redact_secrets


load_app_env()

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT_SECONDS = float(os.getenv("FMP_TIMEOUT_SECONDS", "8") or 8)


def fmp_has_key() -> bool:
    return has_configured_key("FMP_API_KEY")


def fmp_api_status() -> dict[str, Any]:
    status = data_source_env_status()
    return {
        "provider": "Financial Modeling Prep stable API",
        "has_key": bool(status.get("fmp_key")),
        "env_loaded": bool(status.get("env_loaded")),
        "env_sources": list(status.get("env_sources") or []),
        "endpoints": [
            "analyst-estimates",
            "grades-consensus",
            "price-target-consensus",
            "earnings",
            "insider-trading/search",
            "actively-trading-list",
        ],
    }


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    number = _safe_float(value, None)
    if number is None:
        return default
    return int(number)


def _first_value(row: dict[str, Any] | None, *keys: str) -> Any:
    if not isinstance(row, dict):
        return None
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [dict(row) for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("data", "items", "results"):
            if isinstance(data.get(key), list):
                return [dict(row) for row in data.get(key) if isinstance(row, dict)]
        return [dict(data)] if data else []
    return []


def _parse_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return dt.datetime.strptime(candidate, fmt).date()
            except Exception:
                continue
    return None


def _days_ago(value: Any) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return max(0, (dt.date.today() - parsed).days)


def _request_json(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    api_key = env_value("FMP_API_KEY")
    if not api_key:
        return {"error": "FMP_API_KEY mangler"}
    url = endpoint if endpoint.startswith("http") else f"{FMP_BASE_URL}/{endpoint.lstrip('/')}"
    request_params = dict(params or {})
    request_params["apikey"] = api_key
    try:
        response = requests.get(url, params=request_params, timeout=FMP_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            error_text = data.get("Error Message") or data.get("error") or data.get("message")
            if error_text and "limit" in str(error_text).lower():
                return {"error": redact_secrets(error_text)}
        return data
    except Exception as exc:
        return {"error": redact_secrets(f"FMP API-feil: {type(exc).__name__}: {exc}")}


def _score_from_rating_counts(row: dict[str, Any]) -> tuple[float | None, dict[str, int]]:
    counts = {
        "strongBuy": _safe_int(_first_value(row, "strongBuy", "strong_buy", "strongBuyCount")),
        "buy": _safe_int(_first_value(row, "buy", "buyCount")),
        "hold": _safe_int(_first_value(row, "hold", "holdCount")),
        "sell": _safe_int(_first_value(row, "sell", "sellCount")),
        "strongSell": _safe_int(_first_value(row, "strongSell", "strong_sell", "strongSellCount")),
    }
    total = sum(counts.values())
    if total <= 0:
        return None, counts
    positive = counts["strongBuy"] * 1.25 + counts["buy"]
    negative = counts["sell"] + counts["strongSell"] * 1.25
    score = 5.0 + ((positive - negative) / max(total, 1)) * 3.0
    return round(max(0.0, min(10.0, score)), 2), counts


def _grade_action_score(rows: list[dict[str, Any]]) -> tuple[float | None, str]:
    recent = []
    for row in rows[:20]:
        date_value = _first_value(row, "publishedDate", "date", "gradingDate", "updated")
        age = _days_ago(date_value)
        if age is not None and age > 120:
            continue
        action = str(_first_value(row, "action", "gradeAction", "newGrade", "rating") or "").lower()
        previous = str(_first_value(row, "previousGrade", "previousRating") or "").lower()
        current = str(_first_value(row, "newGrade", "rating", "grade") or "").lower()
        text = f"{action} {previous} {current}"
        if any(word in text for word in ("upgrade", "overweight", "outperform", "buy", "strong buy")):
            recent.append(("opp", row))
        elif any(word in text for word in ("downgrade", "underweight", "underperform", "sell", "strong sell")):
            recent.append(("ned", row))
    if not recent:
        return None, "Ingen ferske ratingendringer funnet"
    up = sum(1 for direction, _ in recent if direction == "opp")
    down = sum(1 for direction, _ in recent if direction == "ned")
    score = max(0.0, min(10.0, 5.0 + up * 0.65 - down * 0.80))
    return round(score, 2), f"Ratingendringer siste 120 dager: opp {up}, ned {down}"


def _price_target_score(consensus: dict[str, Any], quote: dict[str, Any]) -> tuple[float | None, str]:
    target = _safe_float(_first_value(
        consensus,
        "targetConsensus",
        "targetMedian",
        "targetMean",
        "priceTargetConsensus",
        "consensus",
        "median",
    ))
    price = _safe_float(_first_value(quote, "price", "previousClose", "close", "lastPrice"))
    if target is None:
        return None, "Price target mangler"
    if price is None or price <= 0:
        return None, f"Price target {target:.2f}, men kurs mangler"
    upside = (target / price - 1.0) * 100.0
    score = max(0.0, min(10.0, 5.0 + upside / 10.0))
    return round(score, 2), f"Price target {target:.2f} mot kurs {price:.2f} ({upside:+.1f}%)"


def _estimate_detail(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Analytikerestimater mangler"
    row = rows[0]
    period = _first_value(row, "date", "fiscalDateEnding", "period", "calendarYear") or "-"
    eps = _first_value(row, "estimatedEpsAvg", "epsAvg", "estimatedEPSAvg", "epsEstimated")
    revenue = _first_value(row, "estimatedRevenueAvg", "revenueAvg", "estimatedRevenue")
    analysts = _first_value(row, "numberAnalystsEstimatedEps", "numberAnalystEstimatedEps", "analysts")
    bits = [f"periode {period}"]
    if eps not in (None, ""):
        bits.append(f"EPS-estimat {eps}")
    if revenue not in (None, ""):
        bits.append(f"omsetningsestimat {revenue}")
    if analysts not in (None, ""):
        bits.append(f"analytikere {analysts}")
    return " | ".join(bits)


def fetch_fmp_analyst_signal(ticker: str) -> dict[str, Any]:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {"error": "Ticker mangler", "source": "FMP analyst"}
    if not fmp_has_key():
        return {"error": "FMP_API_KEY mangler", "source": "FMP analyst"}

    grades_consensus = _rows(_request_json("grades-consensus", {"symbol": symbol}))
    price_target = _rows(_request_json("price-target-consensus", {"symbol": symbol}))
    estimates = _rows(_request_json("analyst-estimates", {"symbol": symbol, "period": "annual", "page": 0, "limit": 10}))
    grade_actions = _rows(_request_json("grades", {"symbol": symbol, "limit": 20}))
    quote_rows = _rows(_request_json("quote", {"symbol": symbol}))

    score_parts: list[tuple[float, float]] = []
    details: list[str] = []
    counts: dict[str, int] = {}

    if grades_consensus:
        grade_score, counts = _score_from_rating_counts(grades_consensus[0])
        if grade_score is not None:
            score_parts.append((grade_score, 0.45))
            details.append(
                "Konsensus "
                f"SB {counts.get('strongBuy', 0)}, B {counts.get('buy', 0)}, H {counts.get('hold', 0)}, "
                f"S {counts.get('sell', 0)}, SS {counts.get('strongSell', 0)}"
            )

    if price_target:
        target_score, target_detail = _price_target_score(price_target[0], quote_rows[0] if quote_rows else {})
        if target_score is not None:
            score_parts.append((target_score, 0.35))
        details.append(target_detail)

    action_score, action_detail = _grade_action_score(grade_actions)
    if action_score is not None:
        score_parts.append((action_score, 0.20))
    details.append(action_detail)

    if estimates:
        details.append(_estimate_detail(estimates))

    if not score_parts:
        return {
            "score": None,
            "trend": "neutral",
            "detail": "Ingen FMP analytiker-/estimatfunn",
            "error": None,
            "source": "FMP analyst/estimates",
        }

    total_weight = sum(weight for _, weight in score_parts) or 1.0
    score = sum(value * weight for value, weight in score_parts) / total_weight
    trend = "up" if score >= 6.4 else "down" if score <= 4.0 else "neutral"
    return {
        "score": round(score, 2),
        "trend": trend,
        "detail": " | ".join(part for part in details if part),
        "counts": counts,
        "error": None,
        "source": "FMP analyst/estimates",
    }


def fetch_fmp_earnings_signal(ticker: str) -> dict[str, Any]:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {"error": "Ticker mangler", "source": "FMP earnings"}
    if not fmp_has_key():
        return {"error": "FMP_API_KEY mangler", "source": "FMP earnings"}

    earnings_rows = _rows(_request_json("earnings", {"symbol": symbol, "limit": 8}))
    if not earnings_rows:
        return {"date": None, "error": None, "detail": "Ingen FMP earnings-rader", "source": "FMP earnings"}

    selected = earnings_rows[0]
    for row in earnings_rows:
        actual = _safe_float(_first_value(row, "epsActual", "actualEarningResult", "actualEPS", "eps"))
        estimate = _safe_float(_first_value(row, "epsEstimated", "estimatedEarning", "epsEstimate", "estimatedEPS"))
        if actual is not None or estimate is not None:
            selected = row
            break

    date_value = _first_value(selected, "date", "fiscalDateEnding", "period")
    actual_eps = _safe_float(_first_value(selected, "epsActual", "actualEarningResult", "actualEPS", "eps"))
    estimate_eps = _safe_float(_first_value(selected, "epsEstimated", "estimatedEarning", "epsEstimate", "estimatedEPS"))
    surprise_pct = None
    if actual_eps is not None and estimate_eps not in (None, 0):
        surprise_pct = ((actual_eps - estimate_eps) / abs(estimate_eps)) * 100.0

    detail_bits = []
    if date_value:
        detail_bits.append(f"dato {str(date_value)[:10]}")
    if estimate_eps is not None:
        detail_bits.append(f"EPS-estimat {estimate_eps:.3g}")
    if actual_eps is not None:
        detail_bits.append(f"EPS faktisk {actual_eps:.3g}")
    if surprise_pct is not None:
        detail_bits.append(f"surprise {surprise_pct:+.1f}%")

    return {
        "date": str(date_value)[:10] if date_value else None,
        "epsEstimate": estimate_eps,
        "epsActual": actual_eps,
        "epsSurprisePct": round(surprise_pct, 2) if surprise_pct is not None else None,
        "detail": " | ".join(detail_bits) or "FMP earnings funnet",
        "error": None,
        "source": "FMP earnings",
    }


def _insider_type(row: dict[str, Any]) -> str:
    code = str(_first_value(row, "acquisitionOrDisposition", "transactionAcquiredDisposedCode", "transactionCode") or "").upper()
    text = str(_first_value(row, "transactionType", "type", "securityTitle") or "").upper()
    if code == "A" or any(word in text for word in ("BUY", "PURCHASE", "ACQUIRE")):
        return "BUY"
    if code == "D" or any(word in text for word in ("SELL", "SALE", "DISPOSE")):
        return "SELL"
    return "UNKNOWN"


def fetch_fmp_insider_signal(ticker: str, months: int = 6) -> dict[str, Any]:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {"error": "Ticker mangler", "source": "FMP insider"}
    if not fmp_has_key():
        return {"error": "FMP_API_KEY mangler", "source": "FMP insider"}

    raw_rows = _rows(_request_json("insider-trading/search", {"symbol": symbol, "page": 0, "limit": 100}))
    max_days = max(31, int(months or 6) * 31)
    transactions: list[dict[str, Any]] = []
    for row in raw_rows:
        date_value = _first_value(row, "transactionDate", "filingDate", "date", "publishedDate")
        age = _days_ago(date_value)
        if age is not None and age > max_days:
            continue
        shares = abs(_safe_float(_first_value(row, "securitiesTransacted", "transactionShares", "shares"), 0.0) or 0.0)
        price = _safe_float(_first_value(row, "price", "transactionPrice"), None)
        value = _safe_float(_first_value(row, "transactionValue", "value"), None)
        if value is None and price is not None:
            value = shares * price
        transactions.append({
            "date": str(date_value)[:10] if date_value else "",
            "type": _insider_type(row),
            "shares": shares,
            "price": price,
            "value": value,
            "name": _first_value(row, "reportingName", "name", "insiderName") or "",
            "relation": _first_value(row, "typeOfOwner", "officerTitle", "relationship") or "",
            "days_ago": age,
        })

    transactions.sort(key=lambda row: row.get("date") or "", reverse=True)
    buy_rows = [row for row in transactions if row.get("type") == "BUY"]
    sell_rows = [row for row in transactions if row.get("type") == "SELL"]
    if not transactions:
        return {
            "score": None,
            "label": "Ingen FMP insiderhandler",
            "transactions": 0,
            "latest_transactions": [],
            "latest_type": "NONE",
            "latest_date": None,
            "error": None,
            "source": "FMP insider",
        }

    buy_weight = sum(max(1.0, min(8.0, ((_safe_float(row.get("value"), 0.0) or 0.0) / 100000.0) ** 0.5)) for row in buy_rows)
    sell_weight = sum(max(1.0, min(8.0, ((_safe_float(row.get("value"), 0.0) or 0.0) / 100000.0) ** 0.5)) for row in sell_rows)
    total = buy_weight + sell_weight * 0.65
    score = 5.0 if total <= 0 else 10.0 * buy_weight / total
    label = "Positivt FMP-insiderbilde" if score >= 6.5 else "Negativt FMP-insiderbilde" if score <= 3.5 else "Blandet FMP-insiderbilde"
    latest = transactions[:8]
    return {
        "score": round(max(0.0, min(10.0, score)), 2),
        "label": label,
        "buy_count": len(buy_rows),
        "sell_count": len(sell_rows),
        "buy_shares": round(sum(_safe_float(row.get("shares"), 0.0) or 0.0 for row in buy_rows), 2),
        "sell_shares": round(sum(_safe_float(row.get("shares"), 0.0) or 0.0 for row in sell_rows), 2),
        "transactions": len(transactions),
        "latest_transactions": latest,
        "latest_type": latest[0].get("type") if latest else "NONE",
        "latest_date": latest[0].get("date") if latest else None,
        "detail": f"FMP insider: kjøp {len(buy_rows)}, salg {len(sell_rows)}, transaksjoner {len(transactions)}",
        "error": None,
        "source": "FMP insider",
    }


def fetch_fmp_signal_packet(ticker: str) -> dict[str, Any]:
    symbol = str(ticker or "").strip().upper()
    packet = {
        "ticker": symbol,
        "provider": "Financial Modeling Prep",
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "enabled": fmp_has_key(),
        "analyst": {},
        "earnings": {},
        "insider": {},
    }
    if not symbol:
        packet["status"] = "Ticker mangler"
        return packet
    if not packet["enabled"]:
        packet["status"] = "FMP_API_KEY mangler"
        return packet
    packet["analyst"] = fetch_fmp_analyst_signal(symbol)
    packet["earnings"] = fetch_fmp_earnings_signal(symbol)
    packet["insider"] = fetch_fmp_insider_signal(symbol)
    hits = 0
    for key in ("analyst", "earnings", "insider"):
        value = packet.get(key)
        if isinstance(value, dict) and not value.get("error") and (
            value.get("score") not in (None, "") or value.get("date") or value.get("transactions")
        ):
            hits += 1
    packet["status"] = f"Hentet ({hits} signalfamilier)"
    packet["hits"] = hits
    return packet


def _market_match(row: dict[str, Any], market: str) -> bool:
    scope = str(market or "Alle").strip()
    if scope in ("Alle", "Global"):
        return True
    symbol = str(_first_value(row, "symbol", "ticker") or "").upper()
    exchange = str(_first_value(row, "exchange", "exchangeShortName", "stockExchange") or "").lower()
    country = str(_first_value(row, "country") or "").lower()
    if scope == "USA":
        return country in ("us", "usa", "united states") or exchange in ("nasdaq", "nyse", "amex")
    if scope == "Norge":
        return symbol.endswith(".OL") or "norway" in country or "oslo" in exchange
    if scope == "Sverige":
        return symbol.endswith(".ST") or "sweden" in country or "stockholm" in exchange
    if scope == "Finland":
        return symbol.endswith(".HE") or "finland" in country or "helsinki" in exchange
    if scope == "Danmark":
        return symbol.endswith(".CO") or "denmark" in country or "copenhagen" in exchange
    if scope == "Brasil":
        return symbol.endswith(".SA") or "brazil" in country or "sao" in exchange or "b3" in exchange
    if scope == "Norden":
        return any(_market_match(row, item) for item in ("Norge", "Sverige", "Finland", "Danmark"))
    return True


def fmp_candidate_tickers(market: str = "Alle", limit: int = 250) -> list[str]:
    if not fmp_has_key():
        return []
    data = _rows(_request_json("actively-trading-list", {}))
    out: list[str] = []
    seen: set[str] = set()
    for row in data:
        symbol = str(_first_value(row, "symbol", "ticker") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if not _market_match(row, market):
            continue
        seen.add(symbol)
        out.append(symbol)
        if len(out) >= max(1, int(limit or 250)):
            break
    return out


__all__ = [
    "fetch_fmp_analyst_signal",
    "fetch_fmp_earnings_signal",
    "fetch_fmp_insider_signal",
    "fetch_fmp_signal_packet",
    "fmp_api_status",
    "fmp_candidate_tickers",
    "fmp_has_key",
]
