import logging
from datetime import datetime
from typing import Any, Mapping
from signal_engine import score_signal
from notifier import notify_trade
from trading_settings import load_rules
from ui_trust import explain_blocked_action
try:
    from settings_store import load_settings
except Exception:
    load_settings = None

from paper_store import load_portfolio, save_portfolio, add_trade
from paper_trading_valuation import normalize_paper_position, paper_reason_label

try:
    from state_audit import build_paper_state_snapshot, validate_buy_order, audit_state_transition
except Exception:  # fail-safe: trading must not crash if audit helper is unavailable
    def build_paper_state_snapshot(portfolio=None, latest_prices=None, rules=None):
        portfolio = portfolio or {}
        return {"cash": float(portfolio.get("cash", 0) or 0), "open_positions": len(portfolio.get("positions", {}) or {})}
    def validate_buy_order(portfolio, **kwargs):
        return True, "OK"
    def audit_state_transition(event, before, after=None, detail=None, level="INFO"):
        return {}

POSITION_SIZE_PCT = 10.0
MAX_OPEN_POSITIONS = 5
STOP_LOSS_PCT = 7.0
TAKE_PROFIT_PCT = 12.0
TRAILING_STOP_PCT = 8.0
MIN_BUY_CONFIDENCE = 60


def build_trading_decision(item, technical_context=None):
    """
    Smart Core v2 wrapper.
    Beholder app13-kompatibelt output.
    """
    return score_signal(item, technical_context or {})




def _settings_bool(name, default=False):
    try:
        if load_settings is None:
            return bool(default)
        settings = load_settings() or {}
        return bool(settings.get(name, default))
    except Exception:
        return bool(default)


def _position_market_value(portfolio):
    """Current market value of open positions using last_price/entry fallback."""
    total = 0.0
    for _ticker, pos in (portfolio or {}).get("positions", {}).items():
        try:
            normalized = normalize_paper_position(_ticker, pos)
            shares = float(normalized.get("shares", normalized.get("units", 0)) or 0)
            price = float(normalized.get("last_price", normalized.get("entry_price", 0)) or 0)
            total += shares * price
        except Exception:
            continue
    return round(total, 2)


