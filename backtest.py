import pandas as pd
from scoring import score_stock

def simple_backtest(hist, sentiment=0.5, initial=10000):
    if hist is None or hist.empty or len(hist) < 120:
        return None
    df = hist.copy().dropna()
    close = df["Close"]
    # Prototype: kjøp og hold valgt aksje
    returns = close.pct_change().fillna(0)
    equity = initial * (1 + returns).cumprod()
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    ann_vol = returns.std() * (252 ** 0.5)
    sharpe = 0 if ann_vol == 0 else (returns.mean() * 252) / ann_vol
    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min()
    return {
        "equity": equity,
        "total_return": float(total_return),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
    }
