"""A price and its actual observation time for automatic paper buys.

Never replace an absent provider timestamp with the scanner's run time: that
would make old daily bars look like fresh market data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Callable


def _intraday_history(ticker: str, interval: str = "5m") -> Any:
    import yfinance as yf

    return yf.Ticker(ticker).history(period="1d", interval=interval, auto_adjust=False,
                                     prepost=False, timeout=8)


def fresh_paper_buy_quote(ticker: str, *, history_provider: Callable[[str], Any] | None = None,
                          now: datetime | None = None, max_age_minutes: float = 15) -> tuple[dict[str, Any] | None, str]:
    """Validate real timestamped bars; retry finer granularity if a 5m bar is stale.

    The retry is a second provider query, never a revised timestamp or a
    synthetic quote. The 15-minute execution limit remains unchanged.
    """
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        return None, "Referansetidspunkt mangler tidssone"

    def validate_frame(frame, interval):
        if frame is None or frame.empty or "Close" not in frame:
            return None, "Ingen tidsstemplet intradagkurs tilgjengelig"
        closes = frame["Close"].dropna()
        if closes.empty:
            return None, "Ingen intradagkurs tilgjengelig"
        observed = closes.index[-1]
        if not isinstance(observed, datetime):
            observed = observed.to_pydatetime()
        if observed.tzinfo is None or observed.utcoffset() is None:
            return None, "Kurstidspunkt mangler tidssone"
        price = float(closes.iloc[-1])
        if not isfinite(price) or price <= 0:
            return None, "Ugyldig intradagkurs"
        observed_utc = observed.astimezone(timezone.utc)
        age = (reference.astimezone(timezone.utc) - observed_utc).total_seconds() / 60
        if age < -5 or age > max(1, float(max_age_minutes)):
            return None, "Intradagkurs er for gammel eller ligger i fremtiden"
        return {"price": price, "market_data_at": observed_utc.isoformat(timespec="seconds"),
                "source": "yfinance " + interval + " Close", "adjustment": "raw",
                "age_minutes": round(age, 1)}, ""

    attempts = (("5m", lambda: history_provider(ticker)),) if history_provider is not None else (
        ("5m", lambda: _intraday_history(ticker, "5m")),
        ("1m", lambda: _intraday_history(ticker, "1m")),
    )
    error = "Ingen tidsstemplet intradagkurs tilgjengelig"
    for interval, fetch in attempts:
        try:
            quote, error = validate_frame(fetch(), interval)
        except Exception:
            error = "Kunne ikke verifisere intradagkurs og tidspunkt"
            continue
        if quote is not None:
            return quote, ""
    return None, error

def validate_execution_quote(price: Any, context: dict, *, now: datetime | None = None,
                             not_before: Any = None) -> tuple[bool, str]:
    """Validate the supplied raw quote before any automatic portfolio mutation."""
    try:
        quote = context.get("execution_quote") or {}
        value = float(price)
        if not isfinite(value) or value <= 0 or abs(float(quote["price"]) - value) > 1e-8:
            return False, "Kurs og utførelsesbevis stemmer ikke overens"
        if quote.get("source") not in ("yfinance 5m Close", "yfinance 1m Close") or quote.get("adjustment") != "raw":
            return False, "Mangler sammenlignbar ujustert intradagkurs"
        stamp = datetime.fromisoformat(str(quote["market_data_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False, "Kurstidspunkt mangler tidssone"
        reference = now or datetime.now(timezone.utc)
        age = (reference - stamp).total_seconds() / 60
        if age < -1 or age > 15:
            return False, "Utførelseskurs er gammel eller ligger i fremtiden"
        if context.get("market_data_at") != quote["market_data_at"]:
            return False, "Markedsdatatidspunkt stemmer ikke med kursbevis"
        if not_before:
            previous = datetime.fromisoformat(str(not_before).replace("Z", "+00:00"))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)  # legacy server UTC
            if stamp < previous:
                return False, "Utførelseskurs er eldre enn siste posisjonskurs"
        return True, ""
    except (TypeError, ValueError, KeyError, OverflowError):
        return False, "Ugyldig eller manglende utførelseskursbevis"
