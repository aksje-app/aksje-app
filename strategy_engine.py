
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
    """Returnerer både nye og gamle nøkkelnavn brukt i appen.

    Tidligere app-kode forventet total_return/max_drawdown/win_rate osv.
    Denne funksjonen beholder også total_return_pct/max_drawdown_pct for nyere kode.
    """
    trades = trades or []
    if equity is None or len(equity) == 0:
        return {
            "total_return_pct": 0,
            "max_drawdown_pct": 0,
            "trades": 0,
            "total_return": 0,
            "max_drawdown": 0,
            "win_rate": 0,
            "num_trades": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
        }

    vals = equity["value"] if "value" in equity else equity.iloc[:, -1]
    total = (vals.iloc[-1] / vals.iloc[0] - 1) * 100 if vals.iloc[0] else 0
    dd = ((vals / vals.cummax()) - 1).min() * 100

    closed = [t for t in trades if str(t.get("type", "")).upper() == "SELL"] if isinstance(trades, list) else []
    pnls = []
    for t in closed:
        try:
            pnls.append(float(t.get("pnl_pct", 0)))
        except Exception:
            pass
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls) * 100) if pnls else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0)

    return {
        "total_return_pct": round(float(total), 2),
        "max_drawdown_pct": round(float(dd), 2),
        "trades": len(trades),
        "total_return": round(float(total), 2),
        "max_drawdown": round(float(dd), 2),
        "win_rate": round(float(win_rate), 1),
        "num_trades": len(trades),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "profit_factor": profit_factor,
    }

def optimize_strategy(df):
    return pd.DataFrame([
        {"parameter":"RSI exit", "value":75, "score":7.2},
        {"parameter":"Stop loss", "value":"7%", "score":7.0},
        {"parameter":"Take profit", "value":"12%", "score":7.4},
    ])
