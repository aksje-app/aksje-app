import logging
from datetime import datetime, timedelta
from typing import Any, Mapping
from signal_engine import score_signal
from notifier import notify_trade
from trading_settings import load_rules
from ui_trust import explain_blocked_action
from services.strategy_binding import stamp_strategy_metadata, strategy_metadata
try:
    from settings_store import load_settings
except Exception:
    load_settings = None

from paper_store import load_portfolio, save_portfolio, add_trade
from paper_trading_valuation import normalize_paper_position, paper_reason_label
from explainability import explain_buy_decision, explain_sell_decision
from paper_trading_professional import exit_priority_decision
from paper_trading_guard import check_paper_trade, record_paper_trade

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

MANUAL_OVERRIDE_STATES = {"OFF", "REVIEW_ONLY", "FORCE_ALLOW", "FORCE_BLOCK"}


def normalize_manual_override_state(value: Any = "OFF") -> str:
    """Normalize paper-trading manual override state.

    OFF never blocks. FORCE_BLOCK is the only manual state that blocks by itself.
    FORCE_ALLOW may bypass soft paper rules, but hard checks like price, ticker,
    cash and hard validation still protect the simulated portfolio. Existing stock positions can be increased with weighted average price.
    """
    raw = str(value or "OFF").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "": "OFF",
        "NONE": "OFF",
        "INGEN": "OFF",
        "FALSE": "OFF",
        "0": "OFF",
        "TRUE": "REVIEW_ONLY",
        "1": "REVIEW_ONLY",
        "ALLOW": "FORCE_ALLOW",
        "TILLAT": "FORCE_ALLOW",
        "BLOCK": "FORCE_BLOCK",
        "BLOKKER": "FORCE_BLOCK",
        "REVIEW": "REVIEW_ONLY",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in MANUAL_OVERRIDE_STATES else "OFF"


def _manual_override_note(state: str) -> str:
    state = normalize_manual_override_state(state)
    if state == "FORCE_BLOCK":
        return "Manuell overstyring: FORCE_BLOCK - kjøp stoppet eksplisitt av bruker."
    if state == "FORCE_ALLOW":
        return "Manuell overstyring: FORCE_ALLOW - myke paper-regler kan overstyres, hardvalidering beholdes."
    if state == "REVIEW_ONLY":
        return "Manuell overstyring: REVIEW_ONLY - merkes for vurdering, blokkerer ikke alene."
    return "Manuell overstyring: OFF - påvirker ikke kjøp."


def build_trading_decision(item, technical_context=None):
    """
    Smart Core v2 wrapper.
    Beholder app13-kompatibelt output.
    """
    return stamp_strategy_metadata(score_signal(item, technical_context or {}), "technical")




def _settings_bool(name, default=False):
    try:
        if load_settings is None:
            return bool(default)
        settings = load_settings() or {}
        return bool(settings.get(name, default))
    except Exception:
        return bool(default)


def _position_market_value(portfolio, rules=None):
    """Current market value of open positions using last_price/entry fallback."""
    total = 0.0
    for _ticker, pos in (portfolio or {}).get("positions", {}).items():
        try:
            normalized = normalize_paper_position(_ticker, pos, rules=rules)
            shares = float(normalized.get("shares", normalized.get("units", 0)) or 0)
            price = float(normalized.get("last_price", normalized.get("entry_price", 0)) or 0)
            total += shares * price
        except Exception:
            continue
    return round(total, 2)


def paper_liquidity_snapshot(portfolio=None, latest_prices=None, rules=None):
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
            normalized = normalize_paper_position(ticker, pos, latest_price=latest_prices.get(ticker), rules=rules)
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


def portfolio_value(portfolio=None, latest_prices=None, rules=None):
    portfolio = portfolio or load_portfolio()
    latest_prices = latest_prices or {}
    total = float(portfolio.get("cash", 0))
    for ticker, pos in portfolio.get("positions", {}).items():
        normalized = normalize_paper_position(ticker, pos, latest_price=latest_prices.get(ticker), rules=rules)
        total += float(normalized.get("shares", 0)) * float(normalized.get("last_price", 0) or 0)
    return round(total, 2)


