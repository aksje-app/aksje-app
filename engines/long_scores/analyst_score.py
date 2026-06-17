from __future__ import annotations

from typing import Any, Mapping

from .common import clamp_score, first_value


def calculate_analyst_score(data: Mapping[str, Any] | None) -> float:
    """Return 0..10 analyst score using analyst.py and FMP analyst/estimates fallback."""
    row = dict(data or {})

    explicit = first_value(row, "analyst_score", "long_analyst_score", "recommendation_score", "analyst_signal_score")
    if explicit not in (None, ""):
        return clamp_score(explicit)

    ticker = str(first_value(row, "ticker", "symbol") or "").strip().upper()
    if ticker:
        try:
            from fmp_signals import fetch_fmp_analyst_signal

            result = fetch_fmp_analyst_signal(ticker)
            if isinstance(result, dict) and result.get("score") is not None and not result.get("error"):
                return clamp_score(result.get("score"))
        except Exception:
            pass

        try:
            from analyst import get_analyst_trend

            result = get_analyst_trend(ticker)
            if isinstance(result, dict) and result.get("score") is not None and not result.get("error"):
                return clamp_score(result.get("score"))
        except Exception:
            pass

    return 5.0


def analyst_score_details(data: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(data or {})
    score = calculate_analyst_score(row)
    details: dict[str, Any] = {"score": score, "source": "analyst.py/Finnhub + FMP fallback", "status": "neutral"}
    ticker = str(first_value(row, "ticker", "symbol") or "").strip().upper()
    try:
        if ticker:
            from analyst import get_analyst_trend

            result = get_analyst_trend(ticker)
            if isinstance(result, dict):
                details.update(result)
                details["score"] = score
    except Exception as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
    return details
