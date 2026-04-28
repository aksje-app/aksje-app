import pandas as pd

def _safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default

def run_strategy(
    df,
    start_capital=100000,
    rsi_buy_max=60,
    rsi_sell_min=75,
):
    """
    Enkel historisk strategi for valgt aksje.

    BUY:
    - RSI under rsi_buy_max
    - MACD over signal

    SELL:
    - RSI over rsi_sell_min
    - eller MACD under signal

    Returnerer dict med:
    - final_value
    - trades DataFrame
    - equity_curve DataFrame
    - stats dict

    Dette er analyse og simulering, ikke investeringsråd.
    """
    data = df.copy().dropna(subset=["Close"])

    capital = float(start_capital)
    position = 0.0
    entry_price = None

    trades = []
    equity_rows = []

    for i in range(50, len(data)):
        date = data.index[i]
        price = _safe_float(data["Close"].iloc[i])
        rsi = _safe_float(data["rsi"].iloc[i], 50)
        macd = _safe_float(data["macd"].iloc[i], 0)
        macd_signal = _safe_float(data["macd_signal"].iloc[i], 0)

        buy_signal = (
            position == 0
            and rsi < rsi_buy_max
            and macd > macd_signal
        )

        sell_signal = (
            position > 0
            and (
                rsi > rsi_sell_min
                or macd < macd_signal
            )
        )

        if buy_signal and price > 0:
            position = capital / price
            entry_price = price
            trades.append({
                "date": date,
                "type": "BUY",
                "price": round(price, 2),
                "value": round(capital, 2),
                "return_pct": None,
            })
            capital = 0.0

        elif sell_signal and price > 0:
            capital = position * price
            ret_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0
            trades.append({
                "date": date,
                "type": "SELL",
                "price": round(price, 2),
                "value": round(capital, 2),
                "return_pct": round(ret_pct, 2),
            })
            position = 0.0
            entry_price = None

        current_value = capital if position == 0 else position * price
        equity_rows.append({
            "date": date,
            "value": current_value,
        })

    # Sluttverdi hvis posisjon fortsatt er åpen
    if equity_rows:
        final_value = equity_rows[-1]["value"]
    else:
        final_value = start_capital

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_rows)

    if not equity_df.empty:
        equity_df["peak"] = equity_df["value"].cummax()
        equity_df["drawdown"] = (equity_df["value"] - equity_df["peak"]) / equity_df["peak"] * 100
        max_drawdown_pct = float(equity_df["drawdown"].min())
    else:
        equity_df = pd.DataFrame(columns=["date", "value", "peak", "drawdown"])
        max_drawdown_pct = 0.0

    sell_trades = trades_df[trades_df["type"] == "SELL"] if not trades_df.empty else pd.DataFrame()
    if not sell_trades.empty and "return_pct" in sell_trades:
        win_rate = float((sell_trades["return_pct"] > 0).mean() * 100)
    else:
        win_rate = 0.0

    stats = {
        "total_return_pct": round((final_value - start_capital) / start_capital * 100, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "trade_count": int(len(trades_df)),
        "win_rate_pct": round(win_rate, 1),
    }

    return {
        "final_value": final_value,
        "trades": trades_df,
        "equity_curve": equity_df,
        "stats": stats,
    }
