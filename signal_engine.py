
"""
Smart Core v2

Én felles beslutningsmotor for:
- score
- confidence
- bonus
- risk
- reasons
- warnings
- BUY / HOLD / SELL

Mål:
UI skal aldri krasje på manglende keys.
Alle kall returnerer samme stabile dictionary.
"""

def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value, low, high):
    return max(low, min(high, value))


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return default


def _risk_label(risk_score):
    if risk_score >= 70:
        return "Høy"
    if risk_score >= 40:
        return "Middels"
    return "Lav"


def score_signal(item, technical_context=None, insider=None, analyst=None, earnings=None):
    """
    Returnerer ALLTID disse feltene:
    score, final_score, decision_score, confidence, bonus, risk, risk_score,
    decision, emoji, reasons, warnings, rsi, macd_bullish, breakout_type.
    """
    technical_context = technical_context or {}
    reasons = []
    warnings = []

    base_score = _safe_float(_get(item, "score", 5.0), 5.0)
    score = base_score
    risk_score = 25

    rsi = _safe_float(technical_context.get("rsi", _get(item, "rsi", 50)), 50)
    macd_bullish = bool(technical_context.get("macd_bullish", _get(item, "macd_bullish", False)))
    breakout_type = str(technical_context.get("breakout_type", _get(item, "breakout_type", "neutral"))).lower()
    trend = str(technical_context.get("trend", _get(item, "trend", "neutral"))).lower()
    channel_pos = _safe_float(technical_context.get("channel_pos", _get(item, "channel_pos", 50)), 50)

    head_shoulders = bool(technical_context.get("head_shoulders_found", False))
    inverse_hs = bool(technical_context.get("inverse_head_shoulders_found", False))

    # RSI
    if rsi >= 80:
        score -= 1.2
        risk_score += 25
        warnings.append("RSI er ekstremt overkjøpt")
    elif rsi >= 70:
        score -= 0.7
        risk_score += 15
        warnings.append("RSI er overkjøpt")
    elif rsi <= 30:
        score += 0.5
        reasons.append("RSI er lav / mulig oversolgt")
    elif 45 <= rsi <= 65:
        score += 0.35
        reasons.append("RSI er i sunn sone")

    # Trend
    if trend in ["up", "opp", "bullish", "positive"]:
        score += 0.6
        reasons.append("Trend peker opp")
    elif trend in ["down", "ned", "bearish", "negative"]:
        score -= 0.8
        risk_score += 20
        warnings.append("Trend peker ned")

    # MACD
    if macd_bullish:
        score += 0.45
        reasons.append("MACD støtter oppside")
    else:
        score -= 0.15
        warnings.append("MACD gir ikke tydelig støtte")

    # Breakout
    if breakout_type in ["bullish", "breakout", "up"]:
        score += 0.7
        reasons.append("Bullish breakout / brudd opp")
    elif breakout_type in ["bearish", "breakdown", "down"]:
        score -= 1.0
        risk_score += 25
        warnings.append("Bearish brudd / svak teknisk struktur")

    # Trendkanal-posisjon
    if channel_pos >= 85:
        score -= 0.5
        risk_score += 15
        warnings.append("Kursen ligger høyt i trendkanalen")
    elif channel_pos <= 25:
        score += 0.25
        reasons.append("Kursen ligger lavt/moderat i trendkanalen")
    else:
        reasons.append("Kursen ligger ikke ekstremt i kanalen")

    # Patterns
    if inverse_hs:
        score += 0.4
        reasons.append("Bullish mønster støtter oppside")
    if head_shoulders:
        score -= 0.8
        risk_score += 25
        warnings.append("Bearish mønster øker risiko")

    # Public data placeholders
    if isinstance(analyst, dict):
        analyst_trend = str(analyst.get("trend", "")).lower()
        if "positive" in analyst_trend or "up" in analyst_trend:
            score += 0.25
            reasons.append("Analytikertrend støtter aksjen")
        elif "negative" in analyst_trend or "down" in analyst_trend:
            score -= 0.25
            warnings.append("Analytikertrend er svak")

    if isinstance(earnings, dict):
        surprise = _safe_float(earnings.get("surprise", 0), 0)
        if surprise > 0:
            score += 0.2
            reasons.append("Resultater overrasket positivt")
        elif surprise < 0:
            score -= 0.2
            warnings.append("Resultater overrasket negativt")

    score = round(_clamp(score, 0, 10), 2)
    bonus = round(score - base_score, 2)
    risk_score = int(_clamp(risk_score, 0, 100))
    risk = _risk_label(risk_score)
    confidence = int(_clamp(round(score * 10), 35, 95))

    # Conservative decision rules
    if score >= 7.2 and risk != "Høy" and rsi < 70 and (macd_bullish or breakout_type in ["bullish", "breakout", "up"]):
        decision = "BUY"
        emoji = "🟢"
    elif score <= 4.2 or risk == "Høy" or rsi >= 80 or breakout_type in ["bearish", "breakdown", "down"]:
        decision = "SELL / AVOID"
        emoji = "🔴"
    else:
        decision = "HOLD / WAIT"
        emoji = "🟡"

    if not reasons:
        reasons.append("Ingen sterk positiv bekreftelse funnet")
    if not warnings:
        warnings.append("Ingen store risikoflagg funnet")

    return {
        "score": score,
        "final_score": score,
        "decision_score": score,
        "confidence": confidence,
        "bonus": bonus,
        "risk": risk,
        "risk_score": risk_score,
        "decision": decision,
        "emoji": emoji,
        "reasons": reasons[:8],
        "warnings": warnings[:8],
        "rsi": round(rsi, 1),
        "macd_bullish": macd_bullish,
        "breakout_type": breakout_type,
        "trend": trend,
        "channel_pos": round(channel_pos, 1),
    }


def calculate_signal_intelligence(item, technical_context=None, insider=None, analyst=None, earnings=None):
    return score_signal(item, technical_context, insider, analyst, earnings)


def explain_decision(decision):
    if not isinstance(decision, dict):
        return [], []
    return decision.get("reasons", []), decision.get("warnings", [])
