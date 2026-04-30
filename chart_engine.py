
import math
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def make_mock_history(ticker, price=100.0, days=180):
    """
    Stabil lokal historikk for UI/graf. Senere kan denne kobles mot ekte prisdata.
    """
    np.random.seed(abs(hash(ticker)) % (2**32))
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="D")
    trend = np.linspace(price * 0.82, price, days)
    noise = np.random.normal(0, price * 0.015, days).cumsum()
    wave = np.sin(np.linspace(0, 8 * math.pi, days)) * price * 0.04
    close = np.maximum(trend + noise + wave, 1)
    df = pd.DataFrame({"Close": close}, index=dates)
    return df


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def trend_channel(df, lookback=120):
    close = df["Close"].dropna().tail(lookback)
    if len(close) < 30:
        return None

    x = np.arange(len(close))
    y = close.values.astype(float)

    slope, intercept = np.polyfit(x, y, 1)
    mid = slope * x + intercept
    residuals = y - mid
    width = np.std(residuals) * 2.0

    upper = mid + width
    lower = mid - width

    current = float(y[-1])
    lower_now = float(lower[-1])
    upper_now = float(upper[-1])
    mid_now = float(mid[-1])

    if upper_now == lower_now:
        pos_pct = 50
    else:
        pos_pct = (current - lower_now) / (upper_now - lower_now) * 100

    if current > upper_now:
        status = "Over trendkanal"
        emoji = "🚀"
    elif current < lower_now:
        status = "Under trendkanal"
        emoji = "🔻"
    elif pos_pct >= 80:
        status = "Nær motstand"
        emoji = "⚠️"
    elif pos_pct <= 20:
        status = "Nær støtte"
        emoji = "🟢"
    else:
        status = "I trendkanal"
        emoji = "📊"

    return {
        "index": close.index,
        "upper": upper,
        "mid": mid,
        "lower": lower,
        "current": current,
        "upper_now": upper_now,
        "mid_now": mid_now,
        "lower_now": lower_now,
        "position_pct": round(float(pos_pct), 1),
        "status": status,
        "emoji": emoji,
    }


def price_chart(ticker, price):
    df = make_mock_history(ticker, price)
    ch = trend_channel(df)
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        name="Pris",
        line=dict(width=2),
    ))

    if ch:
        fig.add_trace(go.Scatter(x=ch["index"], y=ch["upper"], mode="lines", name="Trend øvre", line=dict(dash="dash", width=1)))
        fig.add_trace(go.Scatter(x=ch["index"], y=ch["mid"], mode="lines", name="Trend midt", line=dict(dash="dot", width=1)))
        fig.add_trace(go.Scatter(x=ch["index"], y=ch["lower"], mode="lines", name="Trend nedre", line=dict(dash="dash", width=1)))

        last_x = ch["index"][-1]
        fig.add_annotation(x=last_x, y=ch["current"], text=f"Gjeldende: {ch['current']:.2f}", showarrow=True)
        fig.add_annotation(x=last_x, y=ch["upper_now"], text=f"Motstand {ch['upper_now']:.2f}", showarrow=False, xshift=80)
        fig.add_annotation(x=last_x, y=ch["lower_now"], text=f"Støtte {ch['lower_now']:.2f}", showarrow=False, xshift=80)

    fig.update_layout(
        template="plotly_dark",
        height=420,
        margin=dict(l=20, r=120, t=50, b=30),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0b1220",
        legend=dict(orientation="h"),
        title=f"{ticker} - pris og trendkanal",
    )
    return fig, ch, df


def rsi_chart(ticker, price):
    df = make_mock_history(ticker, price)
    df["RSI"] = calc_rsi(df["Close"])
    current_rsi = float(df["RSI"].iloc[-1])
    prev_rsi = float(df["RSI"].iloc[-2])
    direction = "📈" if current_rsi >= prev_rsi else "📉"

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], mode="lines", name="RSI", line=dict(width=2)))
    fig.add_hline(y=80, line_dash="dot", annotation_text="80 ekstrem")
    fig.add_hline(y=70, line_dash="dash", annotation_text="70 overkjøpt")
    fig.add_hline(y=30, line_dash="dash", annotation_text="30 oversolgt")
    fig.update_layout(
        template="plotly_dark",
        height=300,
        margin=dict(l=20, r=80, t=40, b=25),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0b1220",
        title=f"{ticker} - RSI",
    )
    return fig, round(current_rsi, 1), direction