def paper_liquidity_snapshot(portfolio=None, latest_prices=None):
    """Single source of truth for paper cash, exposure and buying power.

    Cash/buying_power is the only amount available for new purchases.
    Portfolio value is cash + open position market value. Unrealized P/L is
    informational and does not increase cash before a SELL.
    """
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    positions_value = 0.0
    cost_basis = 0.0
    for ticker, pos in (portfolio or {}).get("positions", {}).items():
        try:
            normalized = normalize_paper_position(ticker, pos, latest_price=latest_prices.get(ticker))
            shares = float(normalized.get("shares", normalized.get("units", 0)) or 0)
            entry = float(normalized.get("entry_price", normalized.get("avg_price", 0)) or 0)
            price = float(normalized.get("last_price", entry) or 0)
            positions_value += shares * price
            cost_basis += shares * entry
        except Exception:
            continue
    cash = float((portfolio or {}).get("cash", 0) or 0)
    return {
        "cash": round(cash, 2),
        "buying_power": round(max(0.0, cash), 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(cash + positions_value, 2),
        "unrealized_pnl": round(positions_value - cost_basis, 2),
        "open_positions": len((portfolio or {}).get("positions", {}) or {}),
    }


def adjusted_score(item, decision):
    base = float(item.get("score", 0) or 0)
    if decision.get("decision") == "BUY":
        return round(min(10, base + 0.5), 2)
    if "SELL" in decision.get("decision", ""):
        return round(max(0, base - 0.8), 2)
    return round(base, 2)


def portfolio_value(portfolio=None, latest_prices=None):
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    total = float(portfolio.get("cash", 0))
    for ticker, pos in portfolio.get("positions", {}).items():
        normalized = normalize_paper_position(ticker, pos, latest_price=latest_prices.get(ticker))
        total += float(normalized.get("shares", 0)) * float(normalized.get("last_price", 0) or 0)
    return round(total, 2)


def calc_levels(entry_price, highest_price=None):
    """
    Bruker lagrede trading-regler, slik at stop-loss/take-profit/trailing
    er likt i sidebar, paper trading og auto trading.
    """
    rules = load_rules()
    entry_price = float(entry_price)
    highest_price = float(highest_price or entry_price)

    stop_loss_pct = float(rules.get("stop_loss_pct", STOP_LOSS_PCT))
    take_profit_pct = float(rules.get("take_profit_pct", TAKE_PROFIT_PCT))
    trailing_stop_pct = float(rules.get("trailing_stop_pct", TRAILING_STOP_PCT))

    stop_loss = entry_price * (1 - stop_loss_pct / 100)
    take_profit = entry_price * (1 + take_profit_pct / 100)
    trailing_stop = highest_price * (1 - trailing_stop_pct / 100)

    return round(stop_loss, 2), round(take_profit, 2), round(trailing_stop, 2)







def trades_today_count(portfolio=None, trade_type=None):
    """
    Teller handler i dag basert på paper portfolio trade-logg.
    Brukes for å hindre at auto-kjøp spammer posisjoner.
    """
    portfolio = portfolio or load_portfolio()
    today = datetime.now().date().isoformat()
    count = 0

    for trade in portfolio.get("trades", []):
        t = str(trade.get("time", ""))
        if not t.startswith(today):
            continue
        if trade_type and str(trade.get("type", "")).upper() != str(trade_type).upper():
            continue
        count += 1

    return count


def notify_executed_trade(trade_type, ticker, price, shares=None, amount=None, confidence=None, reason=""):
    """
    Sentral varsling for ALLE faktiske paper trades:
    - Cron BUY/SELL
    - UI paper-kjøp/paper-selg
    - Stop-loss
    - Take-profit
    - Trailing stop

    Feil i Pushover skal aldri stoppe selve handelen.
    """
    try:
        parts = [
            f"{trade_type.upper()}: {ticker}",
            f"Pris: {float(price):.2f}",
        ]

        if shares is not None:
            parts.append(f"Antall: {float(shares):.4f}")
        if amount is not None:
            parts.append(f"Beløp: {float(amount):.2f}")
        if confidence is not None:
            parts.append(f"Confidence: {int(confidence)}%")
        if reason:
            parts.append(f"Årsak: {reason}")

        return notify_trade(
            trade_type,
            ticker,
            price,
            amount=amount,
            shares=shares,
            confidence=confidence,
            reason=reason,
        )
    except Exception as e:
        print(f"notify_executed_trade failed: {e}")
        return False


TRADE_CONTEXT_KEYS = (
    "country",
    "market",
    "sector",
    "industry",
    "rule_used",
    "rule_limit",
    "measured_value",
    "trade_explanation",
)


def resolve_trade_security_context(ticker: Any, item: Mapping[str, Any] | None = None) -> dict:
    """Local ticker metadata used in paper positions and trade logs."""
    row = dict(item or {}) if isinstance(item, Mapping) else {}
    symbol = str(row.get("ticker") or row.get("symbol") or ticker or "").strip().upper()
    meta = dict(row)
    listing = {}
    try:
        from security_metadata import infer_security_listing, resolve_security_metadata

        meta = resolve_security_metadata(symbol, row)
        listing = infer_security_listing(symbol, meta)
    except Exception:
        listing = {}

    sector = str(row.get("sector") or row.get("Sector") or meta.get("sector") or "").strip()
    industry = str(row.get("industry") or row.get("Industry") or row.get("bransje") or sector or "").strip()
    return {
        "country": str(row.get("country") or row.get("land") or listing.get("country") or "").strip(),
        "market": str(row.get("market") or listing.get("market") or "").strip(),
        "sector": sector,
        "industry": industry,
        "asset_type": str(row.get("asset_type") or row.get("type") or "Aksje").strip() or "Aksje",
    }


def _merge_trade_context(ticker: Any, trade_context: Mapping[str, Any] | None = None, *, source: Mapping[str, Any] | None = None) -> dict:
    source_row = dict(source or {}) if isinstance(source, Mapping) else {}
    ctx = resolve_trade_security_context(ticker, source_row)
    if isinstance(trade_context, Mapping):
        for key, value in trade_context.items():
            if value not in (None, ""):
                ctx[str(key)] = value
    return {key: ctx.get(key, "") for key in set(TRADE_CONTEXT_KEYS + ("asset_type",))}


def _default_trade_explanation(trade_type: str, reason: str, ctx: Mapping[str, Any] | None = None) -> str:
    ctx = ctx or {}
    existing = str(ctx.get("trade_explanation") or "").strip()
    if existing:
        return existing
    rule = str(ctx.get("rule_used") or "").strip()
    limit = str(ctx.get("rule_limit") or "").strip()
    measured = str(ctx.get("measured_value") or "").strip()
    if str(trade_type or "").upper() == "SELL":
        if rule and limit and measured:
            return f"Solgt fordi {rule} ble utlost: malt {measured}, grense {limit}."
        if rule:
            return f"Solgt fordi {rule} ble utlost."
        if reason:
            return f"Solgt fordi {reason}."
    if str(trade_type or "").upper() == "BUY":
        if rule and measured:
            return f"Kjopt fordi {rule}: {measured}."
        if reason:
            return f"Kjopt fordi {reason}."
    return ""


def _format_pct(value: float) -> str:
    return f"{float(value):.2f}%"


def paper_buy(ticker, price, confidence=0, reason="BUY signal", trade_context=None):
    rules = load_rules()
    max_open_positions = int(rules.get("max_open_positions", MAX_OPEN_POSITIONS))
    max_trades_per_day = int(rules.get("max_trades_per_day", 3))
    min_buy_confidence = int(rules.get("min_buy_confidence", MIN_BUY_CONFIDENCE))
    position_size_pct = float(rules.get("position_size_pct", POSITION_SIZE_PCT))
    portfolio = load_portfolio()
    before = build_paper_state_snapshot(portfolio, rules=rules)
    ticker = str(ticker).upper()
    trade_ctx = _merge_trade_context(ticker, trade_context)
    if not trade_ctx.get("rule_used"):
        trade_ctx["rule_used"] = "BUY signal"
    if not trade_ctx.get("measured_value"):
        trade_ctx["measured_value"] = f"confidence {int(confidence or 0)}"
    trade_ctx["trade_explanation"] = _default_trade_explanation("BUY", reason, trade_ctx)
    reason = paper_reason_label(reason, "BUY") or "PAPER-KJØP"
    try:
        price = float(price)
    except Exception:
        audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "reason": "invalid_price"}, level="WARNING")
        return False, "Ugyldig prisdata - kjøp stoppet"
    total_value = portfolio_value(portfolio)
    available_cash = float(portfolio.get("cash", 0) or 0)
    amount = min(available_cash, total_value * position_size_pct / 100)
    ok, msg = validate_buy_order(
        portfolio,
        ticker=ticker,
        price=price,
        amount=amount,
        confidence=int(confidence or 0),
        min_confidence=min_buy_confidence,
        allow_existing=False,
        max_open_positions=max_open_positions,
        max_buys_per_day=max_trades_per_day,
        safety_mode=_settings_bool("auto_buy_safety_mode", True),
    )
    if not ok:
        audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "amount": round(float(amount or 0), 2), "reason": msg}, level="WARNING")
        return False, explain_blocked_action([msg], action="Kjøp")
    shares = amount / price
    sl, tp, tr = calc_levels(price, price)
    portfolio["cash"] = round(float(portfolio.get("cash", 0)) - amount, 2)
    portfolio.setdefault("positions", {})[ticker] = {
        "ticker": ticker, "shares": shares, "entry_price": price, "avg_price": price,
        "last_price": price, "highest_price": price, "stop_loss": sl,
        "take_profit": tp, "trailing_stop": tr, "confidence": int(confidence or 0), "reason": reason,
        "opened_at": datetime.now().isoformat(timespec="seconds"), "asset_type": "Aksje", "units_label": "shares",
        "country": trade_ctx.get("country", ""), "market": trade_ctx.get("market", ""),
        "sector": trade_ctx.get("sector", ""), "industry": trade_ctx.get("industry", ""),
    }
    add_trade(portfolio, {
        "type":"BUY", "ticker":ticker, "price":round(price,2), "shares":round(shares,6),
        "amount":round(amount,2), "confidence":int(confidence or 0), "reason":reason,
        "order_kind":"paper", "asset_type": "Aksje",
        **{key: trade_ctx.get(key, "") for key in TRADE_CONTEXT_KEYS},
    })
    after = build_paper_state_snapshot(portfolio, rules=rules)
    audit_state_transition("paper_buy_executed", before, after, {"ticker": ticker, "price": round(price, 4), "amount": round(amount, 2), "confidence": int(confidence or 0), "reason": reason})
    notify_executed_trade("BUY", ticker, price, shares=shares, amount=amount, confidence=confidence, reason=reason)
    return True, f"PAPER-KJØP {ticker} @ {price:.2f}"


