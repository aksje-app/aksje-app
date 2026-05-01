
"""
Signal Engine - Full Prod Advanced

Alltid stabile nøkler:
score, final_score, decision_score, confidence, bonus, risk, risk_score,
decision, emoji, reasons, warnings, rsi, macd_bullish, breakout_type,
trend, channel_pos.

Brukes av både UI og Cron.
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
    return item.get(key, default) if isinstance(item, dict) else default

def _risk_label(score):
    if score >= 70:
        return "Høy"
    if score >= 40:
        return "Middels"
    return "Lav"

def score_signal(item, technical_context=None, insider=None, analyst=None, earnings=None):
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
    momentum = _safe_float(technical_context.get("momentum", _get(item, "momentum", 0)), 0)
    volatility = _safe_float(technical_context.get("volatility", _get(item, "volatility", 0)), 0)
    volume_confirmed = bool(technical_context.get("volume_confirmed", _get(item, "volume_confirmed", False)))

    head_shoulders = bool(technical_context.get("head_shoulders_found", False))
    inverse_hs = bool(technical_context.get("inverse_head_shoulders_found", False))

    # RSI
    if rsi >= 80:
        score -= 1.3; risk_score += 28; warnings.append("RSI er ekstremt overkjøpt")
    elif rsi >= 70:
        score -= 0.8; risk_score += 18; warnings.append("RSI er overkjøpt")
    elif rsi <= 30:
        score += 0.45; reasons.append("RSI er lav / mulig oversolgt")
    elif 45 <= rsi <= 65:
        score += 0.35; reasons.append("RSI er i sunn sone")

    # Trend
    if trend in ["up", "opp", "bullish", "positive"]:
        score += 0.7; reasons.append("Trend peker opp")
    elif trend in ["down", "ned", "bearish", "negative"]:
        score -= 0.9; risk_score += 22; warnings.append("Trend peker ned")

    # MACD
    if macd_bullish:
        score += 0.5; reasons.append("MACD støtter oppside")
    else:
        score -= 0.15; warnings.append("MACD gir ikke tydelig støtte")

    # Breakout
    if breakout_type in ["bullish", "breakout", "up"]:
        score += 0.8; reasons.append("Bullish breakout / brudd opp")
    elif breakout_type in ["bearish", "breakdown", "down"]:
        score -= 1.1; risk_score += 28; warnings.append("Bearish brudd / svak teknisk struktur")

    # Channel
    if channel_pos >= 85:
        score -= 0.55; risk_score += 16; warnings.append("Kursen ligger høyt i trendkanalen")
    elif channel_pos <= 25:
        score += 0.3; reasons.append("Kursen ligger lavt/moderat i trendkanalen")
    else:
        reasons.append("Kursen ligger ikke ekstremt i kanalen")

    # Momentum / volatility / volume
    if momentum > 0:
        score += min(0.45, momentum / 10); reasons.append("Momentum er positivt")
    elif momentum < 0:
        score -= min(0.45, abs(momentum) / 10); warnings.append("Momentum er svakt")

    if volatility > 8:
        risk_score += 15; warnings.append("Volatilitet er høy")
    elif 0 < volatility < 4:
        score += 0.15; reasons.append("Volatilitet er kontrollert")

    if volume_confirmed:
        score += 0.25; reasons.append("Volum bekrefter signalet")

    # Patterns
    if inverse_hs:
        score += 0.45; reasons.append("Bullish mønster støtter oppside")
    if head_shoulders:
        score -= 0.85; risk_score += 25; warnings.append("Bearish mønster øker risiko")

    # Optional public data
    if isinstance(analyst, dict):
        t = str(analyst.get("trend", "")).lower()
        if "positive" in t or "up" in t:
            score += 0.25; reasons.append("Analytikertrend støtter aksjen")
        elif "negative" in t or "down" in t:
            score -= 0.25; warnings.append("Analytikertrend er svak")

    if isinstance(earnings, dict):
        surprise = _safe_float(earnings.get("surprise", 0), 0)
        if surprise > 0:
            score += 0.2; reasons.append("Resultater overrasket positivt")
        elif surprise < 0:
            score -= 0.2; warnings.append("Resultater overrasket negativt")

    score = round(_clamp(score, 0, 10), 2)
    bonus = round(score - base_score, 2)
    risk_score = int(_clamp(risk_score, 0, 100))
    risk = _risk_label(risk_score)
    confidence = int(_clamp(round(score * 10), 35, 95))

    # Advanced conservative decision
    buy_confirmed = (macd_bullish or breakout_type in ["bullish", "breakout", "up"] or trend in ["up", "opp", "bullish", "positive"])
    if score >= 7.2 and risk != "Høy" and rsi < 70 and buy_confirmed:
        decision = "BUY"; emoji = "🟢"
    elif score <= 4.2 or risk == "Høy" or rsi >= 80 or breakout_type in ["bearish", "breakdown", "down"]:
        decision = "SELL / AVOID"; emoji = "🔴"
    else:
        decision = "HOLD / WAIT"; emoji = "🟡"

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

def build_trading_decision(item, technical_context=None):
    return score_signal(item, technical_context or {})

def adjusted_score(base_score, technical_context=None, news_sentiment=None):
    return score_signal({"score": base_score}, technical_context or {}).get("final_score", base_score)

def explain_decision(decision):
    if not isinstance(decision, dict):
        return [], []
    return decision.get("reasons", []), decision.get("warnings", [])