def calc_levels(entry_price, highest_price=None, *, stop_loss_pct=None, take_profit_pct=None, trailing_stop_pct=None):
    """
    Bruker lagrede trading-regler som standard, men v18.6.74d kan bruke
    per-posisjon trailing_stop_pct slik at gamle posisjoner ikke endres
    tilfeldig når global slider justeres.
    """
    rules = load_rules()
    entry_price = float(entry_price)
    highest_price = float(highest_price or entry_price)

    stop_loss_pct = float(rules.get("stop_loss_pct", STOP_LOSS_PCT) if stop_loss_pct is None else stop_loss_pct)
    take_profit_pct = float(rules.get("take_profit_pct", TAKE_PROFIT_PCT) if take_profit_pct is None else take_profit_pct)
    trailing_stop_pct = float(rules.get("trailing_stop_pct", TRAILING_STOP_PCT) if trailing_stop_pct is None else trailing_stop_pct)

    stop_loss = entry_price * (1 - stop_loss_pct / 100)
    take_profit = entry_price * (1 + take_profit_pct / 100)
    trailing_stop = highest_price * (1 - trailing_stop_pct / 100) if trailing_stop_pct > 0 else 0.0

    return round(stop_loss, 2), round(take_profit, 2), round(trailing_stop, 2)









def position_trailing_stop_pct_v18674d(pos: Mapping[str, Any] | None, rules: Mapping[str, Any] | None = None) -> float:
    """Return the trailing stop percent stored on the position, or current rule for legacy positions."""
    rules = rules or load_rules()
    try:
        if pos and pos.get("trailing_stop_pct") not in (None, ""):
            return float(pos.get("trailing_stop_pct") or 0)
    except Exception:
        pass
    try:
        asset_type = str((pos or {}).get("asset_type") or "Aksje")
        if asset_type in {"ETF", "Fond", "Indeksfond", "Aktivt fond", "Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond", "Kombinasjonsfond"}:
            return 0.0
    except Exception:
        pass
    return float((rules or {}).get("trailing_stop_pct", TRAILING_STOP_PCT) or TRAILING_STOP_PCT)


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
    "strategy_family",
    "strategy_id",
    "strategy_version",
    "parameter_version",
    "strategy_version_id",
    "strategy_implementation_version",
    "strategy_config_checksum",
    "strategy_binding_verified",
    "run_id",
    "scan_id",
    "scanner_execution_id",
    "decision_id",
    "market_data_at",
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
    ctx.update(strategy_metadata("technical"))
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

def _parse_trade_time_v18660(value):
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _automatic_signal_fresh_v1931ay(trade_context, rules, now=None):
    """Fail closed when an automatic order lacks a fresh market-data timestamp."""
    ctx = dict(trade_context or {}) if isinstance(trade_context, Mapping) else {}
    if not bool(ctx.get("automatic")):
        return True, ""
    stamp = _parse_trade_time_v18660(ctx.get("market_data_at"))
    if stamp is None:
        return False, "Automatisk handel blokkert: tidspunkt for markedsdata mangler eller er ugyldig."
    try:
        max_age = max(1.0, float((rules or {}).get("automatic_signal_max_age_minutes", 120) or 120))
    except Exception:
        max_age = 120.0
    age_minutes = ((now or datetime.now()) - stamp).total_seconds() / 60.0
    if age_minutes < -5.0 or age_minutes > max_age:
        return False, f"Automatisk handel blokkert: markedsdata er {age_minutes:.1f} minutter gamle (maks {max_age:.0f})."
    return True, ""


def _reentry_block_v1931ay(portfolio, ticker, confidence, rules, buy_price=None, now=None):
    """Block churn after every SELL; risk exits receive a longer quarantine."""
    ticker = str(ticker or "").upper().strip()
    now = now or datetime.now()
    trades = list((portfolio or {}).get("trades", []) or [])
    for trade in reversed(trades):
        try:
            if str(trade.get("ticker") or "").upper().strip() != ticker:
                continue
            if str(trade.get("type") or "").upper() != "SELL":
                continue
            reason = str(trade.get("reason") or "").lower()
            rule_used = str(trade.get("rule_used") or "").lower()
            risk_exit = any(token in f"{reason} {rule_used}" for token in ("stop loss", "stop-loss", "trailing stop"))
            cooldown_key = "risk_exit_cooldown_days" if risk_exit else "sell_signal_cooldown_days"
            cooldown_days = int((rules or {}).get(cooldown_key, 10 if risk_exit else 5) or 0)
            if cooldown_days <= 0:
                return False, ""
            sold_at = _parse_trade_time_v18660(trade.get("time"))
            if sold_at is None:
                return True, f"{ticker} er blokkert for nytt kjøp etter salg. Karantene: {cooldown_days} dager."
            age_days = (now - sold_at).total_seconds() / 86400.0
            if age_days < cooldown_days:
                remaining = max(1, int(round(cooldown_days - age_days)))
                return True, (
                    f"{ticker} ble nylig solgt ({'risikoutgang' if risk_exit else 'ordinært salg'}) og kan ikke kjøpes igjen ennå. "
                    f"Karantene gjenstår ca. {remaining} dag(er)."
                )
            try:
                sold_price = float(trade.get("price") or 0)
                max_premium = float((rules or {}).get("block_rebuy_above_recent_sell_pct", 0.5) or 0.5)
                premium = ((float(buy_price) / sold_price) - 1) * 100 if sold_price > 0 and buy_price is not None else 0.0
                if premium > max_premium and age_days < max(cooldown_days * 2, 10):
                    return True, f"{ticker} kan ikke kjøpes {premium:.2f}% dyrere kort tid etter salg uten dokumentert regimeskifte."
            except Exception:
                pass
            return False, ""
        except Exception:
            continue
    return False, ""


