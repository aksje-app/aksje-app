
def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def classify_rsi(rsi):
    rsi = _safe_float(rsi, 50)
    if rsi >= 78:
        return "bearish", "RSI er ekstremt høy / overkjøpt"
    if rsi >= 70:
        return "warning", "RSI er overkjøpt"
    if rsi <= 30:
        return "bullish", "RSI er lav / oversolgt"
    if 45 <= rsi <= 65:
        return "bullish", "RSI er i sunn sone"
    return "neutral", "RSI er nøytral"


def score_signal(item, technical_context=None, insider=None, analyst=None, earnings=None):
    """
    Pro signalmotor v1.
    Returnerer:
    - final_score 0-10
    - decision
    - confidence
    - reasons
    - warnings
    """
    technical_context = technical_context or {}
    reasons = []
    warnings = []

    base_score = _safe_float(item.get("score", 0) if isinstance(item, dict) else 0)
    score = base_score

    rsi = _safe_float(technical_context.get("rsi", 50), 50)
    rsi_class, rsi_reason = classify_rsi(rsi)

    macd_bullish = bool(technical_context.get("macd_bullish", False))
    breakout_type = str(technical_context.get("breakout_type", "neutral")).lower()
    head_shoulders = bool(technical_context.get("head_shoulders_found", False))
    inverse_hs = bool(technical_context.get("inverse_head_shoulders_found", False))

    # RSI logic
    if rsi_class == "bullish":
        score += 0.5
        reasons.append(rsi_reason)
    elif rsi_class == "warning":
        score -= 0.8
        warnings.append(rsi_reason)
    elif rsi_class == "bearish":
        score -= 1.4
        warnings.append(rsi_reason)
    else:
        reasons.append(rsi_reason)

    # MACD
    if macd_bullish:
        score += 0.55
        reasons.append("MACD er bullish")
    else:
        score -= 0.25
        warnings.append("MACD er ikke bullish")

    # Breakout
    if breakout_type in ["bullish", "breakout", "up"]:
        score += 0.75
        reasons.append("Bullish breakout / brudd opp")
    elif breakout_type in ["bearish", "breakdown", "down"]:
        score -= 1.0
        warnings.append("Bearish breakout / brudd ned")

    # Patterns
    if inverse_hs:
        score += 0.45
        reasons.append("Inverse head & shoulders støtter oppside")
    if head_shoulders:
        score -= 0.8
        warnings.append("Head & shoulders advarer om nedside")

    # Optional public data signals
    if analyst:
        trend = str(analyst.get("trend", "")).lower() if isinstance(analyst, dict) else ""
        if "positive" in trend or "up" in trend:
            score += 0.25
            reasons.append("Analytikertrend støtter signalet")
        elif "negative" in trend or "down" in trend:
            score -= 0.25
            warnings.append("Analytikertrend er svak")

    if earnings:
        surprise = _safe_float(earnings.get("surprise", 0), 0) if isinstance(earnings, dict) else 0
        if surprise > 0:
            score += 0.2
            reasons.append("Earnings overrasket positivt")
        elif surprise < 0:
            score -= 0.2
            warnings.append("Earnings overrasket negativt")

    score = max(0.0, min(10.0, score))
    confidence = int(max(35, min(95, round(score * 10))))

    # Conservative decisions
    if score >= 7.2 and rsi < 70 and (macd_bullish or breakout_type in ["bullish", "breakout", "up"]):
        decision = "BUY"
        emoji = "🟢"
    elif score <= 4.2 or rsi >= 78 or breakout_type in ["bearish", "breakdown", "down"] or head_shoulders:
        decision = "SELL / AVOID"
        emoji = "🔴"
    else:
        decision = "HOLD / WAIT"
        emoji = "🟡"

    if decision == "BUY" and not reasons:
        reasons.append("Samlet score er sterk nok for BUY")

    if decision != "BUY" and not warnings:
        warnings.append("Mangler nok teknisk bekreftelse for BUY")

    return {
        "final_score": round(score, 2),
        "decision_score": round(score, 2),
        "decision": decision,
        "emoji": emoji,
        "confidence": confidence,
        "reasons": reasons[:6],
        "warnings": warnings[:6],
        "rsi": round(rsi, 1),
        "macd_bullish": macd_bullish,
        "breakout_type": breakout_type,
        "bonus": round(score - base_score, 2),
    }


def calculate_signal_intelligence(item, technical_context=None, insider=None, analyst=None, earnings=None):
    """
    Backwards-compatible function used by app13.
    """
    return score_signal(item, technical_context, insider, analyst, earnings)


def explain_decision(decision):
    reasons = decision.get("reasons", []) if isinstance(decision, dict) else []
    warnings = decision.get("warnings", []) if isinstance(decision, dict) else []
    return reasons, warnings
