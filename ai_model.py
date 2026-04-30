
def ai_score_signal(item):
    """
    Stabil forklarbar AI-score v1.
    Dette er ikke tung ML ennå, men en modell-lignende scoring som kan byttes ut senere.
    """
    confidence = float(item.get("confidence", 0))
    score = float(item.get("score", 0))
    signal = str(item.get("signal", "HOLD")).upper()

    base = score * 10
    conf_bonus = (confidence - 50) * 0.4

    if signal == "BUY":
        signal_bonus = 10
    elif "SELL" in signal:
        signal_bonus = -15
    else:
        signal_bonus = 0

    ai_score = max(0, min(100, base + conf_bonus + signal_bonus))

    if ai_score >= 75:
        decision = "BUY"
    elif ai_score <= 40:
        decision = "SELL"
    else:
        decision = "HOLD"

    reasons = []
    if score >= 7:
        reasons.append("Høy samlet score")
    if confidence >= 70:
        reasons.append("Sterk confidence")
    if signal == "BUY":
        reasons.append("Kjøpssignal fra strategi")
    if signal == "HOLD":
        reasons.append("Avventer tydeligere bekreftelse")
    if "SELL" in signal:
        reasons.append("Negativt signal / unngå")

    return {
        "ai_score": round(ai_score, 1),
        "decision": decision,
        "reasons": reasons,
    }
