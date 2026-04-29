import pandas as pd

def run_monthly_score_strategy(results, start_cash=100000):
    """
    Enkel fallback backtest.
    Brukes hvis full backtest-modul mangler.
    Returnerer tom/sikker struktur slik appen ikke krasjer.
    """
    return {
        "equity": pd.DataFrame(columns=["date", "value"]),
        "trades": [],
        "final_value": start_cash,
        "total_return": 0,
        "max_drawdown": 0,
        "win_rate": 0,
    }

def add_stats(strategy_result):
    """
    Legger til standard statistikk hvis mangler.
    """
    if not strategy_result:
        return {}
    strategy_result.setdefault("final_value", 100000)
    strategy_result.setdefault("total_return", 0)
    strategy_result.setdefault("max_drawdown", 0)
    strategy_result.setdefault("win_rate", 0)
    strategy_result.setdefault("trades", [])
    return strategy_result
