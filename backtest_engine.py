
import math
import pandas as pd


def run_simple_backtest(prices, start_cash=100000, buy_threshold=65, sell_threshold=45):
    """
    Enkel stabil backtest:
    - lager momentum-score fra prisendring
    - kjøper når score > buy_threshold
    - selger når score < sell_threshold eller TP/SL treffes
    """
    if prices is None or len(prices) < 30:
        return {
            "final_value": start_cash,
            "return_pct": 0,
            "trades": [],
            "equity_curve": [],
            "win_rate": 0,
        }

    cash = float(start_cash)
    shares = 0.0
    entry = None
    trades = []
    equity_curve = []

    stop_loss_pct = 7
    take_profit_pct = 12

    for i in range(20, len(prices)):
        price = float(prices[i])
        prev = float(prices[i - 10])
        mom = ((price - prev) / prev * 100) if prev else 0
        score = max(0, min(100, 50 + mom * 5))

        value = cash + shares * price
        equity_curve.append(value)

        if shares == 0 and score >= buy_threshold:
            amount = value * 0.10
            shares = amount / price
            cash -= amount
            entry = price
            trades.append({"type": "BUY", "price": round(price, 2), "score": round(score, 1)})

        elif shares > 0:
            pnl_pct = ((price - entry) / entry * 100) if entry else 0

            should_sell = (
                score <= sell_threshold
                or pnl_pct <= -stop_loss_pct
                or pnl_pct >= take_profit_pct
            )

            if should_sell:
                cash += shares * price
                trades.append({
                    "type": "SELL",
                    "price": round(price, 2),
                    "score": round(score, 1),
                    "pnl_pct": round(pnl_pct, 2),
                })
                shares = 0
                entry = None

    final_price = float(prices[-1])
    final_value = cash + shares * final_price
    return_pct = ((final_value - start_cash) / start_cash * 100) if start_cash else 0

    sells = [t for t in trades if t["type"] == "SELL"]
    wins = [t for t in sells if t.get("pnl_pct", 0) > 0]
    win_rate = (len(wins) / len(sells) * 100) if sells else 0

    return {
        "final_value": round(final_value, 2),
        "return_pct": round(return_pct, 2),
        "trades": trades,
        "equity_curve": equity_curve,
        "win_rate": round(win_rate, 1),
    }


def demo_prices(seed_price=100, n=180):
    prices = []
    price = float(seed_price)
    for i in range(n):
        drift = 0.06
        cycle = math.sin(i / 12) * 0.8
        noise = math.sin(i * 1.7) * 0.6
        price = max(1, price + drift + cycle + noise)
        prices.append(round(price, 2))
    return prices