def _stop_loss_reentry_block_v18660(portfolio, ticker, confidence, rules):
    """Compatibility alias; v19.22.0-rc16.31ay protects every SELL."""
    return _reentry_block_v1931ay(portfolio, ticker, confidence, rules)


def _automatic_repeat_buy_block_v1931ay(portfolio, ticker, rules, now=None):
    """Prevent duplicate/addition BUYs from overlapping or repeated cron runs."""
    try:
        cooldown_hours = max(0.0, float((rules or {}).get("automatic_same_ticker_buy_cooldown_hours", 24) or 0))
    except Exception:
        cooldown_hours = 24.0
    if cooldown_hours <= 0:
        return False, ""
    ticker = str(ticker or "").upper().strip()
    now = now or datetime.now()
    for trade in (portfolio or {}).get("trades", []) or []:
        if str(trade.get("ticker") or "").upper().strip() != ticker or str(trade.get("type") or "").upper() != "BUY":
            continue
        bought_at = _parse_trade_time_v18660(trade.get("time"))
        if bought_at is None:
            return True, f"Automatisk tilleggskjøp i {ticker} blokkert fordi forrige kjøp mangler gyldig tidspunkt."
        age_hours = (now - bought_at).total_seconds() / 3600.0
        if age_hours < cooldown_hours:
            return True, f"Automatisk tilleggskjøp i {ticker} blokkert: forrige kjøp var for {age_hours:.1f} timer siden (minimum {cooldown_hours:.0f})."
        return False, ""
    return False, ""



