
from trading_engine import auto_trade
from paper_store import load_portfolio, storage_status

SIGNALS = [
    {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75},
    {"ticker": "GOOGL", "price": 349.94, "signal": "BUY", "confidence": 76},
    {"ticker": "NHY.OL", "price": 101.80, "signal": "BUY", "confidence": 80},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64},
    {"ticker": "YAR.OL", "price": 531.60, "signal": "BUY", "confidence": 72},
]

def run():
    print("=== RECOVERY PRO SCANNER ===")
    print(f"Storage: {storage_status()}")
    trades = 0
    for item in SIGNALS:
        ok, msg = auto_trade(item["ticker"], item["price"], item["signal"], item["confidence"])
        print(f"{item['ticker']}: {item['signal']} conf={item['confidence']} price={item['price']} -> {msg}")
        if ok:
            trades += 1
    p = load_portfolio()
    print(f"Cash: {p['cash']}")
    print(f"Positions: {list(p['positions'].keys())}")
    print(f"Trades this run: {trades}")

if __name__ == "__main__":
    run()
