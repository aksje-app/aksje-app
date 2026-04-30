
from paper_store import load_portfolio, reset_portfolio
from trading_engine import portfolio_value, auto_trade, paper_buy, paper_sell, STOP_LOSS_PCT, TRAILING_STOP_PCT
from trading_settings import load_rules

MAX_TRADES_PER_DAY = int(load_rules().get("max_trades_per_day", 3))
STOP_LOSS_PCT = STOP_LOSS_PCT / 100
TRAILING_STOP_PCT = TRAILING_STOP_PCT / 100


def performance_stats(portfolio=None, latest_prices=None):
    portfolio = portfolio or load_portfolio()
    rules = load_rules()
    start_cash = float(rules.get("start_cash", 100000))
    total = portfolio_value(portfolio, latest_prices or {})
    ret = ((total - start_cash) / start_cash * 100) if start_cash else 0
    trades = portfolio.get("trades", [])
    closed = [t for t in trades if t.get("type") == "SELL"]
    wins = [t for t in closed if float(t.get("pnl_pct") or 0) > 0]
    losses = [t for t in closed if float(t.get("pnl_pct") or 0) <= 0]
    return {
        "total_value": round(total,2),
        "total_return_pct": round(ret,2),
        "closed_trades": len(closed),
        "open_positions": len(portfolio.get("positions", {})),
        "win_rate": round(len(wins)/len(closed)*100,1) if closed else 0,
        "avg_win": round(sum(float(t.get("pnl_pct") or 0) for t in wins)/len(wins),2) if wins else 0,
        "avg_loss": round(sum(float(t.get("pnl_pct") or 0) for t in losses)/len(losses),2) if losses else 0,
        "trades_today": len(trades),
        "max_trades_per_day": int(rules.get("max_trades_per_day", 3)),
    }