def paper_sell(ticker, price, reason="SELL signal", trade_context=None):
    portfolio = load_portfolio()
    before = build_paper_state_snapshot(portfolio)
    ticker = str(ticker).upper()
    try:
        price = float(price)
    except Exception:
        audit_state_transition("paper_sell_blocked", before, detail={"ticker": ticker, "reason": "invalid_price"}, level="WARNING")
        return False, "Ugyldig prisdata - salg stoppet"
    pos = portfolio.get("positions", {}).get(ticker)
    if not pos:
        audit_state_transition("paper_sell_blocked", before, detail={"ticker": ticker, "reason": "missing_position"}, level="WARNING")
        return False, f"Ingen posisjon i {ticker}"
    reason = paper_reason_label(reason, "SELL") or "PAPER-SALG"
    trade_ctx = _merge_trade_context(ticker, trade_context, source=pos)
    normalized_pos = normalize_paper_position(ticker, pos, latest_price=price)
    shares = float(normalized_pos.get("shares", 0))
    entry = float(normalized_pos.get("entry_price", normalized_pos.get("avg_price", price)))
    amount = shares * price
    pnl_pct = ((price-entry)/entry*100) if entry else 0
    trade_ctx["trade_explanation"] = _default_trade_explanation("SELL", reason, trade_ctx)
    portfolio["cash"] = round(float(portfolio.get("cash", 0)) + amount, 2)
    del portfolio["positions"][ticker]
    add_trade(portfolio, {
        "type":"SELL", "ticker":ticker, "price":round(price,2), "shares":round(shares,6),
        "amount":round(amount,2), "confidence":int(pos.get("confidence",0) or 0),
        "pnl_pct":round(pnl_pct,2), "reason":reason, "order_kind":"paper",
        "asset_type": pos.get("asset_type", "Aksje"),
        **{key: trade_ctx.get(key, "") for key in TRADE_CONTEXT_KEYS},
    })
    after = build_paper_state_snapshot(portfolio)
    audit_state_transition("paper_sell_executed", before, after, {"ticker": ticker, "price": round(price, 4), "amount": round(amount, 2), "pnl_pct": round(pnl_pct, 2), "reason": reason})
    notify_executed_trade("SELL", ticker, price, shares=shares, amount=amount, confidence=pos.get("confidence"), reason=reason)
    return True, f"PAPER-SALG {ticker} @ {price:.2f} ({pnl_pct:.2f}%)"


