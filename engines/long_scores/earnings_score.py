from __future__ import annotations

from typing import Any, Mapping

from .common import clamp_score, first_value


def _score_surprise_pct(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        pct = float(value)
    except Exception:
        return None
    # -20% => 0, 0% => 5, +20% => 9, +30%+ => 10
    if pct >= 30:
        return 10.0
    if pct >= 20:
        return 9.0
    if pct >= 10:
        return 8.0
    if pct >= 0:
        return 5.0 + min(2.0, pct / 5.0)
    if pct <= -20:
        return 0.0
    if pct <= -10:
        return 2.0
    return max(0.0, 5.0 + pct * 0.3)


def calculate_earnings_score(data: Mapping[str, Any] | None) -> float:
    """Return 0..10 earnings score using earnings.py and FMP earnings when possible."""
    row = dict(data or {})

    explicit = first_value(row, "earnings_score", "long_earnings_score", "eps_score")
    if explicit not in (None, ""):
        return clamp_score(explicit)

    surprise = first_value(row, "epsSurprisePct", "eps_surprise_pct", "earnings_surprise_pct", "surprise_pct")
    surprise_score = _score_surprise_pct(surprise)
    if surprise_score is not None:
        return clamp_score(surprise_score)

    ticker = str(first_value(row, "ticker", "symbol") or "").strip().upper()
    if ticker:
        try:
            from fmp_signals import fetch_fmp_earnings_signal

            result = fetch_fmp_earnings_signal(ticker)
            if isinstance(result, dict) and not result.get("error"):
                score = _score_surprise_pct(result.get("epsSurprisePct"))
                if score is not None:
                    return clamp_score(score)
                if result.get("epsEstimate") not in (None, ""):
                    return 5.8
        except Exception:
            pass

        try:
            from earnings import get_earnings

            result = get_earnings(ticker)
            if isinstance(result, dict) and not result.get("error"):
                if result.get("epsEstimate") not in (None, "") or result.get("revenueEstimate") not in (None, ""):
                    return 5.6
                if result.get("date"):
                    return 5.2
        except Exception:
            pass

    return 5.0


def earnings_score_details(data: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(data or {})
    score = calculate_earnings_score(row)
    details: dict[str, Any] = {"score": score, "source": "earnings.py/Finnhub + FMP fallback", "status": "neutral"}
    ticker = str(first_value(row, "ticker", "symbol") or "").strip().upper()
    try:
        if ticker:
            from fmp_signals import fetch_fmp_earnings_signal

            result = fetch_fmp_earnings_signal(ticker)
            if isinstance(result, dict):
                details.update(result)
                details["score"] = score
    except Exception as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
    return details
