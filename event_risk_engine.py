"""
event_risk_engine.py

v18.5.15 Real event-risk detection for forecast confidence.

Signals are only marked active when there is concrete data available:
- Earnings calendar via earnings.get_earnings / FINNHUB_API_KEY
- Optional macro calendar from MACRO_EVENT_CALENDAR_JSON env var
- Realized volatility from the supplied price series
- News-risk keywords via news.get_news / NEWSAPI_KEY

No auto-trading connection.
"""

from __future__ import annotations
import logging

import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence


HIGH_RISK_NEWS_WORDS = {
    "lawsuit", "investigation", "sec", "probe", "fraud", "recall", "downgrade", "guidance",
    "warning", "miss", "layoffs", "strike", "bankruptcy", "default", "cuts forecast", "slump",
}


def _pct_returns(prices: Sequence[float]) -> List[float]:
    clean: List[float] = []
    for p in prices:
        try:
            f = float(p)
            if f > 0:
                clean.append(f)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    returns = []
    for prev, cur in zip(clean, clean[1:]):
        if prev > 0:
            returns.append(cur / prev - 1.0)
    return returns


def _realized_volatility(prices: Sequence[float], window: int = 30) -> Optional[float]:
    returns = _pct_returns(prices)[-window:]
    if len(returns) < 8:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def _max_abs_move(prices: Sequence[float], window: int = 5) -> Optional[float]:
    returns = _pct_returns(prices)[-window:]
    if not returns:
        return None
    return max(abs(r) for r in returns)


def _macro_events_from_env(days_ahead: int = 10) -> List[Dict[str, Any]]:
    raw = os.getenv("MACRO_EVENT_CALENDAR_JSON", "").strip()
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []

    today = date.today()
    end = today + timedelta(days=days_ahead)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_date = row.get("date") or row.get("event_date")
        try:
            event_date = datetime.fromisoformat(str(raw_date)).date()
        except Exception:
            continue
        if today <= event_date <= end:
            impact = str(row.get("impact") or "high").lower()
            if impact in {"high", "red", "important", "medium"}:
                out.append({**row, "date": event_date.isoformat(), "days_until": (event_date - today).days})
    return out


def _earnings_signal(ticker: str, days_ahead: int = 14) -> Dict[str, Any]:
    try:
        from earnings import get_earnings

        data = get_earnings(ticker) or {}
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    if data.get("error"):
        return {"available": False, "error": data.get("error")}

    days_until = data.get("days_until")
    try:
        days_int = int(days_until) if days_until is not None else None
    except Exception:
        days_int = None

    if days_int is not None and 0 <= days_int <= days_ahead:
        return {"available": True, "active": True, **data}
    return {"available": True, "active": False, **data}


def _news_signal(ticker: str, limit: int = 8) -> Dict[str, Any]:
    try:
        from news import get_news

        articles, error = get_news(ticker, limit=limit, source="event_risk")
    except Exception as exc:
        return {"available": False, "error": str(exc), "keyword_hits": 0}

    if error:
        return {"available": False, "error": error, "keyword_hits": 0}

    hits = 0
    hit_titles: List[str] = []
    for article in articles or []:
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        matched = [word for word in HIGH_RISK_NEWS_WORDS if word in text]
        if matched:
            hits += len(matched)
            title = str(article.get("title") or "").strip()
            if title:
                hit_titles.append(title[:140])
    return {"available": True, "keyword_hits": hits, "hit_titles": hit_titles[:3], "article_count": len(articles or [])}


