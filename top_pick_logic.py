
"""
Top Pick Logic v1

Skiller mellom:
- Top Pick: sterk aksje totalt sett
- Kjøp nå: sterk aksje + teknisk timing er OK
- Vent: sterk aksje, men dårlig timing akkurat nå
- Unngå/Selg: teknisk eller risiko sier nei
"""

def normalize_decision(decision):
    d = str(decision or "").upper()
    if "BUY" in d:
        return "BUY"
    if "SELL" in d or "AVOID" in d:
        return "SELL / AVOID"
    return "HOLD / WAIT"


def action_from_signal(signal_intelligence):
    """
    Returnerer brukerhandling for kort:
    - KJØP NÅ
    - VENT
    - SELG / UNNGÅ
    """
    si = signal_intelligence or {}
    decision = normalize_decision(si.get("decision"))
    risk = str(si.get("risk", "Middels")).lower()
    rsi = float(si.get("rsi", 50) or 50)
    score = float(si.get("final_score", si.get("score", 0)) or 0)

    if decision == "BUY" and risk != "høy" and rsi < 70 and score >= 7.2:
        return "KJØP NÅ", "buy"

    if decision == "SELL / AVOID":
        return "SELG / UNNGÅ", "sell"

    return "VENT", "wait"


def top_pick_rank_score(base_score, signal_intelligence):
    """
    Ranking som straffer dårlig teknisk timing.
    GOOGL kan fortsatt være sterk aksje, men skal falle ned hvis teknisk signal er SELL/AVOID.
    """
    si = signal_intelligence or {}
    score = float(si.get("final_score", base_score or 0) or 0)
    decision = normalize_decision(si.get("decision"))
    risk = str(si.get("risk", "Middels")).lower()
    rsi = float(si.get("rsi", 50) or 50)

    penalty = 0.0
    bonus = 0.0

    if decision == "BUY":
        bonus += 0.6
    elif decision == "SELL / AVOID":
        penalty += 1.2
    else:
        penalty += 0.25

    if risk == "høy":
        penalty += 0.8
    elif risk == "lav":
        bonus += 0.2

    if rsi >= 80:
        penalty += 1.0
    elif rsi >= 70:
        penalty += 0.6

    return round(max(0, min(10, score + bonus - penalty)), 2)


def render_action_badges_html(signal_intelligence):
    """
    HTML badges til Top Picks-kortene.
    """
    si = signal_intelligence or {}
    score = si.get("final_score", si.get("score", 0))
    decision = normalize_decision(si.get("decision"))
    action, action_type = action_from_signal(si)

    sig_class = "tp-buy" if decision == "BUY" else "tp-sell" if "SELL" in decision else "tp-wait"
    action_class = "tp-buy" if action_type == "buy" else "tp-sell" if action_type == "sell" else "tp-wait"

    return f"""
    <div class="tp-badge-row">
        <span class="tp-badge">Score {score}/10</span>
        <span class="tp-badge {sig_class}">Signal {decision}</span>
        <span class="tp-badge {action_class}">Handling {action}</span>
    </div>
    """