def paper_buy(ticker, price, confidence=0, reason="BUY signal", trade_context=None, amount_override=None, manual_override="OFF", target_price=None, initial_risk_amount=None):
    gate_context = dict(trade_context or {}) if isinstance(trade_context, Mapping) else {}
    gate = check_paper_trade(
        "BUY", ticker=ticker, source=gate_context.get("source") or "trading_engine.paper_buy",
        run_id=gate_context.get("run_id") or gate_context.get("execution_id") or "",
        candidate=gate_context.get("candidate") if isinstance(gate_context.get("candidate"), Mapping) else None,
        automatic=bool(gate_context.get("automatic")),
    )
    if not gate.allowed:
        return False, explain_blocked_action([gate.message], action="Kjøp")
    rules = load_rules()
    fresh, freshness_msg = _automatic_signal_fresh_v1931ay(gate_context, rules)
    if not fresh:
        return False, explain_blocked_action([freshness_msg], action="Kjøp")
    max_open_positions = int(rules.get("max_open_positions", MAX_OPEN_POSITIONS))
    max_trades_per_day = int(rules.get("max_trades_per_day", 3))
    min_buy_confidence = int(rules.get("min_buy_confidence", MIN_BUY_CONFIDENCE))
    position_size_pct = float(rules.get("position_size_pct", POSITION_SIZE_PCT))
    portfolio = load_portfolio()
    before = build_paper_state_snapshot(portfolio, rules=rules)
    ticker = str(ticker).upper()
    trade_ctx = _merge_trade_context(ticker, trade_context)
    manual_override_state = normalize_manual_override_state(manual_override)
    if bool(gate_context.get("automatic")):
        repeat_blocked, repeat_msg = _automatic_repeat_buy_block_v1931ay(portfolio, ticker, rules)
        if repeat_blocked:
            audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "reason": "automatic_repeat_buy", "message": repeat_msg}, level="WARNING")
            return False, explain_blocked_action([repeat_msg], action="Kjøp")
    if not trade_ctx.get("rule_used"):
        trade_ctx["rule_used"] = "BUY signal"
    if not trade_ctx.get("measured_value"):
        trade_ctx["measured_value"] = f"confidence {int(confidence or 0)}"
    trade_ctx["manual_override"] = manual_override_state
    trade_ctx["manual_override_note"] = _manual_override_note(manual_override_state)
    trade_ctx["trade_explanation"] = _default_trade_explanation("BUY", reason, trade_ctx)
    trade_ctx["explain_ai"] = explain_buy_decision(trade_ctx, {"decision": "BUY", "confidence": confidence})
    if manual_override_state in {"FORCE_ALLOW", "FORCE_BLOCK", "REVIEW_ONLY"}:
        trade_ctx["trade_explanation"] = (str(trade_ctx.get("trade_explanation") or "") + " " + _manual_override_note(manual_override_state)).strip()
    reason = paper_reason_label(reason, "BUY") or "PAPER-KJØP"
    if manual_override_state == "FORCE_BLOCK":
        msg = "Manuell overstyring: FORCE_BLOCK - kjøp stoppet eksplisitt."
        audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "reason": "manual_force_block", "manual_override": manual_override_state, "message": msg}, level="WARNING")
        return False, explain_blocked_action([msg], action="Kjøp")
    if manual_override_state == "REVIEW_ONLY":
        msg = "Manuell overstyring: REVIEW_ONLY - kjøp er ikke gjennomført. Aksjen skal legges i Gule flagg / Manuell vurdering."
        audit_state_transition("paper_buy_review_only", before, detail={"ticker": ticker, "reason": "manual_review_only", "manual_override": manual_override_state, "message": msg}, level="INFO")
        return False, msg
    blocked, cooldown_msg = _reentry_block_v1931ay(portfolio, ticker, confidence, rules, buy_price=price)
    if blocked and (bool(gate_context.get("automatic")) or manual_override_state != "FORCE_ALLOW"):
        audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "reason": "sell_reentry_quarantine", "manual_override": manual_override_state, "message": cooldown_msg}, level="WARNING")
        return False, explain_blocked_action([cooldown_msg], action="Kjøp")
    if blocked and manual_override_state == "FORCE_ALLOW":
        audit_state_transition("paper_buy_manual_override_bypass", before, detail={"ticker": ticker, "reason": "sell_reentry_quarantine", "manual_override": manual_override_state, "message": cooldown_msg}, level="WARNING")
    try:
        price = float(price)
    except Exception:
        audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "reason": "invalid_price"}, level="WARNING")
        return False, "Ugyldig prisdata - kjøp stoppet"
    total_value = portfolio_value(portfolio)
    available_cash = float(portfolio.get("cash", 0) or 0)
    if amount_override is not None:
        try:
            requested_amount = float(amount_override)
        except Exception:
            requested_amount = 0.0
        amount = min(available_cash, max(0.0, requested_amount))
    else:
        amount = min(available_cash, total_value * position_size_pct / 100)
    force_allow = manual_override_state == "FORCE_ALLOW"
    positions = portfolio.setdefault("positions", {})
    existing_pos = positions.get(ticker)
    ok, msg = validate_buy_order(
        portfolio,
        ticker=ticker,
        price=price,
        amount=amount,
        confidence=int(confidence or 0),
        min_confidence=0 if force_allow else min_buy_confidence,
        allow_existing=True,
        max_open_positions=None if (force_allow or existing_pos) else max_open_positions,
        max_buys_per_day=None if force_allow else max_trades_per_day,
        safety_mode=_settings_bool("auto_buy_safety_mode", True),
    )
    if not ok:
        audit_state_transition("paper_buy_blocked", before, detail={"ticker": ticker, "amount": round(float(amount or 0), 2), "reason": msg, "manual_override": manual_override_state}, level="WARNING")
        return False, explain_blocked_action([msg], action="Kjøp")
    shares = amount / price
    is_add_to_position = bool(existing_pos)
    if is_add_to_position:
        old_shares = float(existing_pos.get("shares", existing_pos.get("units", 0)) or 0)
        old_avg = float(existing_pos.get("entry_price", existing_pos.get("avg_price", price)) or price)
        new_shares = old_shares + shares
        new_avg = ((old_shares * old_avg) + amount) / new_shares if new_shares else price
        trailing_pct_for_position = position_trailing_stop_pct_v18674d(existing_pos, rules)
        old_high = float(existing_pos.get("highest_price", existing_pos.get("last_price", old_avg)) or old_avg)
        existing_last = float(existing_pos.get("last_price", old_avg) or old_avg)
        highest = max(old_high, existing_last, price, new_avg)
        sl, tp, tr = calc_levels(new_avg, highest, trailing_stop_pct=trailing_pct_for_position)
        existing_pos.update({
            "ticker": ticker,
            "shares": new_shares,
            "units": new_shares,
            "entry_price": round(new_avg, 6),
            "avg_price": round(new_avg, 6),
            "last_price": price,
            "highest_price": highest,
            "stop_loss": sl,
            "take_profit": tp,
            "trailing_stop": tr,
            "trailing_stop_level": tr,
            "trailing_stop_pct": trailing_pct_for_position,
        "target_price": float(target_price or 0),
        "initial_risk_amount": float(initial_risk_amount or 0),
            "confidence": int(confidence or existing_pos.get("confidence", 0) or 0),
            "reason": reason,
            "asset_type": "Aksje",
            "units_label": "shares",
            "last_added_at": datetime.now().isoformat(timespec="seconds"),
            "target_price": float(target_price or existing_pos.get("target_price", 0) or 0),
            "initial_risk_amount": float(initial_risk_amount or existing_pos.get("initial_risk_amount", 0) or 0),
            "country": trade_ctx.get("country", existing_pos.get("country", "")),
            "market": trade_ctx.get("market", existing_pos.get("market", "")),
            "sector": trade_ctx.get("sector", existing_pos.get("sector", "")),
            "industry": trade_ctx.get("industry", existing_pos.get("industry", "")),
        })
        order_kind = "paper_add_to_position"
        result_label = "PAPER-TILLEGGSKJØP"
    else:
        trailing_pct_for_position = float(rules.get("trailing_stop_pct", TRAILING_STOP_PCT) or TRAILING_STOP_PCT)
        sl, tp, tr = calc_levels(price, price, trailing_stop_pct=trailing_pct_for_position)
        positions[ticker] = {
            "ticker": ticker, "shares": shares, "entry_price": price, "avg_price": price,
            "last_price": price, "highest_price": price, "stop_loss": sl,
            "take_profit": tp, "trailing_stop": tr, "trailing_stop_level": tr, "trailing_stop_pct": trailing_pct_for_position, "confidence": int(confidence or 0), "reason": reason,
            "opened_at": datetime.now().isoformat(timespec="seconds"), "asset_type": "Aksje", "units_label": "shares",
            "target_price": float(target_price or 0), "initial_risk_amount": float(initial_risk_amount or 0),
            "country": trade_ctx.get("country", ""), "market": trade_ctx.get("market", ""),
            "sector": trade_ctx.get("sector", ""), "industry": trade_ctx.get("industry", ""),
        }
        order_kind = "paper"
        result_label = "PAPER-KJØP"
    portfolio["cash"] = round(float(portfolio.get("cash", 0)) - amount, 2)
    add_trade(portfolio, {
        "type":"BUY", "ticker":ticker, "price":round(price,2), "shares":round(shares,6),
        "amount":round(amount,2), "confidence":int(confidence or 0), "reason":reason,
        "order_kind":order_kind, "asset_type": "Aksje",
        "manual_override": manual_override_state,
        "manual_override_note": _manual_override_note(manual_override_state),
        "trailing_stop_pct": trailing_pct_for_position,
        **{key: trade_ctx.get(key, "") for key in TRADE_CONTEXT_KEYS},
    })
    after = build_paper_state_snapshot(portfolio, rules=rules)
    audit_state_transition("paper_buy_executed", before, after, {"ticker": ticker, "price": round(price, 4), "amount": round(amount, 2), "confidence": int(confidence or 0), "reason": reason, "manual_override": manual_override_state, "add_to_existing": is_add_to_position})
    record_paper_trade("BUY", ticker=ticker, run_id=gate.run_id)
    notify_executed_trade("BUY", ticker, price, shares=shares, amount=amount, confidence=confidence, reason=reason)
    return True, f"{result_label} {ticker} @ {price:.2f}"


