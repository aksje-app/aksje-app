
import numpy as np
import pandas as pd


def calc_trend_channel(hist, lookback=120):
    """
    Enkel robust trendkanal:
    - bruker log/lineær trend på siste lookback datapunkter
    - kanalbredde basert på residual standardavvik
    """
    try:
        close = hist["Close"].dropna().tail(int(lookback))
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

        current_price = float(y[-1])
        current_mid = float(mid[-1])
        current_upper = float(upper[-1])
        current_lower = float(lower[-1])

        if current_upper == current_lower:
            pos_pct = 50
        else:
            pos_pct = (current_price - current_lower) / (current_upper - current_lower) * 100

        if current_price > current_upper:
            status = "Over trendkanal"
            emoji = "🚀"
        elif current_price < current_lower:
            status = "Under trendkanal"
            emoji = "🔻"
        elif pos_pct >= 80:
            status = "Nær motstand i kanal"
            emoji = "⚠️"
        elif pos_pct <= 20:
            status = "Nær støtte i kanal"
            emoji = "🟢"
        else:
            status = "Midt i trendkanal"
            emoji = "📊"

        return {
            "index": close.index,
            "mid": mid,
            "upper": upper,
            "lower": lower,
            "slope": float(slope),
            "current_price": current_price,
            "current_mid": current_mid,
            "current_upper": current_upper,
            "current_lower": current_lower,
            "position_pct": round(float(pos_pct), 1),
            "status": status,
            "emoji": emoji,
        }
    except Exception:
        return None


def add_trend_channel_to_fig(fig, hist, lookback=120):
    ch = calc_trend_channel(hist, lookback=lookback)
    if not ch:
        return fig, None

    fig.add_trace({
        "type": "scatter",
        "x": ch["index"],
        "y": ch["upper"],
        "mode": "lines",
        "name": "Trendkanal øvre",
        "line": {"dash": "dash", "width": 1},
    })

    fig.add_trace({
        "type": "scatter",
        "x": ch["index"],
        "y": ch["mid"],
        "mode": "lines",
        "name": "Trend midt",
        "line": {"dash": "dot", "width": 1},
    })

    fig.add_trace({
        "type": "scatter",
        "x": ch["index"],
        "y": ch["lower"],
        "mode": "lines",
        "name": "Trendkanal nedre",
        "line": {"dash": "dash", "width": 1},
    })

    last_x = ch["index"][-1]

    fig.add_annotation(
        x=last_x,
        y=ch["current_upper"],
        text=f"Øvre kanal: {ch['current_upper']:.2f}",
        showarrow=False,
        xanchor="left",
        xshift=12,
        bgcolor="rgba(11,17,28,0.85)",
        font={"size": 11, "color": "white"},
    )

    fig.add_annotation(
        x=last_x,
        y=ch["current_lower"],
        text=f"Nedre kanal: {ch['current_lower']:.2f}",
        showarrow=False,
        xanchor="left",
        xshift=12,
        bgcolor="rgba(11,17,28,0.85)",
        font={"size": 11, "color": "white"},
    )

    fig.add_annotation(
        text=f"{ch['emoji']} {ch['status']} · {ch['position_pct']}% i kanal",
        xref="paper",
        yref="paper",
        x=0.01,
        y=1.26,
        showarrow=False,
        align="left",
        font={"size": 14, "color": "white"},
        bgcolor="rgba(30,41,59,0.94)",
        bordercolor="rgba(255,255,255,0.25)",
        borderwidth=1,
    )

    fig.update_layout(margin=dict(l=20, r=175, t=115, b=30))
    return fig, ch
