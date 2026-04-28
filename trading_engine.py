def _num(value, default=0):
    try:
        return float(value)
    except Exception:
        return default

def build_trading_decision(item, technical_context):
    """
    Lager enkel BUY / HOLD / SELL beslutning.
    Dette er analysehjelp, ikke investeringsråd.
    """
    score = _num(item.get("score"), 5)
    rsi = _num(technical_context.get("rsi"), 50)
    macd_bullish = bool(technical_context.get("macd_bullish"))
    breakout_type = technical_context.get("breakout_type", "neutral")
    hs_found = bool(technical_context.get("head_shoulders_found"))
    inv_hs_found = bool(technical_context.get("inverse_head_shoulders_found"))
    volatility = _num(item.get("volatility"), 0.03)
    max_drawdown = _num(item.get("max_drawdown"), -0.20)

    decision_score = 0
    reasons = []

    # Grunnscore
    if score >= 7:
        decision_score += 2
        reasons.append("Sterk total score")
    elif score >= 5.5:
        decision_score += 1
        reasons.append("OK total score")
    elif score < 4:
        decision_score -= 2
        reasons.append("Svak total score")

    # MACD
    if macd_bullish:
        decision_score += 1
        reasons.append("MACD bullish")
    else:
        decision_score -= 1
        reasons.append("MACD bearish")

    # RSI
    if rsi < 30:
        decision_score += 1
        reasons.append("RSI oversolgt")
    elif rsi > 75:
        decision_score -= 2
        reasons.append("RSI svært overkjøpt")
    elif rsi > 70:
        decision_score -= 1
        reasons.append("RSI overkjøpt")

    # Breakout
    if breakout_type == "bullish":
        decision_score += 2
        reasons.append("Bullish breakout")
    elif breakout_type == "bearish":
        decision_score -= 2
        reasons.append("Bearish breakdown")

    # Patterns
    if hs_found:
        decision_score -= 3
        reasons.append("Mulig hode/skulder bearish pattern")
    if inv_hs_found:
        decision_score += 3
        reasons.append("Mulig invertert hode/skulder bullish pattern")

    # Risiko
    if volatility > 0.04:
        decision_score -= 1
        reasons.append("Høy volatilitet")
    if max_drawdown < -0.35:
        decision_score -= 1
        reasons.append("Stor historisk drawdown")

    # Beslutning
    if decision_score >= 4:
        decision = "BUY"
        color = "green"
        emoji = "🟢"
    elif decision_score <= -3:
        decision = "SELL / AVOID"
        color = "red"
        emoji = "🔴"
    else:
        decision = "HOLD / WAIT"
        color = "orange"
        emoji = "🟡"

    confidence = min(100, max(0, 50 + decision_score * 10))

    return {
        "decision": decision,
        "decision_score": decision_score,
        "confidence": confidence,
        "color": color,
        "emoji": emoji,
        "reasons": reasons,
    }

def adjusted_score(item, decision):
    """
    Justerer visuell score litt basert på trading signal.
    Endrer ikke original score i datasettet.
    """
    base = _num(item.get("score"), 5)
    ds = _num(decision.get("decision_score"), 0)
    adj = base + ds * 0.25
    return round(max(1, min(10, adj)), 2)
