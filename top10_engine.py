
TOP10_DATA = {
    "USA": [
        {"ticker": "GOOGL", "price": 349.94, "signal": "BUY", "confidence": 76, "score": 7.67, "rsi": 62.4},
        {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75, "score": 7.50, "rsi": 58.2},
        {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64, "score": 6.40, "rsi": 55.7},
        {"ticker": "NVDA", "price": 210.93, "signal": "HOLD", "confidence": 63, "score": 6.30, "rsi": 68.1},
        {"ticker": "AMZN", "price": 258.77, "signal": "HOLD", "confidence": 61, "score": 6.10, "rsi": 51.9},
    ],
    "NORGE": [
        {"ticker": "NHY.OL", "price": 101.80, "signal": "BUY", "confidence": 80, "score": 8.00, "rsi": 64.2},
        {"ticker": "YAR.OL", "price": 531.60, "signal": "BUY", "confidence": 72, "score": 7.10, "rsi": 59.1},
        {"ticker": "EQNR.OL", "price": 369.00, "signal": "HOLD", "confidence": 66, "score": 6.60, "rsi": 53.8},
        {"ticker": "AKRBP.OL", "price": 342.40, "signal": "HOLD", "confidence": 59, "score": 5.90, "rsi": 48.3},
        {"ticker": "ORK.OL", "price": 113.70, "signal": "HOLD", "confidence": 43, "score": 4.30, "rsi": 45.1},
    ],
    "SVERIGE": [
        {"ticker": "VOLV-B.ST", "price": 319.10, "signal": "HOLD", "confidence": 73, "score": 7.30, "rsi": 61.4},
        {"ticker": "ERIC-B.ST", "price": 108.35, "signal": "HOLD", "confidence": 62, "score": 6.20, "rsi": 50.2},
        {"ticker": "ATCO-A.ST", "price": 174.20, "signal": "HOLD", "confidence": 60, "score": 6.00, "rsi": 54.6},
        {"ticker": "ATCO-B.ST", "price": 154.85, "signal": "HOLD", "confidence": 46, "score": 4.60, "rsi": 46.7},
        {"ticker": "HM-B.ST", "price": 164.60, "signal": "SELL", "confidence": 38, "score": 3.80, "rsi": 74.9},
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

def find_ticker(ticker):
    ticker = str(ticker).upper()
    for items in TOP10_DATA.values():
        for item in items:
            if item["ticker"].upper() == ticker:
                return item
    return None

def get_all_signals():
    return get_top10("ALLE")