def auto_trade(ticker, price, signal, confidence=0, rsi=None, prev_rsi=None):
    portfolio = load_portfolio()
    rules = load_rules()
    ticker = str(ticker).upper()
    price = float(price)
    sig = str(signal or "").upper()
    pos = portfolio.get("positions", {}).get(ticker)
    if pos:
        entry = float(pos.get("entry_price", pos.get("avg_price", price)))
        high = max(float(pos.get("highest_price", entry) or entry), price)
        sl, tp, tr = calc_levels(entry, high)
        pos.update({"last_price":price, "highest_price":high, "stop_loss":sl, "take_profit":tp, "trailing_stop":tr})
        portfolio["positions"][ticker] = pos
        save_portfolio(portfolio)
        pnl_pct = ((price-entry)/entry*100) if entry else 0
        stop_loss_pct = float(rules.get("stop_loss_pct", STOP_LOSS_PCT))
        take_profit_pct = float(rules.get("take_profit_pct", TAKE_PROFIT_PCT))
        trailing_stop_pct = float(rules.get("trailing_stop_pct", TRAILING_STOP_PCT))
        rsi_exit_level = float(rules.get("rsi_exit_level", 75))
        rsi_must_fall = bool(rules.get("rsi_must_fall", True))

        if price <= sl:
            return paper_sell(ticker, price, f"Stop loss {pnl_pct:.2f}%", {
                "rule_used": "Stop-loss",
                "rule_limit": _format_pct(-stop_loss_pct),
                "measured_value": _format_pct(pnl_pct),
                "trade_explanation": f"Solgt fordi tapet var {pnl_pct:.2f}%, som er lik eller under stop-loss {stop_loss_pct:.2f}%.",
            })
        if price >= tp:
            return paper_sell(ticker, price, f"Take profit {pnl_pct:.2f}%", {
                "rule_used": "Take-profit",
                "rule_limit": _format_pct(take_profit_pct),
                "measured_value": _format_pct(pnl_pct),
                "trade_explanation": f"Solgt fordi gevinsten var {pnl_pct:.2f}%, som er lik eller over take-profit {take_profit_pct:.2f}%.",
            })
        if high > entry and price <= tr:
            drop_from_high = ((price - high) / high * 100) if high else 0
            return paper_sell(ticker, price, f"Trailing stop {pnl_pct:.2f}%", {
                "rule_used": "Trailing stop",
                "rule_limit": _format_pct(-trailing_stop_pct),
                "measured_value": _format_pct(drop_from_high),
                "trade_explanation": f"Solgt fordi kursen falt {abs(drop_from_high):.2f}% fra topp etter at posisjonen hadde vaert i pluss.",
            })
        try:
            current_rsi = float(rsi) if rsi is not None else None
            previous_rsi = float(prev_rsi) if prev_rsi is not None else None
            rsi_is_falling = previous_rsi is not None and current_rsi is not None and current_rsi < previous_rsi
            if current_rsi is not None and current_rsi >= rsi_exit_level and (not rsi_must_fall or rsi_is_falling):
                return paper_sell(ticker, price, f"RSI sell {current_rsi:.1f}", {
                    "rule_used": "RSI exit",
                    "rule_limit": f"{rsi_exit_level:.1f}",
                    "measured_value": f"{current_rsi:.1f}",
                    "trade_explanation": (
                        f"Solgt fordi RSI var {current_rsi:.1f} mot grense {rsi_exit_level:.1f}"
                        + (" og RSI falt fra forrige topp." if rsi_must_fall else ".")
                    ),
                })
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
        if "SELL" in sig or "AVOID" in sig:
            return paper_sell(ticker, price, "SELL signal", {
                "rule_used": "SELL/AVOID signal",
                "rule_limit": "signal",
                "measured_value": sig,
                "trade_explanation": f"Solgt fordi signalmotoren ga {sig or 'SELL/AVOID'} etter risikosjekk.",
            })
        return False, f"HOLD {ticker}"
    if "BUY" in sig:
        return paper_buy(ticker, price, confidence, "BUY signal", {
            "rule_used": "BUY signal",
            "measured_value": f"confidence {int(confidence or 0)}",
        })
    return False, "Ingen trade"




