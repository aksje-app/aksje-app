"""
forecast_portfolio.py

Porteføljeprognose:
- bygger samlet bull/base/bear-scenario for flere aksjer
- bruker vekter/antall hvis tilgjengelig
- faller tilbake til lik vekting
- ingen auto-trading-kobling
"""

from __future__ import annotations
import logging

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from forecast_engine import build_forecast


@dataclass(frozen=True)
class PortfolioHoldingForecast:
    ticker: str
    weight: float
    current_value: float
    base_value: float
    bull_value: float
    bear_value: float
    base_pct: float
    bull_pct: float
    bear_pct: float
    confidence: int
    risk: str
    strength: int


@dataclass(frozen=True)
class PortfolioForecastResult:
    horizon: str
    total_current: float
    total_base: float
    total_bull: float
    total_bear: float
    base_pct: float
    bull_pct: float
    bear_pct: float
    weighted_confidence: int
    weighted_strength: int
    risk: str
    holdings: List[PortfolioHoldingForecast]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizon": self.horizon,
            "total_current": self.total_current,
            "total_base": self.total_base,
            "total_bull": self.total_bull,
            "total_bear": self.total_bear,
            "base_pct": self.base_pct,
            "bull_pct": self.bull_pct,
            "bear_pct": self.bear_pct,
            "weighted_confidence": self.weighted_confidence,
            "weighted_strength": self.weighted_strength,
            "risk": self.risk,
            "holdings": [asdict(h) for h in self.holdings],
            "warnings": self.warnings,
        }


def _clean_ticker(ticker: Any) -> Optional[str]:
    if ticker is None:
        return None
    s = str(ticker).strip().upper()
    if not s:
        return None
    if len(s) > 24:
        return None
    if not all(ch.isalnum() or ch in ".-_" for ch in s):
        return None
    return s


def normalize_holdings(raw_holdings: Any) -> List[Dict[str, Any]]:
    """Normalize portfolio holdings from common app structures.

    Supports:
    - list of dicts with ticker/symbol + value/market_value/quantity
    - dict of ticker -> value/quantity/dict
    """
    rows: List[Dict[str, Any]] = []

    def add(ticker: Any, value: Any = None, quantity: Any = None, price: Any = None) -> None:
        t = _clean_ticker(ticker)
        if not t:
            return
        row: Dict[str, Any] = {"ticker": t}
        for key, raw in [("value", value), ("quantity", quantity), ("price", price)]:
            try:
                if raw is not None:
                    row[key] = float(raw)
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
        rows.append(row)

    if isinstance(raw_holdings, list):
        for item in raw_holdings:
            if isinstance(item, dict):
                ticker = item.get("ticker") or item.get("symbol") or item.get("Ticker") or item.get("Symbol")
                value = item.get("value") or item.get("market_value") or item.get("current_value") or item.get("amount")
                quantity = item.get("quantity") or item.get("shares") or item.get("qty")
                price = item.get("price") or item.get("last_price") or item.get("current_price")
                add(ticker, value=value, quantity=quantity, price=price)
            else:
                add(item)
    elif isinstance(raw_holdings, dict):
        # If dict itself is a holding.
        if any(k in raw_holdings for k in ("ticker", "symbol", "Ticker", "Symbol")):
            add(
                raw_holdings.get("ticker") or raw_holdings.get("symbol") or raw_holdings.get("Ticker") or raw_holdings.get("Symbol"),
                value=raw_holdings.get("value") or raw_holdings.get("market_value") or raw_holdings.get("current_value"),
                quantity=raw_holdings.get("quantity") or raw_holdings.get("shares") or raw_holdings.get("qty"),
                price=raw_holdings.get("price") or raw_holdings.get("last_price") or raw_holdings.get("current_price"),
            )
        else:
            for ticker, data in raw_holdings.items():
                if isinstance(data, dict):
                    add(
                        ticker,
                        value=data.get("value") or data.get("market_value") or data.get("current_value"),
                        quantity=data.get("quantity") or data.get("shares") or data.get("qty"),
                        price=data.get("price") or data.get("last_price") or data.get("current_price"),
                    )
                else:
                    add(ticker, value=data)

    # Deduplicate, combine values when possible
    merged: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        t = row["ticker"]
        if t not in merged:
            merged[t] = dict(row)
        else:
            for key in ("value", "quantity"):
                if key in row:
                    merged[t][key] = float(merged[t].get(key, 0.0)) + float(row[key])
            if "price" in row and "price" not in merged[t]:
                merged[t]["price"] = row["price"]

    return list(merged.values())