def detect_event_risk(
    ticker: str,
    prices: Sequence[float],
    *,
    horizon: str = "1m",
    include_news: bool = True,
) -> Dict[str, Any]:
    """Return event-risk state, alerts and confidence adjustment."""
    ticker = str(ticker or "").upper().strip()
    alerts: List[Dict[str, Any]] = []
    diagnostics: Dict[str, Any] = {"ticker": ticker, "horizon": horizon}

    earnings = _earnings_signal(ticker)
    diagnostics["earnings"] = earnings
    if earnings.get("active"):
        days = earnings.get("days_until")
        level = "red" if days is not None and int(days) <= 3 else "yellow"
        alerts.append({
            "ticker": ticker,
            "horizon": horizon,
            "level": level,
            "category": "earnings_event",
            "message": f"Earnings nær: {ticker} har rapportdato {earnings.get('date')} ({days} dager).",
        })

    macro_events = _macro_events_from_env()
    diagnostics["macro_events"] = macro_events
    for event in macro_events[:5]:
        level = "red" if str(event.get("impact", "")).lower() in {"high", "red", "important"} else "yellow"
        alerts.append({
            "ticker": ticker,
            "horizon": horizon,
            "level": level,
            "category": "macro_event",
            "message": f"Makrohendelse nær: {event.get('title') or event.get('name') or 'viktig makro'} {event.get('date')}.",
        })

    vol = _realized_volatility(prices)
    move = _max_abs_move(prices)
    diagnostics["realized_volatility_30d"] = None if vol is None else round(vol, 4)
    diagnostics["max_abs_move_5d"] = None if move is None else round(move, 4)
    if vol is not None and vol >= 0.70:
        alerts.append({
            "ticker": ticker,
            "horizon": horizon,
            "level": "red",
            "category": "high_volatility",
            "message": f"Svært høy realisert volatilitet siste periode ({vol:.0%}). Confidence justeres ned.",
        })
    elif vol is not None and vol >= 0.45:
        alerts.append({
            "ticker": ticker,
            "horizon": horizon,
            "level": "yellow",
            "category": "elevated_volatility",
            "message": f"Forhøyet realisert volatilitet ({vol:.0%}). Prognosen bør tolkes mer forsiktig.",
        })
    if move is not None and move >= 0.08:
        alerts.append({
            "ticker": ticker,
            "horizon": horizon,
            "level": "yellow",
            "category": "large_recent_move",
            "message": f"Stor nylig kursbevegelse ({move:.1%}) kan gi hendelsesrisiko/støy.",
        })

    if include_news:
        news = _news_signal(ticker)
        diagnostics["news"] = news
        hits = int(news.get("keyword_hits") or 0)
        if hits >= 3:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "red",
                "category": "news_risk",
                "message": f"Store nyhetsrisiko-signaler funnet ({hits} nøkkelord) for {ticker}.",
            })
        elif hits > 0:
            alerts.append({
                "ticker": ticker,
                "horizon": horizon,
                "level": "yellow",
                "category": "news_risk",
                "message": f"Mulig nyhetsrisiko funnet ({hits} nøkkelord) for {ticker}.",
            })

    red = sum(1 for a in alerts if a.get("level") == "red")
    yellow = sum(1 for a in alerts if a.get("level") == "yellow")
    adjustment = -min(20, red * 8 + yellow * 4)

    return {
        "ticker": ticker,
        "horizon": horizon,
        "is_event_risk": bool(red or yellow),
        "confidence_adjustment": adjustment,
        "alerts": alerts,
        "diagnostics": diagnostics,
    }


def summarize_event_risk(event_info: Dict[str, Any]) -> str:
    """Return a compact human-readable event-risk summary for UI/storage."""
    alerts = list((event_info or {}).get("alerts", []) or [])
    if not alerts:
        return "Ingen konkret hendelsesrisiko funnet med tilgjengelige datakilder."
    red = sum(1 for a in alerts if a.get("level") == "red")
    yellow = sum(1 for a in alerts if a.get("level") == "yellow")
    first = alerts[0].get("message") or alerts[0].get("category") or "Hendelsesrisiko nær"
    return f"Hendelsesrisiko nær: {red} røde / {yellow} gule signaler. {first}"


def event_risk_confidence_breakdown(
    *,
    base_confidence: int,
    event_info: Dict[str, Any],
    learning_adjustment: int = 0,
) -> Dict[str, Any]:
    """Explain how event-risk and learning adjust confidence.

    This helper is side-effect free so it can be used by UI and tests. The
    forecast engine still performs the final clamp when building the forecast.
    """
    base = int(base_confidence or 0)
    event_adj = int((event_info or {}).get("confidence_adjustment") or 0)
    learn_adj = int(learning_adjustment or 0)
    adjusted = max(5, min(95, base + event_adj + learn_adj))
    return {
        "base_confidence": base,
        "event_adjustment": event_adj,
        "learning_adjustment": learn_adj,
        "total_adjustment": adjusted - base,
        "adjusted_confidence": adjusted,
        "event_risk": bool((event_info or {}).get("is_event_risk")),
        "event_summary": summarize_event_risk(event_info or {}),
    }