# -------------------------------------------------------------------
# v18.5.45: Paper trading support for funds and ETFs
# -------------------------------------------------------------------
FUND_ASSET_TYPES = {"ETF", "Fond", "Indeksfond", "Aktivt fond"}


def _normalize_paper_symbol(symbol):
    return str(symbol or "").strip().upper()


def _normalize_asset_type(asset_type):
    text = str(asset_type or "").strip()
    if text.lower() in {"etf", "exchange traded fund"}:
        return "ETF"
    if text.lower() in {"indeks", "indeksfond", "index fund"}:
        return "Indeksfond"
    if text.lower() in {"aktivt", "aktivt fond", "active fund"}:
        return "Aktivt fond"
    if text.lower() in {"fond", "fund"}:
        return "Fond"
    return text or "Aksje"


def _units_label_for_asset(asset_type):
    asset_type = _normalize_asset_type(asset_type)
    if asset_type in FUND_ASSET_TYPES:
        return "andeler" if asset_type != "ETF" else "units"
    return "shares"


def paper_buy_instrument(
    symbol,
    price,
    amount,
    asset_type="ETF",
    confidence=0,
    reason="Manuelt paper-kjøp",
    currency="NOK",
    nav_date="",
    purchase_mode="Engangskjøp",
):
    """Buy a paper-trading instrument by amount.

    v18.5.45: Supports ETF/fund accumulation. Unlike the legacy stock
    paper_buy(), this function can add to an existing fund/ETF position and uses
    a user-selected amount instead of position-size rules.
    """
    symbol = _normalize_paper_symbol(symbol)
    asset_type = _normalize_asset_type(asset_type)
    currency = str(currency or "NOK").upper()
    try:
        price = float(price)
        amount = float(amount)
    except Exception:
        return False, "Ugyldig pris eller beløp"
    if not symbol:
        return False, "Mangler symbol"
    if price <= 0:
        return False, "Ugyldig pris/NAV"
    if amount <= 0:
        return False, "Beløp må være større enn 0"

    portfolio = load_portfolio()
    before = build_paper_state_snapshot(portfolio)
    ok, msg = validate_buy_order(
        portfolio,
        ticker=symbol,
        price=price,
        amount=amount,
        confidence=int(confidence or 0),
        min_confidence=0,
        allow_existing=True,
        safety_mode=_settings_bool("auto_buy_safety_mode", True),
    )
    if not ok:
        audit_state_transition("paper_instrument_buy_blocked", before, detail={"symbol": symbol, "amount": round(float(amount or 0), 2), "reason": msg}, level="WARNING")
        return False, explain_blocked_action([msg], action="Kjøp")
    cash = float(portfolio.get("cash", 0) or 0)

    units = amount / price
    positions = portfolio.setdefault("positions", {})
    existing = positions.get(symbol)
    units_label = _units_label_for_asset(asset_type)
    if existing:
        old_units = float(existing.get("shares", 0) or 0)
        old_avg = float(existing.get("entry_price", existing.get("avg_price", price)) or price)
        new_units = old_units + units
        new_avg = ((old_units * old_avg) + amount) / new_units if new_units else price
        existing.update({
            "ticker": symbol,
            "shares": new_units,
            "entry_price": round(new_avg, 6),
            "avg_price": round(new_avg, 6),
            "last_price": price,
            "highest_price": max(float(existing.get("highest_price", price) or price), price),
            "asset_type": asset_type,
            "units_label": units_label,
            "currency": currency,
            "nav_date": nav_date or existing.get("nav_date", ""),
            "purchase_mode": purchase_mode,
            "confidence": int(confidence or existing.get("confidence", 0) or 0),
            "reason": reason,
        })
    else:
        sl, tp, tr = calc_levels(price, price)
        positions[symbol] = {
            "ticker": symbol,
            "shares": units,
            "entry_price": price,
            "avg_price": price,
            "last_price": price,
            "highest_price": price,
            "stop_loss": 0 if asset_type in FUND_ASSET_TYPES else sl,
            "take_profit": 0 if asset_type in FUND_ASSET_TYPES else tp,
            "trailing_stop": 0 if asset_type in FUND_ASSET_TYPES else tr,
            "confidence": int(confidence or 0),
            "reason": reason,
            "opened_at": datetime.now().isoformat(timespec="seconds"),
            "asset_type": asset_type,
            "units_label": units_label,
            "currency": currency,
            "nav_date": nav_date,
            "purchase_mode": purchase_mode,
        }

    portfolio["cash"] = round(cash - amount, 2)
    add_trade(portfolio, {
        "type": "BUY",
        "ticker": symbol,
        "price": round(price, 6),
        "shares": round(units, 8),
        "amount": round(amount, 2),
        "confidence": int(confidence or 0),
        "reason": reason,
        "asset_type": asset_type,
        "currency": currency,
        "nav_date": nav_date,
        "order_kind": "amount_buy",
    })
    after = build_paper_state_snapshot(portfolio)
    audit_state_transition("paper_instrument_buy_executed", before, after, {"symbol": symbol, "asset_type": asset_type, "amount": round(amount, 2), "price": round(price, 6), "currency": currency, "purchase_mode": purchase_mode})
    notify_executed_trade("BUY", symbol, price, shares=units, amount=amount, confidence=confidence, reason=reason)
    return True, f"KJØP {asset_type} {symbol}: {amount:.2f} {currency} @ {price:.4f}"


