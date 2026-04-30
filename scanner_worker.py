
from trading_engine import auto_trade
from paper_store import load_portfolio
import os

# Enkel stabil test-scanner.
# Neste steg blir å koble denne mot ekte signalmotoren igjen.

TEST_SIGNALS = [
    {"ticker": "GOOGL", "price": 349.94, "signal": "BUY", "confidence": 76},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64},
    {"ticker": "AAPL", "price": 190.10, "signal": "HOLD", "confidence": 62},
]


def run():
    print("=== Trading Engine v1 scanner ===")

    trades = 0

    for item in TEST_SIGNALS:
        ok, msg = auto_trade(
            item["ticker"],
            item["price"],
            item["signal"],
            item["confidence"],
        )

        print(f"{item['ticker']}: {item['signal']} conf={item['confidence']} -> {msg}")

        if ok:
            trades += 1

    p = load_portfolio()
    print(f"Cash: {p['cash']}")
    print(f"Positions: {list(p['positions'].keys())}")
    print(f"Trades this run: {trades}")


if __name__ == "__main__":
    run()
