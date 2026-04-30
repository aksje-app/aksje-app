
from trading_engine import auto_trade
from paper_store import load_portfolio, storage_status

# Auto SELL Engine v3.
# TEST_SIGNALS demonstrerer:
# - AAPL BUY hvis den ikke eies
# - AAPL SELL via take-profit hvis den eies og prisen settes høyt nok senere
# Juster priser midlertidig for å teste SL/TP/Trailing.
TEST_SIGNALS = [
    {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75, "rsi": None, "prev_rsi": None},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64, "rsi": None, "prev_rsi": None},
    {"ticker": "GOOGL", "price": 349.94, "signal": "HOLD", "confidence": 76, "rsi": None, "prev_rsi": None},
]


def run():
    print("=== AUTO SELL ENGINE V3 ===")
    print(f"Storage: {storage_status()}")

    trades = 0

    for item in TEST_SIGNALS:
        ok, msg = auto_trade(
            item["ticker"],
            item["price"],
            item["signal"],
            item["confidence"],
            rsi=item.get("rsi"),
            prev_rsi=item.get("prev_rsi"),
        )

        print(f"{item['ticker']}: {item['signal']} ({item['confidence']}%) price={item['price']} → {msg}")

        if ok:
            trades += 1

    p = load_portfolio()
    print(f"Cash: {p['cash']}")
    print(f"Positions: {list(p['positions'].keys())}")
    print(f"Trades this run: {trades}")


if __name__ == "__main__":
    run()