def paper_sell_instrument(symbol, price, sell_amount=None, reason="Manuelt paper-salg", currency="NOK", nav_date=""):
    """Sell all or part of a paper-trading instrument by amount.

    If sell_amount is None, the whole position is sold. If sell_amount is lower
    than current value, only a proportional number of units is sold.
    """
    symbol = _normalize_paper_symbol(symbol)
    try:
        price = float(price)
    except Exception:
        return False, "Ugyldig pris/NAV"
    if not symbol:
        return False, "Mangler symbol"
    if price <= 0:
        return False, "Ugyldig pris/NAV"

    portfolio = load_portfolio()
    before = build_paper_state_snapshot(portfolio)
    pos = portfolio.get("positions", {}).get(symbol)
    if not pos:
        audit_state_transition("paper_instrument_sell_blocked", before, detail={"symbol": symbol, "reason": "missing_position"}, level="WARNING")
        return False, f"Ingen posisjon i {symbol}"

    units = float(pos.get("shares", 0) or 0)
    entry = float(pos.get("entry_price", pos.get("avg_price", price)) or price)
    current_value = units * price
    if current_value <= 0:
        return False, "Posisjonen har ingen verdi"
    if sell_amount is None or float(sell_amount or 0) <= 0 or float(sell_amount or 0) >= current_value:
        units_to_sell = units
        amount = current_value
        close_all = True
    else:
        amount = float(sell_amount)
        units_to_sell = amount / price
        close_all = False

    pnl_pct = ((price - entry) / entry * 100) if entry else 0
    portfolio["cash"] = round(float(portfolio.get("cash", 0) or 0) + amount, 2)
    if close_all:
        del portfolio["positions"][symbol]
    else:
        pos["shares"] = max(0.0, units - units_to_sell)
        pos["last_price"] = price
        pos["nav_date"] = nav_date or pos.get("nav_date", "")
        portfolio["positions"][symbol] = pos

    add_trade(portfolio, {
        "type": "SELL",
        "ticker": symbol,
        "price": round(price, 6),
        "shares": round(units_to_sell, 8),
        "amount": round(amount, 2),
        "confidence": int(pos.get("confidence", 0) or 0),
        "pnl_pct": round(pnl_pct, 2),
        "reason": reason,
        "asset_type": pos.get("asset_type", "Aksje"),
        "currency": currency or pos.get("currency", ""),
        "nav_date": nav_date or pos.get("nav_date", ""),
        "order_kind": "amount_sell" if not close_all else "sell_all",
    })
    after = build_paper_state_snapshot(portfolio)
    audit_state_transition("paper_instrument_sell_executed", before, after, {"symbol": symbol, "amount": round(amount, 2), "price": round(price, 6), "pnl_pct": round(pnl_pct, 2), "close_all": close_all})
    notify_executed_trade("SELL", symbol, price, shares=units_to_sell, amount=amount, confidence=pos.get("confidence"), reason=reason)
    suffix = "alt" if close_all else f"{amount:.2f} {currency}"
    return True, f"SALG {symbol}: {suffix} @ {price:.4f} ({pnl_pct:.2f}%)"


# -------------------------------------------------------------------
# Pro signal tuning v1
# Conservative rules to reduce bad BUYs:
# - no BUY when RSI is high/overbought
# - prefer BUY only with good score + MACD/breakout support
# -------------------------------------------------------------------
def pro_signal_from_context(base_score, technical_context=None):
    technical_context = technical_context or {}
    try:
        score = float(base_score or 0)
    except Exception:
        score = 0.0

    try:
        rsi = float(technical_context.get("rsi", 50))
    except Exception:
        rsi = 50.0

    macd_bullish = bool(technical_context.get("macd_bullish", False))
    breakout_type = str(technical_context.get("breakout_type", "neutral")).lower()

    buy_ok = (
        score >= 7.0
        and rsi < 70
        and (macd_bullish or breakout_type in ["bullish", "breakout", "up"])
    )

    sell_avoid = (
        score <= 4.0
        or rsi >= 78
        or breakout_type in ["bearish", "breakdown", "down"]
    )

    return buy_ok, sell_avoid, rsi, macd_bullish, breakout_type
