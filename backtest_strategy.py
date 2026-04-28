import pandas as pd
import yfinance as yf
from analysis import calculate_score_from_hist

def download_history(tickers, period="3y"):
    data = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if not hist.empty and len(hist) > 260:
                data[ticker] = hist
        except Exception:
            pass
    return data

def run_monthly_score_strategy(tickers, months=12, top_n=5, benchmark="^GSPC"):
    """
    Tester strategien måned for måned:
    - Bruker historikk fram til månedens start
    - Rangerer aksjene
    - Kjøper topp N
    - Holder ca. 1 måned
    """
    histories = download_history(tickers, period="3y")
    if not histories:
        return pd.DataFrame(), pd.DataFrame(), "Fant ikke historiske data."

    all_dates = sorted(set().union(*[set(h.index.normalize()) for h in histories.values()]))
    if len(all_dates) < 260:
        return pd.DataFrame(), pd.DataFrame(), "For lite data til strategi-test."

    month_starts = pd.date_range(end=pd.Timestamp.today(), periods=months + 1, freq="MS")
    portfolio_value = 1.0
    rows = []

    for i in range(len(month_starts) - 1):
        start = month_starts[i]
        end = month_starts[i + 1]

        scores = []
        for ticker, hist in histories.items():
            past = hist[hist.index < start]
            if len(past) < 180:
                continue
            score, metrics = calculate_score_from_hist(past.tail(260), sentiment=0.5, pe=None)
            if score is not None:
                scores.append((ticker, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        selected = [t for t, s in scores[:top_n]]

        returns = []
        for ticker in selected:
            hist = histories[ticker]
            period = hist[(hist.index >= start) & (hist.index < end)]
            if len(period) > 2:
                r = (period["Close"].iloc[-1] - period["Close"].iloc[0]) / period["Close"].iloc[0]
                returns.append(float(r))

        month_return = sum(returns) / len(returns) if returns else 0
        portfolio_value *= (1 + month_return)

        rows.append({
            "date": start,
            "value": portfolio_value,
            "monthly_return": month_return,
            "selected": ", ".join(selected),
        })

    strategy = pd.DataFrame(rows)

    try:
        bench = yf.Ticker(benchmark).history(start=month_starts[0], end=month_starts[-1], auto_adjust=True)
        if not bench.empty:
            bench_df = bench[["Close"]].copy()
            bench_df["benchmark_value"] = bench_df["Close"] / bench_df["Close"].iloc[0]
            bench_df = bench_df.reset_index().rename(columns={"Date": "date"})
        else:
            bench_df = pd.DataFrame()
    except Exception:
        bench_df = pd.DataFrame()

    return strategy, bench_df, None

def add_drawdown(df):
    if df.empty:
        return df
    out = df.copy()
    out["peak"] = out["value"].cummax()
    out["drawdown"] = (out["value"] - out["peak"]) / out["peak"]
    return out