def paper_sell(ticker, price, reason="SELL signal", trade_context=None, sell_pct=100.0, sell_shares=None):
    gate_context = dict(trade_context or {}) if isinstance(trade_context, Mapping) else {}
    gate = check_paper_trade(
        "SELL", ticker=ticker, source=gate_context.get("source") or "trading_engine.paper_sell",
        run_id=gate_context.get("run_id") or gate_context.get("execution_id") or "",
        candidate=gate_context.get("candidate") if isinstance(gate_context.get("candidate"), Mapping) else None,
        automatic=bool(gate_context.get("automatic")),
    )
    if not gate.allowed:
        return False, explain_blocked_action([gate.message], action="Salg")
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
    total_shares = float(normalized_pos.get("shares", 0))
    entry = float(normalized_pos.get("entry_price", normalized_pos.get("avg_price", price)))
    if sell_shares is not None:
        shares = min(total_shares, max(0.0, float(sell_shares)))
    else:
        pct = min(100.0, max(0.0, float(sell_pct or 100.0)))
        shares = total_shares * pct / 100.0
    if shares <= 0:
        return False, "Salgsantall må være større enn 0"
    amount = shares * price
    pnl_pct = ((price-entry)/entry*100) if entry else 0
    trade_ctx["trade_explanation"] = _default_trade_explanation("SELL", reason, trade_ctx)
    trade_ctx["explain_ai"] = explain_sell_decision(reason, trade_ctx)
    portfolio["cash"] = round(float(portfolio.get("cash", 0)) + amount, 2)
    remaining_shares = max(0.0, total_shares - shares)
    is_partial = remaining_shares > 1e-9
    if is_partial:
        pos["shares"] = remaining_shares
        pos["units"] = remaining_shares
        pos["last_price"] = price
        pos["last_partial_sell_at"] = datetime.now().isoformat(timespec="seconds")
        portfolio["positions"][ticker] = pos
    else:
        del portfolio["positions"][ticker]
    add_trade(portfolio, {
        "type":"SELL", "ticker":ticker, "price":round(price,2), "shares":round(shares,6),
        "amount":round(amount,2), "confidence":int(pos.get("confidence",0) or 0),
        "pnl_pct":round(pnl_pct,2), "reason":reason, "order_kind":"paper_partial_sell" if is_partial else "paper",
        "sell_pct": round((shares / total_shares * 100.0) if total_shares else 100.0, 2),
        "remaining_shares": round(remaining_shares, 6),
        "asset_type": pos.get("asset_type", "Aksje"),
        **{key: trade_ctx.get(key, "") for key in TRADE_CONTEXT_KEYS},
    })
    after = build_paper_state_snapshot(portfolio)
    audit_state_transition("paper_sell_executed", before, after, {"ticker": ticker, "price": round(price, 4), "amount": round(amount, 2), "pnl_pct": round(pnl_pct, 2), "reason": reason})
    record_paper_trade("SELL", ticker=ticker, run_id=gate.run_id)
    notify_executed_trade("SELL", ticker, price, shares=shares, amount=amount, confidence=pos.get("confidence"), reason=reason)
    return True, f"PAPER-SALG {ticker} @ {price:.2f} ({pnl_pct:.2f}%)" + (f" - {shares:.4f} solgt, {remaining_shares:.4f} gjenstår" if is_partial else "")


