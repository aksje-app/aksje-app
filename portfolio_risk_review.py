"""Shared, non-executing risk review for existing paper/shadow holdings.

Conservative by design: missing evidence means REVIEW, never automatic SELL.
Portfolio engines retain their authoritative stop and execution policies.
"""
from math import isfinite


def _number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def review_existing_position(*, ticker, entry_price, current_price,
                             peak_price=None, score_change=None,
                             relative_return_pct=None, thesis_valid=None,
                             position_weight_pct=None, position_cap_pct=None,
                             stop_triggered=False, data_fresh=True):
    """Return advisory classification; no transaction or holdings mutation."""
    current, entry = _number(current_price), _number(entry_price)
    peak = _number(peak_price)
    weight, cap = _number(position_weight_pct), _number(position_cap_pct)
    score_delta, relative = _number(score_change), _number(relative_return_pct)
    reasons = []
    if not data_fresh or current is None or current <= 0 or entry is None or entry <= 0:
        return {"ticker":str(ticker), "action":"OVERVAAK", "reason_codes":["MISSING_OR_STALE_PRICE"],
                "execution_authorized":False}
    loss_pct = (current / entry - 1) * 100
    drawdown_pct = (current / max(entry, peak or entry, current) - 1) * 100
    if stop_triggered:
        action = "SELG"
        reasons.append("EXISTING_STOP_TRIGGERED")
    elif thesis_valid is False and (loss_pct < 0 or (score_delta is not None and score_delta < 0)):
        action = "REDUSER"
        reasons.append("THESIS_INVALID_WITH_WEAKNESS")
    elif weight is not None and cap is not None and cap > 0 and weight > cap:
        action = "REDUSER"
        reasons.append("ABOVE_POSITION_CAP")
    elif thesis_valid is None or score_delta is None or relative is None:
        action = "OVERVAAK"
        reasons.append("INCOMPLETE_RISK_EVIDENCE")
    elif loss_pct <= -0.8 and (score_delta < 0 or relative < 0):
        action = "OVERVAAK"
        reasons.append("EARLY_LOSS_AND_WEAK_SIGNAL")
    elif drawdown_pct <= -1.5 and (score_delta < 0 or relative < 0):
        action = "OVERVAAK"
        reasons.append("PEAK_DRAWDOWN_AND_WEAK_SIGNAL")
    else:
        action = "BEHOLD"
        reasons.append("NO_NEW_RISK_TRIGGER")
    return {"ticker":str(ticker), "action":action, "reason_codes":reasons,
            "loss_pct":round(loss_pct,3), "drawdown_pct":round(drawdown_pct,3),
            "execution_authorized":False}


def review_portfolio(engine, positions, evidence_by_ticker):
    """Shared interface for all three engines; evidence must be explicit."""
    from staged_entries import SUPPORTED_ENGINES
    if engine not in SUPPORTED_ENGINES:
        raise ValueError("Unknown portfolio engine")
    result = []
    for ticker, position in (positions or {}).items():
        evidence = (evidence_by_ticker or {}).get(ticker, {})
        result.append(review_existing_position(
            ticker=ticker, entry_price=position.get("entry_price"),
            current_price=evidence.get("current_price", position.get("last_price")),
            peak_price=position.get("peak_price"),
            score_change=evidence.get("score_change"),
            relative_return_pct=evidence.get("relative_return_pct"),
            thesis_valid=evidence.get("thesis_valid"),
            position_weight_pct=evidence.get("position_weight_pct"),
            position_cap_pct=evidence.get("position_cap_pct"),
            stop_triggered=bool(evidence.get("stop_triggered")),
            data_fresh=bool(evidence.get("data_fresh",False)),
        ))
    return result


def review_super_portfolio_state(state, *, evidence_by_ticker=None):
    """Normalize existing Super Portfolio Shadow positions for advisory review."""
    positions = (state or {}).get("positions") or {}
    cfg = (state or {}).get("config") or {}
    cap = cfg.get("max_position_pct", 15.0)
    normalized = {}
    evidence = {}
    for ticker, position in positions.items():
        normalized[ticker] = {
            "entry_price": position.get("entry_price"),
            "last_price": position.get("last_price"),
            "peak_price": position.get("peak_price"),
        }
        supplied = dict((evidence_by_ticker or {}).get(ticker) or {})
        supplied.setdefault("position_weight_pct", position.get("target_weight_pct"))
        supplied.setdefault("position_cap_pct", cap)
        evidence[ticker] = supplied
    return review_portfolio("super_portfolio", normalized, evidence)


def review_autonomi_state(portfolio, *, evidence_by_ticker=None, position_cap_pct=None):
    """Normalize existing Autonomi theoretical positions; missing evidence stays unknown."""
    normalized = {}
    evidence = {}
    for ticker, position in ((portfolio or {}).get("positions") or {}).items():
        normalized[ticker] = {
            "entry_price": position.get("average_price"),
            "last_price": position.get("last_price"),
            "peak_price": position.get("highest_price"),
        }
        supplied = dict((evidence_by_ticker or {}).get(ticker) or {})
        if position_cap_pct is not None:
            supplied.setdefault("position_cap_pct", position_cap_pct)
        evidence[ticker] = supplied
    return review_portfolio("autonomi", normalized, evidence)


def review_superfond_state(state, *, evidence_by_id=None, position_cap_pct=None):
    """Normalize existing Superfond model holdings denominated in NOK."""
    normalized = {}
    evidence = {}
    s = state or {}
    equity = float(s.get("cash") or 0) + sum(
        float(p.get("quantity") or 0) * float(p.get("last_nok") or 0)
        for p in (s.get("positions") or {}).values()
    )
    for fund_id, position in (s.get("positions") or {}).items():
        normalized[fund_id] = {
            "entry_price": position.get("entry_nok"),
            "last_price": position.get("last_nok"),
            # No peak is assumed when historical peak is not reliably available.
            "peak_price": position.get("peak_nok"),
        }
        supplied = dict((evidence_by_id or {}).get(fund_id) or {})
        if equity > 0:
            supplied.setdefault("position_weight_pct",
                100 * float(position.get("quantity") or 0) * float(position.get("last_nok") or 0) / equity)
        if position_cap_pct is not None:
            supplied.setdefault("position_cap_pct", position_cap_pct)
        evidence[fund_id] = supplied
    return review_portfolio("superfond", normalized, evidence)
