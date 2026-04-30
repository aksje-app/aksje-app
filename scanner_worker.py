
from trading_engine import auto_trade
from paper_store import load_portfolio, storage_status
from top10_engine import get_all_signals

def run():
    print("=== AUTO TRADING V4 PRO ===")
    print(f"Storage: {storage_status()}")

    trades = 0
    signals = get_all_signals()

    for item in signals:
        ok, msg = auto_trade(
            item["ticker"],
            item["price"],
            item["signal"],
            item["confidence"],
            rsi=item.get("rsi"),
            prev_rsi=item.get("prev_rsi"),
        )

        print(
            f"{item['ticker']}: {item['signal']} "
            f"score={item['score']} conf={item['confidence']} "
            f"price={item['price']} → {msg}"
        )

        if ok:
            trades += 1

    p = load_portfolio()
    print(f"Cash: {p['cash']}")
    print(f"Positions: {list(p['positions'].keys())}")
    print(f"Trades this run: {trades}")

if __name__ == "__main__":
    run()