def _auto_sell_hold_guard_v18675(pos, rules, reason_kind="signal"):
    """Protect newly opened positions from rapid signal-flip exits.

    Hard risk exits (stop-loss, trailing stop and take-profit) remain active.
    The guard only blocks ordinary SELL/AVOID and RSI exits during minimum hold.
    """
    try:
        minimum_hours = max(0.0, float((rules or {}).get("minimum_hold_hours", 24) or 0))
    except Exception:
        minimum_hours = 24.0
    raw = (pos or {}).get("last_added_at") or (pos or {}).get("opened_at") or (pos or {}).get("entry_time")
    try:
        opened = datetime.fromisoformat(str(raw))
        age_hours = max(0.0, (datetime.now() - opened).total_seconds() / 3600.0)
    except Exception:
        return True, 0.0, minimum_hours
    return age_hours >= minimum_hours, age_hours, minimum_hours


def auto_trade(ticker, price, signal, confidence=0, rsi=None, prev_rsi=None, trade_context=None):
    auto_context = dict(trade_context or {}) if isinstance(trade_context, Mapping) else {}
    auto_context.setdefault("source", "trading_engine.auto_trade")
    auto_context["automatic"] = True
    gate = check_paper_trade(
        "TRADE", ticker=ticker, source=auto_context.get("source"),
        run_id=auto_context.get("run_id") or auto_context.get("execution_id") or "",
        automatic=True,
    )
    if not gate.allowed:
        return False, gate.message
    portfolio = load_portfolio()
    rules = load_rules()
    ticker = str(ticker).upper()
    price = float(price)
    sig = str(signal or "").upper()
    pos = portfolio.get("positions", {}).get(ticker)
    if pos:
        entry = float(pos.get("entry_price", pos.get("avg_price", price)))
        high = max(float(pos.get("highest_price", entry) or entry), price)
        trailing_stop_pct = position_trailing_stop_pct_v18674d(pos, rules)
        sl, tp, tr = calc_levels(entry, high, trailing_stop_pct=trailing_stop_pct)
        pos.update({"last_price": price, "highest_price": high, "stop_loss": sl, "take_profit": tp, "trailing_stop": tr, "trailing_stop_level": tr, "trailing_stop_pct": trailing_stop_pct})
        portfolio["positions"][ticker] = pos
        save_portfolio(portfolio)
        pnl_pct = ((price-entry)/entry*100) if entry else 0
        stop_loss_pct = float(rules.get("stop_loss_pct", STOP_LOSS_PCT))
        take_profit_pct = float(rules.get("take_profit_pct", TAKE_PROFIT_PCT))
        rsi_exit_level = float(rules.get("rsi_exit_level", 75))
        rsi_must_fall = bool(rules.get("rsi_must_fall", True))

        if price <= sl:
            return paper_sell(ticker, price, f"Stop loss {pnl_pct:.2f}%", {**auto_context,
                "rule_used": "Stop-loss",
                "rule_limit": _format_pct(-stop_loss_pct),
                "measured_value": _format_pct(pnl_pct),
                "trade_explanation": f"Solgt fordi tapet var {pnl_pct:.2f}%, som er lik eller under stop-loss {stop_loss_pct:.2f}%.",
            })
        if price >= tp:
            return paper_sell(ticker, price, f"Take profit {pnl_pct:.2f}%", {**auto_context,
                "rule_used": "Take-profit",
                "rule_limit": _format_pct(take_profit_pct),
                "measured_value": _format_pct(pnl_pct),
                "trade_explanation": f"Solgt fordi gevinsten var {pnl_pct:.2f}%, som er lik eller over take-profit {take_profit_pct:.2f}%.",
            })
        if high > entry and price <= tr:
            drop_from_high = ((price - high) / high * 100) if high else 0
            return paper_sell(ticker, price, f"Trailing stop {pnl_pct:.2f}%", {**auto_context,
                "rule_used": "Trailing stop",
                "rule_limit": _format_pct(-trailing_stop_pct),
                "measured_value": _format_pct(drop_from_high),
                "trade_explanation": f"Solgt fordi kursen falt {abs(drop_from_high):.2f}% fra topp etter at posisjonen hadde vaert i pluss.",
            })
        target_price = float(pos.get("target_price", 0) or 0)
        if target_price > 0 and price >= target_price:
            return paper_sell(ticker, price, f"Target price {pnl_pct:.2f}%", {**auto_context,
                "rule_used": "Target price",
                "rule_limit": f"{target_price:.2f}",
                "measured_value": f"{price:.2f}",
                "trade_explanation": f"Solgt fordi målpris {target_price:.2f} ble nådd.",
            })
        try:
            current_rsi = float(rsi) if rsi is not None else None
            previous_rsi = float(prev_rsi) if prev_rsi is not None else None
            rsi_is_falling = previous_rsi is not None and current_rsi is not None and current_rsi < previous_rsi
            if current_rsi is not None and current_rsi >= rsi_exit_level and (not rsi_must_fall or rsi_is_falling):
                allowed_exit, age_hours, min_hours = _auto_sell_hold_guard_v18675(pos, rules, "rsi")
                if not allowed_exit:
                    return False, f"HOLD {ticker}: RSI-exit blokkert av minimum holdetid ({age_hours:.1f}/{min_hours:.1f} timer)"
                return paper_sell(ticker, price, f"RSI sell {current_rsi:.1f}", {**auto_context,
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
            allowed_exit, age_hours, min_hours = _auto_sell_hold_guard_v18675(pos, rules, "signal")
            if not allowed_exit:
                audit_state_transition("paper_auto_sell_hold_blocked", build_paper_state_snapshot(portfolio, rules=rules), detail={"ticker": ticker, "signal": sig, "age_hours": round(age_hours, 2), "minimum_hold_hours": min_hours})
                return False, f"HOLD {ticker}: SELL/AVOID blokkert av minimum holdetid ({age_hours:.1f}/{min_hours:.1f} timer)"
            return paper_sell(ticker, price, "SELL signal", {**auto_context,
                "rule_used": "SELL/AVOID signal",
                "rule_limit": "signal",
                "measured_value": sig,
                "trade_explanation": f"Solgt fordi signalmotoren ga {sig or 'SELL/AVOID'} etter risikosjekk.",
            })
        return False, f"HOLD {ticker}"
    if "BUY" in sig:
        return paper_buy(ticker, price, confidence, "BUY signal", {**auto_context,
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
    manual_override="OFF",
    trade_context=None,
):
    """Buy a paper-trading instrument by amount.

    v18.5.45: Supports ETF/fund accumulation. Unlike the legacy stock
    paper_buy(), this function can add to an existing fund/ETF position and uses
    a user-selected amount instead of position-size rules.
    """
    gate_context = dict(trade_context or {}) if isinstance(trade_context, Mapping) else {}
    gate = check_paper_trade(
        "BUY", ticker=symbol, source=gate_context.get("source") or "trading_engine.paper_buy_instrument",
        run_id=gate_context.get("run_id") or gate_context.get("execution_id") or "",
        candidate=gate_context.get("candidate") if isinstance(gate_context.get("candidate"), Mapping) else None,
        automatic=bool(gate_context.get("automatic")),
    )
    if not gate.allowed:
        return False, explain_blocked_action([gate.message], action="Kjøp")
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
    manual_override_state = normalize_manual_override_state(manual_override)
    if manual_override_state == "FORCE_BLOCK":
        msg = "Manuell overstyring: FORCE_BLOCK - kjøp stoppet eksplisitt."
        audit_state_transition("paper_instrument_buy_blocked", before, detail={"symbol": symbol, "reason": "manual_force_block", "manual_override": manual_override_state, "message": msg}, level="WARNING")
        return False, explain_blocked_action([msg], action="Kjøp")
    if manual_override_state == "REVIEW_ONLY":
        msg = "Manuell overstyring: REVIEW_ONLY - kjøp er ikke gjennomført. Instrumentet skal legges i Gule flagg / Manuell vurdering."
        audit_state_transition("paper_instrument_buy_review_only", before, detail={"symbol": symbol, "reason": "manual_review_only", "manual_override": manual_override_state, "message": msg}, level="INFO")
        return False, msg
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
        audit_state_transition("paper_instrument_buy_blocked", before, detail={"symbol": symbol, "amount": round(float(amount or 0), 2), "reason": msg, "manual_override": manual_override_state}, level="WARNING")
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
        existing_trailing_pct = position_trailing_stop_pct_v18674d(existing, load_rules())
        existing_high = max(float(existing.get("highest_price", price) or price), price)
        existing_sl, existing_tp, existing_tr = calc_levels(new_avg, existing_high, trailing_stop_pct=existing_trailing_pct)
        existing.update({
            "ticker": symbol,
            "shares": new_units,
            "entry_price": round(new_avg, 6),
            "avg_price": round(new_avg, 6),
            "last_price": price,
            "highest_price": existing_high,
            "stop_loss": 0 if asset_type in FUND_ASSET_TYPES else existing_sl,
            "take_profit": 0 if asset_type in FUND_ASSET_TYPES else existing_tp,
            "trailing_stop": 0 if asset_type in FUND_ASSET_TYPES else existing_tr,
            "trailing_stop_level": 0 if asset_type in FUND_ASSET_TYPES else existing_tr,
            "trailing_stop_pct": 0 if asset_type in FUND_ASSET_TYPES else existing_trailing_pct,
            "asset_type": asset_type,
            "units_label": units_label,
            "currency": currency,
            "nav_date": nav_date or existing.get("nav_date", ""),
            "purchase_mode": purchase_mode,
            "confidence": int(confidence or existing.get("confidence", 0) or 0),
            "reason": reason,
        })
    else:
        trailing_pct_for_position = 0.0 if asset_type in FUND_ASSET_TYPES else float(load_rules().get("trailing_stop_pct", TRAILING_STOP_PCT) or TRAILING_STOP_PCT)
        sl, tp, tr = calc_levels(price, price, trailing_stop_pct=trailing_pct_for_position)
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
            "trailing_stop_level": 0 if asset_type in FUND_ASSET_TYPES else tr,
            "trailing_stop_pct": trailing_pct_for_position,
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
        "manual_override": manual_override_state,
        "manual_override_note": _manual_override_note(manual_override_state),
        "trailing_stop_pct": trailing_pct_for_position if 'trailing_pct_for_position' in locals() else position_trailing_stop_pct_v18674d(positions.get(symbol, {}), load_rules()),
        "currency": currency,
        "nav_date": nav_date,
        "order_kind": "amount_buy",
    })
    after = build_paper_state_snapshot(portfolio)
    audit_state_transition("paper_instrument_buy_executed", before, after, {"symbol": symbol, "asset_type": asset_type, "amount": round(amount, 2), "price": round(price, 6), "currency": currency, "purchase_mode": purchase_mode})
    record_paper_trade("BUY", ticker=symbol, run_id=gate.run_id)
    notify_executed_trade("BUY", symbol, price, shares=units, amount=amount, confidence=confidence, reason=reason)
    return True, f"KJØP {asset_type} {symbol}: {amount:.2f} {currency} @ {price:.4f}"


def paper_sell_instrument(symbol, price, sell_amount=None, reason="Manuelt paper-salg", currency="NOK", nav_date="", trade_context=None):
    """Sell all or part of a paper-trading instrument by amount.

    If sell_amount is None, the whole position is sold. If sell_amount is lower
    than current value, only a proportional number of units is sold.
    """
    gate_context = dict(trade_context or {}) if isinstance(trade_context, Mapping) else {}
    gate = check_paper_trade(
        "SELL", ticker=symbol, source=gate_context.get("source") or "trading_engine.paper_sell_instrument",
        run_id=gate_context.get("run_id") or gate_context.get("execution_id") or "",
        candidate=gate_context.get("candidate") if isinstance(gate_context.get("candidate"), Mapping) else None,
        automatic=bool(gate_context.get("automatic")),
    )
    if not gate.allowed:
        return False, explain_blocked_action([gate.message], action="Salg")
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
    record_paper_trade("SELL", ticker=symbol, run_id=gate.run_id)
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
