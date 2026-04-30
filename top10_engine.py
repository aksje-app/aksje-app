
# Enkel stabil Top10-motor. Senere kobles denne mot ekte analyse/ranking.
TOP10_DATA = {
    "USA": [
        {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75, "score": 7.5},
        {"ticker": "GOOGL", "price": 349.94, "signal": "BUY", "confidence": 76, "score": 7.67},
        {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64, "score": 6.4},
        {"ticker": "NVDA", "price": 210.93, "signal": "HOLD", "confidence": 63, "score": 6.3},
        {"ticker": "AMZN", "price": 258.77, "signal": "HOLD", "confidence": 61, "score": 6.1},
    ],
    "NORGE": [
        {"ticker": "YAR.OL", "price": 531.60, "signal": "BUY", "confidence": 72, "score": 7.1},
        {"ticker": "EQNR.OL", "price": 369.00, "signal": "HOLD", "confidence": 66, "score": 6.6},
        {"ticker": "NHY.OL", "price": 101.80, "signal": "BUY", "confidence": 80, "score": 8.0},
        {"ticker": "ORK.OL", "price": 113.70, "signal": "HOLD", "confidence": 43, "score": 4.3},
        {"ticker": "AKRBP.OL", "price": 342.40, "signal": "HOLD", "confidence": 59, "score": 5.9},
    ],
    "SVERIGE": [
        {"ticker": "VOLV-B.ST", "price": 319.10, "signal": "HOLD", "confidence": 73, "score": 7.3},
        {"ticker": "ERIC-B.ST", "price": 108.35, "signal": "HOLD", "confidence": 62, "score": 6.2},
        {"ticker": "HM-B.ST", "price": 164.60, "signal": "SELL", "confidence": 38, "score": 3.8},
        {"ticker": "ATCO-A.ST", "price": 174.20, "signal": "HOLD", "confidence": 60, "score": 6.0},
        {"ticker": "ATCO-B.ST", "price": 154.85, "signal": "HOLD", "confidence": 46, "score": 4.6},
    ],
}

def get_top10(market="ALLE"):
    market = str(market).upper()
    if market in TOP10_DATA:
        return sorted(TOP10_DATA[market], key=lambda x: x["score"], reverse=True)[:10]

    all_items = []
    for items in TOP10_DATA.values():
        all_items.extend(items)
    return sorted(all_items, key=lambda x: x["score"], reverse=True)[:10]

def get_all_signals():
    return get_top10("ALLE")
