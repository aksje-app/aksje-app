from __future__ import annotations

from typing import Any, Mapping

from .common import clamp_score, first_value


def _score_transactions(transactions: Any) -> float | None:
    if not isinstance(transactions, list):
        return None
    try:
        from insider import insider_score_from_transactions

        result = insider_score_from_transactions(transactions)
        if isinstance(result, dict) and result.get("score") is not None:
            return clamp_score(result.get("score"))
    except Exception:
        return None
    return None


def calculate_insider_score(data: Mapping[str, Any] | None) -> float:
    """Return 0..10 insider score using existing insider.py and optional FMP fallback."""
    row = dict(data or {})

    explicit = first_value(row, "insider_score", "long_insider_score", "insider_signal_score", "insider_quality_score")
    if explicit not in (None, ""):
        return clamp_score(explicit)

    tx_score = _score_transactions(row.get("latest_transactions") or row.get("insider_transactions") or row.get("transactions"))
    if tx_score is not None:
        return tx_score

    ticker = str(first_value(row, "ticker", "symbol") or "").strip().upper()
    if ticker:
        try:
            from insider import get_insider_signal

            result = get_insider_signal(ticker, months=6)
            if isinstance(result, dict) and result.get("score") is not None and not result.get("error"):
                return clamp_score(result.get("score"))
        except Exception:
            pass

        try:
            from fmp_signals import fetch_fmp_insider_signal

            result = fetch_fmp_insider_signal(ticker, months=6)
            if isinstance(result, dict) and result.get("score") is not None and not result.get("error"):
                return clamp_score(result.get("score"))
        except Exception:
            pass

    return 5.0


def insider_score_details(data: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(data or {})
    score = calculate_insider_score(row)
    details: dict[str, Any] = {"score": score, "source": "insider.py/Finnhub + FMP fallback", "status": "neutral"}
    ticker = str(first_value(row, "ticker", "symbol") or "").strip().upper()
    try:
        if ticker:
            from insider import get_insider_signal

            result = get_insider_signal(ticker, months=6)
            if isinstance(result, dict):
                details.update({k: result.get(k) for k in ("label", "buy_count", "sell_count", "latest_type", "latest_date", "source", "error")})
                details["status"] = result.get("label") or "ok"
    except Exception as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
    return details
