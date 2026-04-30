from trading_engine import auto_trade

TEST_SIGNALS = [
    {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64},
    {"ticker": "GOOGL", "price": 349.94, "signal": "HOLD", "confidence": 76},
]

def run():
    print("=== AUTO TRADING RUN ===")

    for item in TEST_SIGNALS:
        ok, msg = auto_trade(
            item["ticker"],
            item["price"],
            item["signal"],
            item["confidence"],
        )

        print(f"{item['ticker']}: {item['signal']} ({item['confidence']}%) → {msg}")

if __name__ == "__main__":
    run()