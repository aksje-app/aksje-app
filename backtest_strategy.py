import pandas as pd
import yfinance as yf
from analysis import calculate_metrics, score_from_metrics

def download_history(tickers, period="5y"):
    data = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if not hist.empty and len(hist) > 280:
                data[ticker] = hist
        except Exception:
            pass
    return data

def run_monthly_score_strategy(
    tickers,
    months=24,
    top_n=5,
    benchmark="^GSPC",
    transaction_cost=0.002,
    stop_loss=None,
):
    histories = download_history(tickers, period="5y")
    if not histories:
        return pd.DataFrame(), pd.DataFrame(), "Fant ikke historiske data."

    month_starts = pd.date_range(end=pd.Timestamp.today().normalize(), periods=months + 1, freq="MS")
    portfolio_value = 1.0
    rows = []
    previous_holdings = set()

    for i in range(len(month_starts) - 1):
        start = month_starts[i]
        end = month_starts[i + 1]

        scores = []
        for ticker, hist in histories.items():
            past = hist[hist.index.tz_localize(None) < start]
            if len(past) < 220:
                continue
            metrics = calculate_metrics(past.tail(300))
            score, parts = score_from_metrics(metrics, sentiment=0.5)
            if score is not None:
                scores.append((ticker, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        selected = [t for t, s in scores[:top_n]]
        current_holdings = set(selected)

        turnover = len(previous_holdings.symmetric_difference(current_holdings)) / max(top_n * 2, 1)
        cost = turnover * transaction_cost
        previous_holdings = current_holdings

        returns = []
        for ticker in selected:
            hist = histories[ticker].copy()
            hist.index = hist.index.tz_localize(None)
            period = hist[(hist.index >= start) & (hist.index < end)]
            if len(period) > 2:
                start_price = period["Close"].iloc[0]
                end_price = period["Close"].iloc[-1]
                r = (end_price - start_price) / start_price

                if stop_loss:
                    min_r = (period["Close"].min() - start_price) / start_price
                    if min_r <= -abs(stop_loss):
                        r = -abs(stop_loss)

                returns.append(float(r))

        month_return = sum(returns) / len(returns) if returns else 0
        month_return_after_cost = month_return - cost
        portfolio_value *= (1 + month_return_after_cost)

        rows.append({
            "date": start,
            "value": portfolio_value,
            "monthly_return": month_return_after_cost,
            "gross_return": month_return,
            "cost": cost,
            "selected": ", ".join(selected),
        })

    strategy = pd.DataFrame(rows)

    try:
        bench = yf.Ticker(benchmark).history(start=month_starts[0], end=month_starts[-1], auto_adjust=True)
        if not bench.empty:
            bench_df = bench[["Close"]].copy()
            bench_df["benchmark_value"] = bench_df["Close"] / bench_df["Close"].iloc[0]
            bench_df = bench_df.reset_index().rename(columns={"Date": "date"})
            bench_df["date"] = pd.to_datetime(bench_df["date"]).dt.tz_localize(None)
        else:
            bench_df = pd.DataFrame()
    except Exception:
        bench_df = pd.DataFrame()

    return strategy, bench_df, None

def add_stats(df):
    if df.empty:
        return df, {}
    out = df.copy()
    out["peak"] = out["value"].cummax()
    out["drawdown"] = (out["value"] - out["peak"]) / out["peak"]

    total_return = out["value"].iloc[-1] - 1
    max_dd = out["drawdown"].min()
    monthly = out["monthly_return"]
    win_rate = (monthly > 0).mean()
    avg_month = monthly.mean()
    vol_month = monthly.std()
    sharpe_like = (avg_month / vol_month * (12 ** 0.5)) if vol_month and vol_month > 0 else 0

    stats = {
        "total_return": total_return,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "avg_month": avg_month,
        "sharpe_like": sharpe_like,
    }
    return out, stats
