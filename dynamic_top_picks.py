
from signal_engine import score_signal

def rank_candidates(items, technical_context_by_ticker=None):
    technical_context_by_ticker = technical_context_by_ticker or {}
    ranked = []
    for item in items:
        ticker = item.get("ticker")
        decision = score_signal(item, technical_context_by_ticker.get(ticker, {}))
        enriched = dict(item)
        enriched.update({
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "decision_score": decision["final_score"],
            "reasons": decision["reasons"],
            "warnings": decision["warnings"],
        })
        ranked.append(enriched)
    return sorted(ranked, key=lambda x: x.get("decision_score", 0), reverse=True)
