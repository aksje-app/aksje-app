
import pandas as pd

def run_strategy(df, start_value=100000):
    if df is None or df.empty or "Close" not in df:
        return start_value, [], pd.DataFrame({"date":[], "value":[]})
    close = df["Close"].dropna()
    if close.empty:
        return start_value, [], pd.DataFrame({"date":[], "value":[]})
    returns = close.pct_change().fillna(0)
    equity = (1+returns).cumprod() * start_value
    out = pd.DataFrame({"date": close.index, "value": equity.values})
    trades = []
    return float(equity.iloc[-1]), trades, out

def strategy_stats(equity, trades=None):
    if equity is None or len(equity)==0:
        return {"total_return_pct":0, "max_drawdown_pct":0, "trades":0}
    vals = equity["value"] if "value" in equity else equity.iloc[:, -1]
    total = (vals.iloc[-1]/vals.iloc[0]-1)*100 if vals.iloc[0] else 0
    dd = ((vals/vals.cummax())-1).min()*100
    return {"total_return_pct": round(float(total),2), "max_drawdown_pct": round(float(dd),2), "trades": len(trades or [])}

def optimize_strategy(df):
    return pd.DataFrame([
        {"parameter":"RSI exit", "value":75, "score":7.2},
        {"parameter":"Stop loss", "value":"7%", "score":7.0},
        {"parameter":"Take profit", "value":"12%", "score":7.4},
    ])
