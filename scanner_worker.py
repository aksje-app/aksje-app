
def run():
    tickers = ["AAPL", "MSFT", "GOOGL"]

    for t in tickers:
        signal = "BUY"
        confidence = 70

        if confidence >= 60:
            print(f"{t}: {signal} ({confidence}%)")

if __name__ == "__main__":
    run()
