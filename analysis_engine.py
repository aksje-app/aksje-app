
import numpy as np
import pandas as pd


def make_demo_history(ticker, price, points=180):
    """
    Stabil demo/historikk til UI. Senere kan denne byttes mot live Yahoo/Finnhub.
    Gir samme serie per ticker, så grafene hopper ikke tilfeldig.
    """
    seed = sum(ord(c) for c in str(ticker))
    rng = np.random.default_rng(seed)
    drift = 0.03 if "BUY" else 0.0
    noise = rng.normal(0, 1.2, points)
    series = np.cumsum(noise + drift)
    series = series - series[-1] + float(price)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=points, freq="D")
    return pd.DataFrame({"date": dates, "close": series})


def calculate_rsi(prices, period=14):
    prices = np.asarray(prices, dtype=float)
    if len(prices) < period + 2:
        return 50.0

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = pd.Series(gains).rolling(period).mean().iloc[-1]
    avg_loss = pd.Series(losses).rolling(period).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def trend_channel(prices):
    prices = np.asarray(prices, dtype=float)
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    mid = slope * x + intercept
    residuals = prices - mid
    width = np.std(residuals) * 1.8
    upper = mid + width
    lower = mid - width
    return mid, upper, lower


def support_resistance(prices):
    prices = np.asarray(prices, dtype=float)
    recent = prices[-80:] if len(prices) > 80 else prices
    support = float(np.percentile(recent, 15))
    resistance = float(np.percentile(recent, 85))
    return round(support, 2), round(resistance, 2)


def analyze(ticker, price):
    df = make_demo_history(ticker, price)
    prices = df["close"].values
    rsi = calculate_rsi(prices)
    mid, upper, lower = trend_channel(prices)
    support, resistance = support_resistance(prices)

    current = float(prices[-1])
    if upper[-1] == lower[-1]:
        channel_pos = 50
    else:
        channel_pos = (current - lower[-1]) / (upper[-1] - lower[-1]) * 100

    if channel_pos > 80:
        trend_status = "Nær motstand"
    elif channel_pos < 20:
        trend_status = "Nær støtte"
    else:
        trend_status = "Midt i kanal"

    if rsi >= 80:
        rsi_status = "Ekstremt overkjøpt"
    elif rsi >= 70:
        rsi_status = "Overkjøpt"
    elif rsi <= 30:
        rsi_status = "Oversolgt"
    else:
        rsi_status = "Nøytral"

    return {
        "history": df,
        "rsi": rsi,
        "rsi_status": rsi_status,
        "trend_mid": mid,
        "trend_upper": upper,
        "trend_lower": lower,
        "channel_pos": round(float(channel_pos), 1),
        "trend_status": trend_status,
        "support": support,
        "resistance": resistance,
        "current": round(current, 2),
    }
