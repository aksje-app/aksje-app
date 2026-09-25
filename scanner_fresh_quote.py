"""A price and its actual observation time for automatic paper buys.

Never replace an absent provider timestamp with the scanner's run time: that
would make old daily bars look like fresh market data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Callable


def _intraday_history(ticker: str) -> Any:
    import yfinance as yf

    return yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=True,
                                     prepost=False, timeout=8)


def fresh_paper_buy_quote(ticker: str, *, history_provider: Callable[[str], Any] | None = None,
                          now: datetime | None = None, max_age_minutes: float = 120) -> tuple[dict[str, Any] | None, str]:
    """Use one timed intraday query; reject missing, stale and unzoned bars."""
    try:
        frame = (history_provider or _intraday_history)(ticker)
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
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            return None, "Referansetidspunkt mangler tidssone"
        age = (reference.astimezone(timezone.utc) - observed_utc).total_seconds() / 60
        if age < -5 or age > max(1, float(max_age_minutes)):
            return None, "Intradagkurs er for gammel eller ligger i fremtiden"
        return {"price": price, "market_data_at": observed_utc.isoformat(timespec="seconds"),
                "source": "yfinance 5m Close", "age_minutes": round(age, 1)}, ""
    except Exception:
        return None, "Kunne ikke verifisere intradagkurs og tidspunkt"
