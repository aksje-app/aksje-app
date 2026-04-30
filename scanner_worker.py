
from trading_engine import auto_trade
from paper_store import load_portfolio, storage_status

TEST_SIGNALS = [
    {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64},
    {"ticker": "GOOGL", "price": 349.94, "signal": "HOLD", "confidence": 76},
]

def run():
    print("=== AUTO TRADING ENGINE V2 ===")
    print(f"Storage: {storage_status()}")
    trades = 0
    for item in TEST_SIGNALS:
        ok, msg = auto_trade(item["ticker"], item["price"], item["signal"], item["confidence"])
        print(f"{item['ticker']}: {item['signal']} ({item['confidence']}%) → {msg}")
        if ok:
            trades += 1
    p = load_portfolio()
    print(f"Cash: {p['cash']}")
    print(f"Positions: {list(p['positions'].keys())}")
    print(f"Trades this run: {trades}")

if __name__ == "__main__":
    run()
