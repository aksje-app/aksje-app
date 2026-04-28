import pandas as pd

def run_strategy(df, start_capital=100000):
    """
    Enkel historisk strategi-simulering for én aksje.
    Bruker RSI + MACD:
    - BUY når RSI < 60 og MACD > signal
    - SELL når RSI > 75 eller MACD < signal

    Returnerer:
    - final_value
    - trades
    - equity_curve
    """
    capital = float(start_capital)
    position = 0.0
    equity_curve = []
    trades = []

    if df is None or df.empty or len(df) < 60:
        return capital, trades, equity_curve

    for i in range(50, len(df)):
        row = df.iloc[i]
        price = float(row["Close"])

        rsi = row.get("rsi", 50)
        macd = row.get("macd", 0)
        signal = row.get("macd_signal", 0)

        # Hopp over rader med manglende indikatorer
        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal) or price <= 0:
            value = capital if position == 0 else position * price
            equity_curve.append((df.index[i], value))
            continue

        buy = (rsi < 60 and macd > signal)
        sell = (rsi > 75 or macd < signal)

        if position == 0 and buy:
            position = capital / price
            capital = 0.0
            trades.append({
                "type": "BUY",
                "date": df.index[i],
                "price": round(price, 2),
                "value": round(position * price, 2),
            })

        elif position > 0 and sell:
            capital = position * price
            position = 0.0
            trades.append({
                "type": "SELL",
                "date": df.index[i],
                "price": round(price, 2),
                "value": round(capital, 2),
            })

        value = capital if position == 0 else position * price
        equity_curve.append((df.index[i], value))

    final_value = equity_curve[-1][1] if equity_curve else capital
    return final_value, trades, equity_curve


def strategy_stats(equity_curve, trades, start_capital=100000):
    """
    Lager enkel statistikk for strategien.
    """
    if not equity_curve:
        return {
            "total_return": 0,
            "max_drawdown": 0,
            "num_trades": 0,
        }

    eq = pd.DataFrame(equity_curve, columns=["date", "value"])
    eq["peak"] = eq["value"].cummax()
    eq["drawdown"] = (eq["value"] - eq["peak"]) / eq["peak"]

    final_value = eq["value"].iloc[-1]
    total_return = (final_value - start_capital) / start_capital
    max_drawdown = eq["drawdown"].min()

    return {
        "total_return": round(total_return * 100, 1),
        "max_drawdown": round(max_drawdown * 100, 1),
        "num_trades": len(trades),
    }
