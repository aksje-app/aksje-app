import pandas as pd
import itertools

def run_strategy(
    df,
    start_capital=100000,
    buy_rsi=60,
    sell_rsi=75,
    use_macd=True,
):
    """
    Enkel historisk strategi-simulering for én aksje.

    BUY:
    - RSI < buy_rsi
    - hvis use_macd=True: MACD > signal

    SELL:
    - RSI > sell_rsi
    - eller hvis use_macd=True: MACD < signal
    """
    capital = float(start_capital)
    position = 0.0
    equity_curve = []
    trades = []

    if df is None or df.empty or len(df) < 60:
        return capital, trades, equity_curve

    entry_price = None

    for i in range(50, len(df)):
        row = df.iloc[i]
        price = float(row["Close"])

        rsi = row.get("rsi", 50)
        macd = row.get("macd", 0)
        signal = row.get("macd_signal", 0)

        if pd.isna(rsi) or pd.isna(macd) or pd.isna(signal) or price <= 0:
            value = capital if position == 0 else position * price
            equity_curve.append((df.index[i], value))
            continue

        buy = rsi < buy_rsi
        sell = rsi > sell_rsi

        if use_macd:
            buy = buy and macd > signal
            sell = sell or macd < signal

        if position == 0 and buy:
            position = capital / price
            capital = 0.0
            entry_price = price
            trades.append({
                "type": "BUY",
                "date": df.index[i],
                "price": round(price, 2),
                "value": round(position * price, 2),
                "pnl_pct": None,
            })

        elif position > 0 and sell:
            capital = position * price
            pnl_pct = ((price - entry_price) / entry_price * 100) if entry_price else None
            position = 0.0
            entry_price = None
            trades.append({
                "type": "SELL",
                "date": df.index[i],
                "price": round(price, 2),
                "value": round(capital, 2),
                "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            })

        value = capital if position == 0 else position * price
        equity_curve.append((df.index[i], value))

    final_value = equity_curve[-1][1] if equity_curve else capital
    return final_value, trades, equity_curve


def strategy_stats(equity_curve, trades, start_capital=100000):
    if not equity_curve:
        return {
            "total_return": 0,
            "max_drawdown": 0,
            "num_trades": 0,
            "win_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
        }

    eq = pd.DataFrame(equity_curve, columns=["date", "value"])
    eq["peak"] = eq["value"].cummax()
    eq["drawdown"] = (eq["value"] - eq["peak"]) / eq["peak"]

    final_value = eq["value"].iloc[-1]
    total_return = (final_value - start_capital) / start_capital
    max_drawdown = eq["drawdown"].min()

    sells = [t for t in trades if t.get("type") == "SELL" and t.get("pnl_pct") is not None]
    wins = [t["pnl_pct"] for t in sells if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in sells if t["pnl_pct"] <= 0]

    win_rate = (len(wins) / len(sells) * 100) if sells else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit if gross_profit > 0 else 0

    return {
        "total_return": round(total_return * 100, 1),
        "max_drawdown": round(max_drawdown * 100, 1),
        "num_trades": len(trades),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
    }


def optimize_strategy(df, start_capital=100000):
    """
    Tester flere enkle RSI/MACD-varianter og returnerer rangert resultat.
    """
    buy_rsi_options = [45, 50, 55, 60, 65]
    sell_rsi_options = [65, 70, 75, 80]
    use_macd_options = [True, False]

    rows = []

    for buy_rsi, sell_rsi, use_macd in itertools.product(
        buy_rsi_options,
        sell_rsi_options,
        use_macd_options,
    ):
        if buy_rsi >= sell_rsi:
            continue

        final_value, trades, equity = run_strategy(
            df,
            start_capital=start_capital,
            buy_rsi=buy_rsi,
            sell_rsi=sell_rsi,
            use_macd=use_macd,
        )
        stats = strategy_stats(equity, trades, start_capital=start_capital)

        # Enkel kvalitetsscore: avkastning minus risiko
        quality_score = stats["total_return"] + stats["max_drawdown"] * 0.7 + stats["win_rate"] * 0.15

        rows.append({
            "buy_rsi": buy_rsi,
            "sell_rsi": sell_rsi,
            "use_macd": use_macd,
            "final_value": round(final_value, 0),
            "total_return": stats["total_return"],
            "max_drawdown": stats["max_drawdown"],
            "win_rate": stats["win_rate"],
            "profit_factor": stats["profit_factor"],
            "num_trades": stats["num_trades"],
            "quality_score": round(quality_score, 2),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("quality_score", ascending=False)
