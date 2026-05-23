from __future__ import annotations

from typing import Any, Mapping


MARKET_CURRENCY_BY_SUFFIX = {
    ".OL": "NOK",
    ".ST": "SEK",
    ".HE": "EUR",
    ".CO": "DKK",
    ".SA": "BRL",
}

MARKET_CURRENCY_BY_MARKET = {
    "Norge": "NOK",
    "Sverige": "SEK",
    "Finland": "EUR",
    "Danmark": "DKK",
    "Brasil": "BRL",
    "USA": "USD",
    "USA/annet": "USD",
}

# Fallback estimates only. Live providers can override with market_cap_fx_to_nok.
FX_TO_NOK_ESTIMATE = {
    "NOK": 1.0,
    "USD": 10.5,
    "EUR": 11.7,
    "SEK": 1.0,
    "DKK": 1.57,
    "BRL": 1.9,
}


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def format_thousands_dot(value: Any, decimals: int = 0) -> str:
    number = _float(value, None)
    if number is None:
        return ""
    decimals = max(0, int(decimals or 0))
    text = f"{number:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if decimals == 0:
        return text.split(",")[0]
    return text


def infer_market_cap_currency(ticker: Any, row: Mapping[str, Any] | None = None) -> str:
    row = row or {}
    for key in ("market_cap_currency", "currency", "financial_currency", "financialCurrency"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            return value
    market = str(row.get("market") or "").strip()
    if market in MARKET_CURRENCY_BY_MARKET:
        return MARKET_CURRENCY_BY_MARKET[market]
    ticker_text = str(ticker or row.get("ticker") or "").strip().upper()
    for suffix, currency in MARKET_CURRENCY_BY_SUFFIX.items():
        if ticker_text.endswith(suffix):
            return currency
    return "USD"


def market_cap_nok_estimate(value: Any, currency: str, row: Mapping[str, Any] | None = None) -> float | None:
    amount = _float(value, None)
    if amount is None or amount <= 0:
        return None
    row = row or {}
    explicit = _float(row.get("market_cap_nok") or row.get("market_cap_nok_estimate"), None)
    if explicit is not None and explicit > 0:
        return explicit
    fx = _float(row.get("market_cap_fx_to_nok") or row.get("fx_to_nok"), None)
    if fx is None or fx <= 0:
        fx = FX_TO_NOK_ESTIMATE.get(str(currency or "").upper())
    if fx is None or fx <= 0:
        return None
    return amount * fx


def market_cap_display(value: Any, currency: str | None = None) -> str:
    amount = format_thousands_dot(value, 0)
    if not amount:
        return ""
    suffix = str(currency or "").strip().upper()
    return f"{amount} {suffix}".strip()


def market_cap_fields(ticker: Any, row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = row or {}
    value = _float(row.get("market_cap"), None)
    currency = infer_market_cap_currency(ticker, row)
    nok_estimate = market_cap_nok_estimate(value, currency, row)
    return {
        "market_cap_currency": currency,
        "market_cap_nok_estimate": None if nok_estimate is None else round(float(nok_estimate), 0),
        "market_cap_display": market_cap_display(value, currency),
    }
