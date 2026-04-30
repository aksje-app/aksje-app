from trading_engine import auto_trade
import random

# Simulert live scanner (erstatter gammel signal_engine midlertidig)
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"
]
TEST_SIGNALS = [
    {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64},
    {"ticker": "GOOGL", "price": 349.94, "signal": "HOLD", "confidence": 76},
]

 def run():
    print("=== AUTO TRADING RUN ===")

    for ticker in TICKERS:
        price = random.uniform(100, 400)  # mock price
        signal, confidence = get_signal()

        ok, msg = auto_trade(ticker, price, signal, confidence)

        print(f"{ticker}: {signal} ({confidence}%) → {msg}")

if __name__ == "__main__":
    run()