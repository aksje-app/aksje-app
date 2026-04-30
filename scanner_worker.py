from trading_engine import auto_trade
import random

# Simulert live scanner (erstatter gammel signal_engine midlertidig)
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"
]

def get_signal():
    signals = ["BUY", "HOLD", "SELL"]
    return random.choice(signals), random.randint(55, 85)

def run():
    print("=== AUTO TRADING RUN ===")

    for ticker in TICKERS:
        price = random.uniform(100, 400)  # mock price
        signal, confidence = get_signal()

        ok, msg = auto_trade(ticker, price, signal, confidence)

        print(f"{ticker}: {signal} ({confidence}%) → {msg}")

if __name__ == "__main__":
    run()