"""Read-only triage for notification relevance.

Shadow mode: never blocks deliveries. Results help measure noise before
changing any production notification policy.
"""
from collections import Counter

CRITICAL_MARKERS = ("STOP TRIGGERED", "SHADOW SELL", "RISIKO", "FEIL", "ERROR", "FULL STOP")

def classify(event):
    side = str(event.get("side") or "").upper()
    title = str(event.get("title") or "").upper()
    combined = side + " " + title
    if any(marker in combined for marker in CRITICAL_MARKERS):
        return {"bucket": "critical", "reason": "Risiko- eller stoppmelding; skal ikke filtreres"}
    challenger = event.get("challenger") or {}
    gain = challenger.get("rank_gain")
    rank = challenger.get("rank")
    trend = event.get("short_trend") or {}
    if isinstance(gain, int) and gain >= 10 and isinstance(rank, int) and rank <= 15:
        if (trend.get("last_1_sessions_pct") or 0) > 0:
            return {"bucket": "interesting", "reason": "Markant fremgang til høy rangering med positiv kort trend"}
        return {"bucket": "daily", "reason": "Kraftig rangeringoppgang, men kort trend er ikke positiv"}
    if challenger and isinstance(rank, int) and rank <= 5:
        return {"bucket": "interesting", "reason": "Blant de fem høyest rangerte"}
    return {"bucket": "daily", "reason": "Ingen dokumentert vesentlig endring; egnet for oppsummering"}

def summarize(events):
    rows = [{"id": str(event.get("id") or ""), **classify(event)} for event in events]
    return {"shadow_only": True, "counts": dict(Counter(r["bucket"] for r in rows)), "rows": rows}
