
def _num(value, default=0):
    try:
        return float(value) if value is not None else default
    except Exception:
        return default

def calculate_signal_intelligence(item, technical_context=None, insider=None, analyst=None, earnings=None):
    technical_context = technical_context or {}
    base_score = _num(item.get("score"), 5)
    bonus = 0.0
    risk = 0.0
    reasons = []

    if technical_context.get("macd_bullish"):
        bonus += 0.4
        reasons.append("MACD bullish")
    else:
        risk += 0.3
        reasons.append("MACD bearish")

    rsi = _num(technical_context.get("rsi"), 50)
    if rsi < 30:
        bonus += 0.4
        reasons.append("RSI oversolgt")
    elif rsi > 75:
        risk += 0.9
        reasons.append("RSI svært overkjøpt")
    elif rsi > 70:
        risk += 0.5
        reasons.append("RSI overkjøpt")

    breakout_type = technical_context.get("breakout_type", "neutral")
    if breakout_type == "bullish":
        bonus += 0.8
        reasons.append("Bullish breakout")
    elif breakout_type == "bearish":
        risk += 0.8
        reasons.append("Bearish breakdown")

    if technical_context.get("head_shoulders_found"):
        risk += 1.2
        reasons.append("Bearish hode/skulder")
    if technical_context.get("inverse_head_shoulders_found"):
        bonus += 1.0
        reasons.append("Bullish invertert hode/skulder")

    if insider:
        insider_score = _num(insider.get("score"), 0.5)
        if insider_score >= 0.7:
            bonus += 0.8
            reasons.append("Positiv innsidehandel")
        elif insider_score <= 0.3:
            risk += 0.8
            reasons.append("Negativ innsidehandel")
        elif insider_score < 0.45:
            risk += 0.3
            reasons.append("Litt negativ innsidehandel")

    if analyst:
        analyst_score = _num(analyst.get("score"), 0.5)
        if analyst_score >= 0.65:
            bonus += 0.5
            reasons.append("Positiv analytikertrend")
        elif analyst_score <= 0.35:
            risk += 0.5
            reasons.append("Negativ analytikertrend")

    if earnings:
        days = earnings.get("days_until")
        if days is not None:
            days = int(days)
            if 0 <= days <= 3:
                risk += 1.2
                reasons.append("Resultatdato svært nær")
            elif 4 <= days <= 10:
                risk += 0.7
                reasons.append("Resultatdato nær")
            elif 11 <= days <= 20:
                risk += 0.2
                reasons.append("Resultatdato om kort tid")

    volatility = _num(item.get("volatility"), 0.03)
    max_drawdown = _num(item.get("max_drawdown"), 0)

    if volatility > 0.055:
        risk += 0.9
        reasons.append("Svært høy volatilitet")
    elif volatility > 0.04:
        risk += 0.4
        reasons.append("Høy volatilitet")

    if max_drawdown < -0.45:
        risk += 1.0
        reasons.append("Svært stor drawdown")
    elif max_drawdown < -0.30:
        risk += 0.5
        reasons.append("Stor drawdown")

    final_score = max(1, min(10, base_score + bonus - risk))

    if final_score >= 7.5 and risk < 1.8:
        decision, emoji = "BUY", "🟢"
    elif final_score <= 4.5 or risk >= 2.5:
        decision, emoji = "SELL / AVOID", "🔴"
    else:
        decision, emoji = "HOLD / WAIT", "🟡"

    confidence = int(max(0, min(100, 50 + (final_score - 5) * 10 + bonus * 5 - risk * 5)))

    return {
        "final_score": round(final_score, 2),
        "base_score": round(base_score, 2),
        "bonus": round(bonus, 2),
        "risk": round(risk, 2),
        "decision": decision,
        "emoji": emoji,
        "confidence": confidence,
        "reasons": reasons,
    }