def build_portfolio_forecast(
    holdings: Sequence[Dict[str, Any]],
    price_history_by_ticker: Dict[str, Sequence[float]],
    horizon: str = "1m",
    *,
    ai_scores: Optional[Dict[str, float]] = None,
    sentiment_scores: Optional[Dict[str, float]] = None,
    market_regime: str = "neutral",
    event_risk_by_ticker: Optional[Dict[str, bool]] = None,
) -> PortfolioForecastResult:
    """Build combined portfolio forecast.

    holdings should contain ticker and optionally value or quantity.
    price_history_by_ticker maps ticker -> historical prices.
    """
    norm = normalize_holdings(list(holdings))
    if not norm:
        raise ValueError("Ingen gyldige beholdninger for porteføljeprognose.")

    warnings: List[str] = []
    holding_results: List[PortfolioHoldingForecast] = []
    raw_values: Dict[str, float] = {}

    for h in norm:
        ticker = h["ticker"]
        prices = price_history_by_ticker.get(ticker) or price_history_by_ticker.get(ticker.upper())
        if not prices or len(prices) < 30:
            warnings.append(f"Mangler nok prisdata for {ticker}.")
            continue

        current_price = float(prices[-1])
        value = h.get("value")
        if value is None:
            qty = h.get("quantity")
            if qty is not None:
                value = float(qty) * current_price
        if value is None or float(value) <= 0:
            value = 1.0  # equal-weight fallback

        raw_values[ticker] = float(value)

    if not raw_values:
        raise ValueError("Ingen beholdninger hadde nok prisdata.")

    total_value_input = sum(raw_values.values())
    if total_value_input <= 0:
        total_value_input = float(len(raw_values))

    for ticker, input_value in raw_values.items():
        prices = price_history_by_ticker.get(ticker) or price_history_by_ticker.get(ticker.upper())
        weight = input_value / total_value_input

        result = build_forecast(
            ticker,
            prices,
            horizon,
            ai_score=(ai_scores or {}).get(ticker),
            sentiment_score=(sentiment_scores or {}).get(ticker),
            market_regime=market_regime,
            event_risk=(event_risk_by_ticker or {}).get(ticker, False),
        )
        s = result.summary

        current_value = input_value
        base_value = current_value * (1.0 + s.base_pct / 100.0)
        bull_value = current_value * (1.0 + s.bull_pct / 100.0)
        bear_value = current_value * (1.0 + s.bear_pct / 100.0)

        holding_results.append(PortfolioHoldingForecast(
            ticker=ticker,
            weight=round(weight, 4),
            current_value=round(current_value, 2),
            base_value=round(base_value, 2),
            bull_value=round(bull_value, 2),
            bear_value=round(bear_value, 2),
            base_pct=s.base_pct,
            bull_pct=s.bull_pct,
            bear_pct=s.bear_pct,
            confidence=s.confidence,
            risk=s.risk,
            strength=s.forecast_strength,
        ))

    total_current = sum(h.current_value for h in holding_results)
    total_base = sum(h.base_value for h in holding_results)
    total_bull = sum(h.bull_value for h in holding_results)
    total_bear = sum(h.bear_value for h in holding_results)

    weighted_conf = sum(h.confidence * h.weight for h in holding_results)
    weighted_strength = sum(h.strength * h.weight for h in holding_results)

    # Simple portfolio risk from worst holding + diversification
    high_risk_count = sum(1 for h in holding_results if h.risk == "Høy")
    if high_risk_count >= max(1, len(holding_results) // 2):
        risk = "Høy"
    elif high_risk_count > 0:
        risk = "Medium"
    else:
        risk = "Lav"

    if len(holding_results) < len(norm):
        warnings.append("Noen beholdninger ble utelatt på grunn av manglende prisdata.")

    return PortfolioForecastResult(
        horizon=horizon,
        total_current=round(total_current, 2),
        total_base=round(total_base, 2),
        total_bull=round(total_bull, 2),
        total_bear=round(total_bear, 2),
        base_pct=round((total_base / total_current - 1.0) * 100.0, 2),
        bull_pct=round((total_bull / total_current - 1.0) * 100.0, 2),
        bear_pct=round((total_bear / total_current - 1.0) * 100.0, 2),
        weighted_confidence=int(round(weighted_conf)),
        weighted_strength=int(round(weighted_strength)),
        risk=risk,
        holdings=holding_results,
        warnings=warnings,
    )
