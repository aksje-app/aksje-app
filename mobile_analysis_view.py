
import math
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    import yfinance as yf
except Exception:
    yf = None

from technical import calculate_rsi, calculate_macd, calculate_bollinger
from trading_engine import paper_buy, paper_sell, calc_levels
from paper_trading import load_portfolio


# MOBILE_ANALYSIS_STEP2_CHART_V1
# MOBILE_ANALYSIS_STEP3_TRADING_PANEL_V1
# PLOTLY_KEY_FIX_V1
# WIDGET_KEY_FIX_V2
# INDICATOR_LABELS_V1
# MOBILE_ANALYSIS_ADVANCED_INDICATORS_V1
# PRO_TERMINAL_UI_V1
# CONTROLS_FIX_V1


TIMEFRAME_CONFIG = {
    "1m": {"period": "1d", "interval": "1m", "max_points": 240},
    "15m": {"period": "5d", "interval": "15m", "max_points": 180},
    "1h": {"period": "1mo", "interval": "1h", "max_points": 180},
    "4h": {"period": "3mo", "interval": "1h", "max_points": 180},
    "1d": {"period": "1y", "interval": "1d", "max_points": 220},
}


CHART_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToAdd": ["pan2d", "zoom2d", "resetScale2d", "toImage"],
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


def _fmt_price(value, currency=""):
    try:
        value = float(value)
    except Exception:
        return "N/A"
    suffix = f" {currency}" if currency else ""
    if abs(value) >= 1000:
        return f"{value:,.2f}".replace(",", " ") + suffix
    return f"{value:.2f}" + suffix


def _fmt_pct(value):
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "N/A"


def _fmt_volume(value):
    try:
        value = float(value)
    except Exception:
        return "N/A"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value/1_000:.1f}K"
    return f"{value:.0f}"


def _currency_for_ticker(ticker):
    ticker = str(ticker).upper()
    if ticker.endswith(".OL"):
        return "kr"
    if ticker.endswith(".ST"):
        return "SEK"
    return "$"


def _clean_ohlcv(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    rename = {}
    for col in df.columns:
        low = str(col).lower()
        if low == "open":
            rename[col] = "Open"
        elif low == "high":
            rename[col] = "High"
        elif low == "low":
            rename[col] = "Low"
        elif low == "close":
            rename[col] = "Close"
        elif low == "volume":
            rename[col] = "Volume"
    df = df.rename(columns=rename)

    for col in ["Open", "High", "Low", "Close"]:
        if col not in df:
            return pd.DataFrame()

    if "Volume" not in df:
        df["Volume"] = 0

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df


def _resample_4h(df):
    if df is None or df.empty:
        return df
    try:
        out = df.resample("4H").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna(subset=["Open", "High", "Low", "Close"])
        return out if not out.empty else df
    except Exception:
        return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_timeframe_data(ticker, timeframe):
    if yf is None:
        return pd.DataFrame()

    cfg = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1d"])
    try:
        hist = yf.Ticker(ticker).history(
            period=cfg["period"],
            interval=cfg["interval"],
            auto_adjust=False,
            prepost=False,
        )
        hist = _clean_ohlcv(hist)
        if timeframe == "4h":
            hist = _resample_4h(hist)
        return hist
    except Exception:
        return pd.DataFrame()


def _latest_stats(df, fallback_item=None):
    fallback_item = fallback_item or {}
    df = _clean_ohlcv(df)

    if df.empty:
        price = fallback_item.get("price") or fallback_item.get("last_price") or fallback_item.get("regularMarketPrice")
        return {
            "price": price,
            "change_pct": None,
            "high": None,
            "low": None,
            "volume": None,
        }

    close = df["Close"].dropna()
    price = float(close.iloc[-1]) if len(close) else None

    if len(close) >= 2 and close.iloc[-2]:
        change_pct = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100
    else:
        change_pct = None

    high = float(df["High"].tail(390).max()) if "High" in df else None
    low = float(df["Low"].tail(390).min()) if "Low" in df else None
    volume = float(df["Volume"].tail(390).sum()) if "Volume" in df else None

    return {
        "price": price,
        "change_pct": change_pct,
        "high": high,
        "low": low,
        "volume": volume,
    }


def calculate_sar(df, step=0.02, max_step=0.2):
    """
    Enkel Parabolic SAR-implementasjon.
    Brukes visuelt som trend-/stoppreferanse.
    """
    df = _clean_ohlcv(df)
    if df.empty or len(df) < 5:
        return pd.Series(index=df.index, dtype=float)

    high = df["High"].values
    low = df["Low"].values

    sar = [low[0]]
    bull = True
    af = step
    ep = high[0]

    for i in range(1, len(df)):
        prev_sar = sar[-1]
        new_sar = prev_sar + af * (ep - prev_sar)

        if bull:
            new_sar = min(new_sar, low[i - 1], low[i])
            if low[i] < new_sar:
                bull = False
                new_sar = ep
                ep = low[i]
                af = step
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + step, max_step)
        else:
            new_sar = max(new_sar, high[i - 1], high[i])
            if high[i] > new_sar:
                bull = True
                new_sar = ep
                ep = high[i]
                af = step
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + step, max_step)

        sar.append(new_sar)

    return pd.Series(sar, index=df.index, name="SAR")


def calculate_kdj(df, n=9, k_period=3, d_period=3):
    """
    KDJ oscillator.
    K og D er glattet stochastic. J viser avvik/momentum.
    """
    df = _clean_ohlcv(df)
    if df.empty:
        empty = pd.Series(index=df.index, dtype=float)
        return empty, empty, empty

    low_min = df["Low"].rolling(n).min()
    high_max = df["High"].rolling(n).max()
    rsv = ((df["Close"] - low_min) / (high_max - low_min).replace(0, pd.NA)) * 100
    k = rsv.ewm(alpha=1 / k_period, adjust=False).mean()
    d = k.ewm(alpha=1 / d_period, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def _panel_count(indicators):
    panels = 1  # main candle
    panels += 1  # volume always shown as bottom base
    if "MACD" in indicators:
        panels += 1
    if "RSI" in indicators:
        panels += 1
    if "KDJ" in indicators:
        panels += 1
    return panels


def _add_main_indicators(fig, df, indicators):
    close = df["Close"]

    if "MA" in indicators:
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma5, name="MA(5)", mode="lines", line=dict(color="#3b82f6", width=1.7)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ma10, name="MA(10)", mode="lines", line=dict(color="#22c55e", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ma20, name="MA(20)", mode="lines", line=dict(color="#f59e0b", width=1.5)), row=1, col=1)

    if "EMA" in indicators:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ema12, name="EMA(12)", mode="lines", line=dict(color="#38bdf8", width=1.5, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ema26, name="EMA(26)", mode="lines", line=dict(color="#a78bfa", width=1.5, dash="dot")), row=1, col=1)

    if "BOLL" in indicators:
        bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
        fig.add_trace(go.Scatter(x=df.index, y=bb_upper, name="BOLL øvre", mode="lines", line=dict(color="#94a3b8", width=1, dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=bb_ma, name="BOLL midt", mode="lines", line=dict(color="#64748b", width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=bb_lower, name="BOLL nedre", mode="lines", line=dict(color="#94a3b8", width=1, dash="dash")), row=1, col=1)

    if "SAR" in indicators:
        sar = calculate_sar(df)
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=sar,
                name="SAR",
                mode="markers",
                marker=dict(size=5, color="#e879f9", symbol="circle"),
                hovertemplate="<b>SAR</b><br>%{x}<br>%{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    return fig





def calculate_trend_channel(df, period=20):
    """
    Trendkanal basert på rullerende høy/lav.
    Returnerer øvre, midtre og nedre kanal.
    """
    df = _clean_ohlcv(df)
    if df.empty:
        empty = pd.Series(index=df.index, dtype=float)
        return empty, empty, empty

    upper = df["High"].rolling(period).max()
    lower = df["Low"].rolling(period).min()
    mid = (upper + lower) / 2.0
    return upper, mid, lower


def _series_last(series):
    try:
        s = pd.Series(series).dropna()
        if s.empty:
            return None
        return float(s.iloc[-1])
    except Exception:
        return None


def _fmt_any(value, currency=""):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except Exception:
        return str(value)
    if currency:
        return _fmt_price(value, currency)
    return f"{value:.2f}"


def _indicator_snapshot(df, indicators, currency=""):
    df = _clean_ohlcv(df)
    snap = []
    if df.empty:
        return snap

    close = df['Close']
    if 'MA' in indicators:
        snap += [
            ('MA5', _series_last(close.rolling(5).mean()), currency),
            ('MA10', _series_last(close.rolling(10).mean()), currency),
            ('MA20', _series_last(close.rolling(20).mean()), currency),
        ]
    if 'EMA' in indicators:
        snap += [
            ('EMA12', _series_last(close.ewm(span=12, adjust=False).mean()), currency),
            ('EMA26', _series_last(close.ewm(span=26, adjust=False).mean()), currency),
        ]
    if 'BOLL' in indicators:
        bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
        snap += [
            ('BOLL Ø', _series_last(bb_upper), currency),
            ('BOLL M', _series_last(bb_ma), currency),
            ('BOLL N', _series_last(bb_lower), currency),
        ]
    if 'SAR' in indicators:
        sar = calculate_sar(df)
        snap += [('SAR', _series_last(sar), currency)]
    if 'VWAP' in indicators:
        vwap = calculate_vwap(df)
        snap += [('VWAP', _series_last(vwap), currency)]
    if 'KANAL' in indicators:
        ch_u, ch_m, ch_l = calculate_trend_channel(df)
        snap += [('Kanal Ø', _series_last(ch_u), currency), ('Kanal M', _series_last(ch_m), currency), ('Kanal N', _series_last(ch_l), currency)]
    if 'VOL' in indicators and 'Volume' in df:
        snap += [('VOL', _series_last(df['Volume']), '')]
    if 'MACD' in indicators:
        macd, macd_signal, macd_hist = calculate_macd(df)
        snap += [
            ('MACD', _series_last(macd), ''),
            ('Signal', _series_last(macd_signal), ''),
            ('Hist', _series_last(macd_hist), ''),
        ]
    if 'RSI' in indicators:
        rsi = calculate_rsi(df)
        snap += [('RSI', _series_last(rsi), '')]
    if 'KDJ' in indicators:
        k, d, j = calculate_kdj(df)
        snap += [('K', _series_last(k), ''), ('D', _series_last(d), ''), ('J', _series_last(j), '')]
    if 'ATR' in indicators:
        atr = calculate_atr(df)
        snap += [('ATR', _series_last(atr), currency)]
    if 'OBV' in indicators:
        obv = calculate_obv(df)
        snap += [('OBV', _series_last(obv), '')]
    if 'ADX' in indicators:
        adx, plus_di, minus_di = calculate_adx(df)
        snap += [('ADX', _series_last(adx), ''), ('+DI', _series_last(plus_di), ''), ('-DI', _series_last(minus_di), '')]
    return [(name, value, unit) for name, value, unit in snap if value is not None]


def _render_indicator_snapshot(df, indicators, currency=""):
    snap = _indicator_snapshot(df, indicators, currency=currency)
    if not snap:
        return
    st.markdown('**Aktive indikatorer nå**')
    parts = []
    for name, value, unit in snap:
        if name in {'VOL', 'OBV'}:
            vtxt = _fmt_volume(value)
        elif name in {'RSI', 'K', 'D', 'J', 'MACD', 'Signal', 'Hist', 'ADX', '+DI', '-DI'}:
            vtxt = f"{float(value):.2f}"
        else:
            vtxt = _fmt_price(value, unit)
        parts.append(f"<span class='mobile-chip'><b>{name}</b>: {vtxt}</span>")
    st.markdown("<div style='margin-top:8px; margin-bottom:8px;'>" + ''.join(parts) + "</div>", unsafe_allow_html=True)


def _add_last_value_label(fig, x, y, text, row=1, col=1, color='rgba(59,130,246,0.85)', text_color='white'):
    try:
        if y is None or pd.isna(y):
            return
        fig.add_annotation(
            x=x,
            y=float(y),
            text=text,
            showarrow=False,
            xanchor='left',
            yanchor='middle',
            bgcolor=color,
            bordercolor=color,
            borderwidth=1,
            font=dict(color=text_color, size=11),
            opacity=0.92,
            row=row,
            col=1,
        )
    except Exception:
        pass



def build_mobile_chart(df, ticker, timeframe, indicators, chart_type='Candles'):
    df = _clean_ohlcv(df)
    if df.empty:
        return None

    cfg = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1d"])
    max_points = cfg.get("max_points", 220)
    if len(df) > max_points:
        df = df.tail(max_points)

    indicators = indicators or ["MA", "VOL", "KANAL"]
    overlay_set = {"MA", "EMA", "BOLL", "SAR", "VWAP", "KANAL"}
    panel_rows = []
    for name in ["VOL", "MACD", "RSI", "KDJ", "ATR", "OBV", "ADX"]:
        if name in indicators:
            panel_rows.append(name)

    rows = 1 + len(panel_rows)
    row_titles = ["Pris"] + panel_rows

    if len(panel_rows) == 0:
        row_heights = [1.0]
    else:
        price_h = 0.54 if len(panel_rows) <= 2 else 0.46
        remainder = max(0.26, 1.0 - price_h)
        each = remainder / len(panel_rows)
        row_heights = [price_h] + [each] * len(panel_rows)

    height = min(420 + (rows - 1) * 110, 1180)

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.022,
        subplot_titles=row_titles,
        specs=[[{"secondary_y": False}] for _ in range(rows)],
    )

    chart_type = chart_type or "Candles"
    if chart_type == "Line":
        fig.add_trace(
            go.Scattergl(
                x=df.index,
                y=df["Close"],
                name=f"{ticker} linje",
                mode="lines",
                line=dict(color="#60a5fa", width=1.8),
                hovertemplate="<b>%{x}</b><br>Close: %{y:.2f}<extra></extra>",
            ),
            row=1, col=1,
        )
    elif chart_type == "Area":
        fig.add_trace(
            go.Scattergl(
                x=df.index,
                y=df["Close"],
                name=f"{ticker} område",
                mode="lines",
                fill="tozeroy",
                line=dict(color="#60a5fa", width=1.6),
                fillcolor="rgba(96,165,250,0.18)",
                hovertemplate="<b>%{x}</b><br>Close: %{y:.2f}<extra></extra>",
            ),
            row=1, col=1,
        )
    else:
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name=f"{ticker} candles",
                increasing_line_color="#22c55e",
                decreasing_line_color="#ef4444",
                increasing_fillcolor="#22c55e",
                decreasing_fillcolor="#ef4444",
                hovertemplate=("<b>%{x}</b><br>Open: %{open:.2f}<br>High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}<extra></extra>"),
            ),
            row=1, col=1,
        )

    close = df["Close"]
    last_x = df.index[-1]

    if "MA" in indicators:
        ma5 = close.rolling(5).mean(); ma10 = close.rolling(10).mean(); ma20 = close.rolling(20).mean()
        fig.add_trace(go.Scattergl(x=df.index, y=ma5, name="MA5", mode="lines", line=dict(color="#3b82f6", width=1.2)), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=ma10, name="MA10", mode="lines", line=dict(color="#22c55e", width=1.2)), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=ma20, name="MA20", mode="lines", line=dict(color="#f59e0b", width=1.3)), row=1, col=1)
        _add_last_value_label(fig, last_x, _series_last(ma5), f"MA5 {(_series_last(ma5) or 0):.2f}", row=1, color='rgba(59,130,246,0.85)')
        _add_last_value_label(fig, last_x, _series_last(ma10), f"MA10 {(_series_last(ma10) or 0):.2f}", row=1, color='rgba(34,197,94,0.85)')
        _add_last_value_label(fig, last_x, _series_last(ma20), f"MA20 {(_series_last(ma20) or 0):.2f}", row=1, color='rgba(245,158,11,0.85)')

    if "EMA" in indicators:
        ema12 = close.ewm(span=12, adjust=False).mean(); ema26 = close.ewm(span=26, adjust=False).mean()
        fig.add_trace(go.Scattergl(x=df.index, y=ema12, name="EMA12", mode="lines", line=dict(color="#38bdf8", width=1.2)), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=ema26, name="EMA26", mode="lines", line=dict(color="#a78bfa", width=1.2)), row=1, col=1)
        _add_last_value_label(fig, last_x, _series_last(ema12), f"EMA12 {(_series_last(ema12) or 0):.2f}", row=1, color='rgba(56,189,248,0.85)')
        _add_last_value_label(fig, last_x, _series_last(ema26), f"EMA26 {(_series_last(ema26) or 0):.2f}", row=1, color='rgba(167,139,250,0.85)')

    if "BOLL" in indicators:
        bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
        fig.add_trace(go.Scattergl(x=df.index, y=bb_upper, name="BOLL øvre", mode="lines", line=dict(color="#22d3ee", width=1.1, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=bb_ma, name="BOLL midt", mode="lines", line=dict(color="#f97316", width=1.0)), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=bb_lower, name="BOLL nedre", mode="lines", line=dict(color="#a855f7", width=1.1, dash="dot")), row=1, col=1)
        _add_last_value_label(fig, last_x, _series_last(bb_upper), f"BB øvre {(_series_last(bb_upper) or 0):.2f}", row=1, color='rgba(34,211,238,0.85)')
        _add_last_value_label(fig, last_x, _series_last(bb_ma), f"BB midt {(_series_last(bb_ma) or 0):.2f}", row=1, color='rgba(249,115,22,0.85)')
        _add_last_value_label(fig, last_x, _series_last(bb_lower), f"BB nedre {(_series_last(bb_lower) or 0):.2f}", row=1, color='rgba(168,85,247,0.85)')

    if "SAR" in indicators:
        sar = calculate_sar(df)
        fig.add_trace(go.Scattergl(x=df.index, y=sar, name="SAR", mode="markers", marker=dict(color="#e879f9", size=4, opacity=0.9)), row=1, col=1)
        _add_last_value_label(fig, last_x, _series_last(sar), f"SAR {(_series_last(sar) or 0):.2f}", row=1, color='rgba(232,121,249,0.85)')

    if "VWAP" in indicators:
        vwap = calculate_vwap(df)
        fig.add_trace(go.Scattergl(x=df.index, y=vwap, name="VWAP", mode="lines", line=dict(color="#facc15", width=1.2)), row=1, col=1)
        _add_last_value_label(fig, last_x, _series_last(vwap), f"VWAP {(_series_last(vwap) or 0):.2f}", row=1, color='rgba(250,204,21,0.88)', text_color='#111827')

    if "KANAL" in indicators:
        ch_u, ch_m, ch_l = calculate_trend_channel(df)
        fig.add_trace(go.Scattergl(x=df.index, y=ch_u, name="Trendkanal øvre", mode="lines", line=dict(color="#94a3b8", width=1.0, dash="dash")), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=ch_m, name="Trendkanal midt", mode="lines", line=dict(color="#cbd5e1", width=1.0, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scattergl(x=df.index, y=ch_l, name="Trendkanal nedre", mode="lines", line=dict(color="#94a3b8", width=1.0, dash="dash")), row=1, col=1)
        _add_last_value_label(fig, last_x, _series_last(ch_u), f"Kanal Ø {(_series_last(ch_u) or 0):.2f}", row=1, color='rgba(148,163,184,0.85)', text_color='#111827')
        _add_last_value_label(fig, last_x, _series_last(ch_m), f"Kanal M {(_series_last(ch_m) or 0):.2f}", row=1, color='rgba(203,213,225,0.85)', text_color='#111827')
        _add_last_value_label(fig, last_x, _series_last(ch_l), f"Kanal N {(_series_last(ch_l) or 0):.2f}", row=1, color='rgba(148,163,184,0.85)', text_color='#111827')

    last_price = float(close.dropna().iloc[-1])
    fig.add_hline(y=last_price, line_dash="dot", line_color="rgba(16,185,129,0.9)", row=1, col=1)
    fig.add_annotation(x=last_x, y=last_price, text=f"Gjeldende kurs {last_price:.2f}", showarrow=False, xanchor="left", yanchor="middle", bgcolor="rgba(16,185,129,0.92)", bordercolor="#10b981", borderwidth=1, font=dict(color="white", size=12), row=1, col=1)

    row_idx = 2
    for panel in panel_rows:
        if panel == "VOL":
            vol_colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(df["Open"], df["Close"])]
            fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="VOL", marker=dict(color=vol_colors), opacity=0.75), row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(df["Volume"]), f"VOL {_fmt_volume(_series_last(df['Volume']))}", row=row_idx, color='rgba(34,197,94,0.85)')
        elif panel == "MACD":
            macd, macd_signal, macd_hist = calculate_macd(df)
            hist_colors = ["#22c55e" if float(v or 0) >= 0 else "#ef4444" for v in macd_hist.fillna(0)]
            fig.add_trace(go.Bar(x=df.index, y=macd_hist, name="MACD hist", marker=dict(color=hist_colors), opacity=0.5), row=row_idx, col=1)
            fig.add_trace(go.Scattergl(x=df.index, y=macd, name="MACD", mode="lines", line=dict(color="#3b82f6", width=1.3)), row=row_idx, col=1)
            fig.add_trace(go.Scattergl(x=df.index, y=macd_signal, name="Signal", mode="lines", line=dict(color="#ef4444", width=1.2)), row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(macd), f"MACD {(_series_last(macd) or 0):.2f}", row=row_idx, color='rgba(59,130,246,0.85)')
            _add_last_value_label(fig, last_x, _series_last(macd_signal), f"Signal {(_series_last(macd_signal) or 0):.2f}", row=row_idx, color='rgba(239,68,68,0.85)')
        elif panel == "RSI":
            rsi = calculate_rsi(df)
            fig.add_trace(go.Scattergl(x=df.index, y=rsi, name="RSI", mode="lines", line=dict(color="#a78bfa", width=1.5)), row=row_idx, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="rgba(239,68,68,0.75)", row=row_idx, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="rgba(34,197,94,0.75)", row=row_idx, col=1)
            fig.update_yaxes(range=[0, 100], row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(rsi), f"RSI {(_series_last(rsi) or 0):.1f}", row=row_idx, color='rgba(167,139,250,0.85)')
        elif panel == "KDJ":
            k, d, j = calculate_kdj(df)
            fig.add_trace(go.Scattergl(x=df.index, y=k, name="K", mode="lines", line=dict(color="#3b82f6", width=1.3)), row=row_idx, col=1)
            fig.add_trace(go.Scattergl(x=df.index, y=d, name="D", mode="lines", line=dict(color="#f59e0b", width=1.3)), row=row_idx, col=1)
            fig.add_trace(go.Scattergl(x=df.index, y=j, name="J", mode="lines", line=dict(color="#e879f9", width=1.2)), row=row_idx, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="rgba(239,68,68,0.65)", row=row_idx, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="rgba(34,197,94,0.65)", row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(k), f"K {(_series_last(k) or 0):.1f}", row=row_idx, color='rgba(59,130,246,0.85)')
            _add_last_value_label(fig, last_x, _series_last(d), f"D {(_series_last(d) or 0):.1f}", row=row_idx, color='rgba(245,158,11,0.85)')
            _add_last_value_label(fig, last_x, _series_last(j), f"J {(_series_last(j) or 0):.1f}", row=row_idx, color='rgba(232,121,249,0.85)')
        elif panel == "ATR":
            atr = calculate_atr(df)
            fig.add_trace(go.Scattergl(x=df.index, y=atr, name="ATR", mode="lines", line=dict(color="#f97316", width=1.4)), row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(atr), f"ATR {(_series_last(atr) or 0):.2f}", row=row_idx, color='rgba(249,115,22,0.85)')
        elif panel == "OBV":
            obv = calculate_obv(df)
            fig.add_trace(go.Scattergl(x=df.index, y=obv, name="OBV", mode="lines", line=dict(color="#14b8a6", width=1.4)), row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(obv), f"OBV {_fmt_volume(_series_last(obv))}", row=row_idx, color='rgba(20,184,166,0.85)')
        elif panel == "ADX":
            adx, plus_di, minus_di = calculate_adx(df)
            fig.add_trace(go.Scattergl(x=df.index, y=adx, name="ADX", mode="lines", line=dict(color="#facc15", width=1.4)), row=row_idx, col=1)
            fig.add_trace(go.Scattergl(x=df.index, y=plus_di, name="+DI", mode="lines", line=dict(color="#22c55e", width=1.2)), row=row_idx, col=1)
            fig.add_trace(go.Scattergl(x=df.index, y=minus_di, name="-DI", mode="lines", line=dict(color="#ef4444", width=1.2)), row=row_idx, col=1)
            fig.add_hline(y=25, line_dash="dash", line_color="rgba(250,204,21,0.50)", row=row_idx, col=1)
            _add_last_value_label(fig, last_x, _series_last(adx), f"ADX {(_series_last(adx) or 0):.1f}", row=row_idx, color='rgba(250,204,21,0.88)', text_color='#111827')
        row_idx += 1

    fig.update_layout(
        title=f"{ticker} · {timeframe}",
        template="plotly_dark",
        height=height,
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        margin=dict(l=8, r=110, t=52, b=22),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        dragmode="pan",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, bgcolor="rgba(7,17,31,0.70)", font=dict(size=10)),
    )

    for i in range(1, rows + 1):
        fig.update_yaxes(side="right", row=i, col=1, gridcolor="rgba(148,163,184,0.12)", zeroline=False)
        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", row=i, col=1, gridcolor="rgba(148,163,184,0.10)")
        fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", row=i, col=1)

    return fig


def render_chart_help():


    st.caption("Graf: dra for pan, bruk musehjul/pinch for zoom, dobbelttrykk for reset. Verdier for aktive indikatorer vises over grafen og som etiketter på linjene. KANAL gir trendkanal tilbake rundt gjeldende kurs.")





def _safe_key(*parts):
    raw = "_".join(str(p) for p in parts if p is not None)
    return (
        raw.replace(" ", "_")
        .replace("/", "_")
        .replace(".", "_")
        .replace(":", "_")
        .replace("-", "_")
        .replace("(", "")
        .replace(")", "")
    )


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _get_position_for_ticker(portfolio, ticker):
    positions = portfolio.get("positions", {}) if portfolio else {}
    ticker_upper = str(ticker).upper()
    return positions.get(ticker) or positions.get(ticker_upper)


def _position_metrics(position, current_price):
    if not position:
        return {}

    shares = _safe_float(position.get("shares", 0))
    entry = _safe_float(position.get("entry_price", position.get("price", 0)))
    current_price = _safe_float(current_price, entry)
    value_now = shares * current_price
    cost = shares * entry
    pnl = value_now - cost
    pnl_pct = ((current_price / entry) - 1) * 100 if entry else 0

    return {
        "shares": shares,
        "entry": entry,
        "value_now": value_now,
        "cost": cost,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
    }


def _trade_rows_for_ticker(portfolio, ticker):
    trades = portfolio.get("trades", []) if portfolio else []
    ticker_upper = str(ticker).upper()
    rows = []
    for trade in trades:
        if str(trade.get("ticker", "")).upper() != ticker_upper:
            continue

        price = _safe_float(trade.get("price", 0))
        shares = _safe_float(trade.get("shares", 0))
        amount = _safe_float(trade.get("amount", price * shares))
        rows.append({
            "Tid": trade.get("time") or trade.get("timestamp") or "",
            "Type": trade.get("type", ""),
            "Pris": round(price, 2),
            "Antall": round(shares, 4),
            "Beløp": round(amount, 2),
            "P/L %": trade.get("pnl_pct", ""),
            "Confidence": trade.get("confidence", ""),
            "Årsak": trade.get("reason", ""),
        })
    return rows



def _decision_class(signal_text: str) -> str:
    s = str(signal_text or '').upper()
    if 'BUY' in s or 'KJØP' in s:
        return 'green'
    if 'SELL' in s or 'SALG' in s or 'AVOID' in s or 'UNNGÅ' in s:
        return 'red'
    return ''


def _render_mobile_section_picker(key_prefix=''):
    st.markdown("<div style='margin:10px 0 6px 0; font-weight:900;'>Panel</div>", unsafe_allow_html=True)
    return st.radio(
        'Panelvalg',
        ['Marked', 'Ordre', 'Trades', 'Info'],
        horizontal=True,
        label_visibility='collapsed',
        key=f'mobile_panel_picker_{key_prefix}',
    )




def _position_side_text(position):
    return "LONG" if position else "FLAT"


def _signal_badge(signal_text):
    s = str(signal_text or "").upper()
    if "BUY" in s or "KJØP" in s:
        return "BUY", "green"
    if "SELL" in s or "SALG" in s or "AVOID" in s or "UNNGÅ" in s:
        return "SELL", "red"
    return "WAIT", ""


def _pct_class(value):
    try:
        return "green" if float(value) >= 0 else "red"
    except Exception:
        return ""


def render_pro_terminal_header(ticker, company, label, price, currency, change_pct, stats, decision, item, technical_context):
    """
    Trading-terminal header: mer kompakt, mer informativ og bedre på mobil.
    """
    portfolio = load_portfolio()
    position = _get_position_for_ticker(portfolio, ticker)
    metrics = _position_metrics(position, price)
    signal_text = str(decision.get("decision", "HOLD / WAIT"))
    signal_short, signal_class = _signal_badge(signal_text)
    side = _position_side_text(position)
    score = item.get("score", decision.get("decision_score", "N/A"))
    confidence = int(decision.get("confidence", 0) or 0)
    rsi = technical_context.get("rsi", None)
    rsi_txt = f"{float(rsi):.1f}" if isinstance(rsi, (int, float)) else "N/A"
    change_class = _pct_class(change_pct)

    st.markdown(
        f"""
        <div class="pro-terminal-head">
            <div class="pro-left">
                <div class="pro-symbol-row">
                    <span class="pro-symbol">{ticker}</span>
                    <span class="pro-market">{label}</span>
                    <span class="pro-badge {signal_class}">{signal_short}</span>
                    <span class="pro-badge">POS: {side}</span>
                </div>
                <div class="pro-company">{company or "Ingen selskapsnavn"}</div>
                <div class="pro-mini-line">
                    <span>Score <b>{score}</b></span>
                    <span>Conf <b>{confidence}%</b></span>
                    <span>RSI <b>{rsi_txt}</b></span>
                    <span>Risk <b>{decision.get("risk", "N/A")}</b></span>
                </div>
            </div>
            <div class="pro-right">
                <div class="pro-price">{_fmt_price(price, currency)}</div>
                <div class="pro-change {change_class}">{_fmt_pct(change_pct)} · valgt periode</div>
            </div>
        </div>
        <div class="pro-stat-grid">
            <div class="pro-stat"><span>24t høy</span><b>{_fmt_price(stats.get("high"), currency)}</b></div>
            <div class="pro-stat"><span>24t lav</span><b>{_fmt_price(stats.get("low"), currency)}</b></div>
            <div class="pro-stat"><span>Volum</span><b>{_fmt_volume(stats.get("volume"))}</b></div>
            <div class="pro-stat"><span>P/L</span><b>{_fmt_price(metrics.get("pnl", 0), currency) if position else "N/A"}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pro_preset_bar(ticker, label, timeframe):
    """
    Presets gjør analyse raskere på mobil og reduserer unødvendige indikatorer.
    """
    preset_key = _safe_key("indicator_preset_v1", label, ticker, timeframe)
    preset = st.radio(
        "Indikator-preset",
        ["Standard", "Momentum", "Volatilitet", "Volum", "Full"],
        horizontal=True,
        label_visibility="collapsed",
        key=preset_key,
    )
    if preset == "Standard":
        return ["MA", "VOL", "KANAL"]
    if preset == "Momentum":
        return ["MA", "MACD", "RSI", "KDJ"]
    if preset == "Volatilitet":
        return ["MA", "BOLL", "ATR", "KANAL"]
    if preset == "Volum":
        return ["VWAP", "VOL", "OBV", "ADX"]
    return ["MA", "EMA", "BOLL", "SAR", "VWAP", "KANAL", "VOL", "MACD", "RSI", "ADX"]


def render_overview_panel_v4(ticker, price, currency, confidence, decision, item, technical_context=None, key_prefix=''):
    technical_context = technical_context or {}
    portfolio = load_portfolio()
    position = _get_position_for_ticker(portfolio, ticker)
    metrics = _position_metrics(position, price)
    signal_text = str(decision.get('decision', 'HOLD / WAIT'))
    signal_class = _decision_class(signal_text)
    score = item.get('score', decision.get('decision_score', 'N/A'))
    risk = decision.get('risk', 'N/A')
    current_price = _safe_float(price)

    st.markdown('### 📋 Oversikt')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Signal', signal_text)
    c2.metric('Score', score)
    c3.metric('Confidence', f"{int(confidence or 0)}%")
    c4.metric('Risiko', risk)

    d1, d2, d3, d4 = st.columns(4)
    d1.metric('Siste pris', _fmt_price(current_price, currency))
    d2.metric('Posisjon', 'Åpen' if position else 'Ingen')
    d3.metric('Verdi nå', _fmt_price(metrics.get('value_now', 0), currency) if position else 'N/A')
    d4.metric('P/L', _fmt_price(metrics.get('pnl', 0), currency) if position else 'N/A', delta=f"{metrics.get('pnl_pct', 0):+.2f}%" if position else None)

    st.markdown(
        f"""
        <div style="margin:8px 0 10px 0; display:flex; flex-wrap:wrap; gap:8px;">
            <span class="mobile-chip {signal_class}">Signal: {signal_text}</span>
            <span class="mobile-chip">Score: {score}</span>
            <span class="mobile-chip">Confidence: {int(confidence or 0)}%</span>
            <span class="mobile-chip">RSI: {f"{float(technical_context.get('rsi')):.1f}" if isinstance(technical_context.get('rsi'), (int, float)) else 'N/A'}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    q1, q2 = st.columns(2)
    with q1:
        if st.button(f'🟢 Hurtig paper-kjøp {ticker}', key=f'quick_buy_{key_prefix}_{ticker}', use_container_width=True):
            ok, msg = paper_buy(ticker, current_price, confidence, 'Mobil oversikt hurtigkjøp')
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)
    with q2:
        sell_disabled = not position
        if st.button(f'🔴 Hurtig paper-selg {ticker}', key=f'quick_sell_{key_prefix}_{ticker}', use_container_width=True, disabled=sell_disabled):
            ok, msg = paper_sell(ticker, current_price, 'Mobil oversikt hurtigsalg')
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)

    st.caption('Marked-panelet er rask beslutningsflate. Ordre gir kontrollert kjøp/salg, Trades viser historikk og Info forklarer signal/risiko.')



def render_trading_panel_v3(ticker, price, currency, confidence, decision, item, key_prefix=''):
    """
    Kompakt og mer mobilvennlig trading-panel.
    Bruker samme paper_buy/paper_sell som resten av systemet.
    """
    _panel_key = _safe_key("order_panel_v4", key_prefix, ticker)
    portfolio = load_portfolio()
    position = _get_position_for_ticker(portfolio, ticker)
    metrics = _position_metrics(position, price)
    price = _safe_float(price)
    signal_text = str(decision.get('decision', 'HOLD / WAIT'))
    score = item.get('score', decision.get('decision_score', 'N/A'))
    risk = decision.get('risk', 'N/A')

    try:
        stop_loss, take_profit, trailing_stop = calc_levels(price)
    except Exception:
        stop_loss, take_profit, trailing_stop = None, None, None

    st.markdown('<div class="pro-action-card">', unsafe_allow_html=True)
    st.markdown('### 🧾 Ordre')
    st.caption('Paper trading · samme motor som resten av systemet.')

    top1, top2, top3, top4 = st.columns(4)
    top1.metric('Pris', _fmt_price(price, currency))
    top2.metric('Signal', signal_text)
    top3.metric('Confidence', f"{int(confidence or 0)}%")
    top4.metric('Score', score)

    mode_labels = ['Kjøp beløp', 'Kjøp antall', 'Selg antall']
    mode = st.radio(
        'Ordretype',
        mode_labels,
        horizontal=True,
        key=f'order_mode_v4_{_panel_key}',
        label_visibility='collapsed',
    )

    default_cash = _safe_float(portfolio.get('cash', 0))
    buy_amount_key = f'order_amount_v4_{_panel_key}'
    qty_key = f'order_qty_v4_{_panel_key}'
    price_key = f'order_price_v4_{_panel_key}'
    if price_key not in st.session_state:
        st.session_state[price_key] = float(round(price or 0, 4))
    if buy_amount_key not in st.session_state:
        st.session_state[buy_amount_key] = float(round(min(max(default_cash * 0.10, 1000), default_cash) if default_cash else 1000, 2))
    if qty_key not in st.session_state:
        max_sell = metrics.get('shares', 0) if position else 10.0
        st.session_state[qty_key] = float(min(10.0, max_sell) if max_sell else 10.0)

    st.markdown('**Hurtigvalg**')
    quick_cols = st.columns(4)
    if mode == 'Kjøp beløp':
        quick_values = [0.10, 0.25, 0.50, 1.00]
        for pct, col in zip(quick_values, quick_cols):
            with col:
                if st.button(f'{int(pct*100)}%', key=f'quickpct_buy_{pct}_{_panel_key}', use_container_width=True):
                    st.session_state[buy_amount_key] = float(round(default_cash * pct, 2)) if default_cash else st.session_state.get(buy_amount_key, 1000.0)
                    st.rerun()
    elif mode == 'Selg antall':
        max_sell = metrics.get('shares', 0) if position else 0
        quick_values = [0.25, 0.50, 0.75, 1.00]
        for pct, col in zip(quick_values, quick_cols):
            with col:
                if st.button(f'{int(pct*100)}%', key=f'quickpct_sell_{pct}_{_panel_key}', use_container_width=True, disabled=max_sell <= 0):
                    st.session_state[qty_key] = float(round(max_sell * pct, 4))
                    st.rerun()
    else:
        qty_values = [1, 5, 10, 25]
        for val, col in zip(qty_values, quick_cols):
            with col:
                if st.button(f'{val}', key=f'quickqty_{val}_{_panel_key}', use_container_width=True):
                    st.session_state[qty_key] = float(val)
                    st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        order_price = st.number_input(
            f'Pris ({currency})',
            min_value=0.0,
            step=0.1,
            key=price_key,
        )
    with c2:
        if mode == 'Kjøp beløp':
            amount = st.number_input(
                f'Beløp ({currency})',
                min_value=0.0,
                step=500.0,
                key=buy_amount_key,
            )
            qty = amount / order_price if order_price else 0
        else:
            qty = st.number_input(
                'Antall',
                min_value=0.0,
                step=1.0,
                key=qty_key,
            )
            amount = qty * order_price

    s1, s2, s3, s4 = st.columns(4)
    s1.metric('Estimert antall', f'{qty:.4f}')
    s2.metric('Estimert verdi', _fmt_price(amount, currency))
    s3.metric('Cash', _fmt_price(default_cash, currency))
    s4.metric('Åpen posisjon', 'Ja' if position else 'Nei')

    r1, r2, r3 = st.columns(3)
    r1.metric('Stop-loss', _fmt_price(stop_loss, currency) if stop_loss else 'N/A')
    r2.metric('Take-profit', _fmt_price(take_profit, currency) if take_profit else 'N/A')
    r3.metric('Trailing stop', _fmt_price(trailing_stop, currency) if trailing_stop else 'N/A')

    st.markdown(
        f"""
        <div style="background:rgba(15,23,42,0.75); border:1px solid rgba(148,163,184,0.25); border-radius:12px; padding:10px; margin:8px 0 12px 0;">
            <b>Ordregrunnlag</b><br>
            Signal: <b>{signal_text}</b> · Confidence: <b>{confidence}%</b> · Score: <b>{score}</b> · Risiko: <b>{risk}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns(2)
    with b1:
        buy_disabled = mode == 'Selg antall' or order_price <= 0 or amount <= 0
        if st.button(f'🟢 Paper-kjøp {ticker}', key=f'buy_v4_{_panel_key}', use_container_width=True, disabled=buy_disabled):
            ok, msg = paper_buy(ticker, order_price, confidence, 'Mobil ordrepanel v4')
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)
    with b2:
        sell_disabled = not position or qty <= 0 or order_price <= 0
        if st.button(f'🔴 Paper-selg {ticker}', key=f'sell_v4_{_panel_key}', use_container_width=True, disabled=sell_disabled):
            ok, msg = paper_sell(ticker, order_price, 'Mobil ordrepanel v4')
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)

    if not position:
        st.caption('Selg-knappen er deaktivert fordi du ikke har åpen paper-posisjon i denne aksjen.')
    st.markdown('</div>', unsafe_allow_html=True)


def render_trades_panel_v3(ticker):
    portfolio = load_portfolio()
    rows = _trade_rows_for_ticker(portfolio, ticker)

    st.markdown("### 📜 Trades")
    if not rows:
        st.info("Ingen paper trades for denne aksjen ennå.")
        return

    buy_count = sum(1 for r in rows if str(r.get("Type", "")).upper() == "BUY")
    sell_count = sum(1 for r in rows if str(r.get("Type", "")).upper() == "SELL")
    total_amount = sum(_safe_float(r.get("Beløp", 0)) for r in rows)

    c1, c2, c3 = st.columns(3)
    c1.metric("Kjøp", buy_count)
    c2.metric("Salg", sell_count)
    c3.metric("Omsatt", f"{total_amount:,.0f}".replace(",", " "))

    df = pd.DataFrame(rows[-12:][::-1])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Viser de 12 siste handlene for valgt aksje.")


def render_info_panel_v3(ticker, price, currency, decision, item, technical_context):
    portfolio = load_portfolio()
    position = _get_position_for_ticker(portfolio, ticker)
    metrics = _position_metrics(position, price)

    st.markdown("### ℹ️ Informasjon")

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Siste pris", _fmt_price(price, currency))
    i2.metric("Score", item.get("score", decision.get("decision_score", "N/A")))
    i3.metric("Confidence", f"{int(decision.get('confidence', 0) or 0)}%")
    i4.metric("Risiko", decision.get("risk", "N/A"))

    j1, j2, j3, j4 = st.columns(4)
    j1.metric("RSI", f"{float(technical_context.get('rsi')):.1f}" if isinstance(technical_context.get("rsi"), (int, float)) else "N/A")
    j2.metric("Trend", technical_context.get("trend") or technical_context.get("trend_text") or "N/A")
    j3.metric("MACD", technical_context.get("macd_signal") or technical_context.get("macd") or "N/A")
    j4.metric("Posisjonsverdi", _fmt_price(metrics.get("value_now", 0), currency) if position else "N/A")

    reasons = decision.get("reasons", []) or []
    warnings = decision.get("warnings", []) or []

    with st.expander("Hvorfor signalet?", expanded=True):
        if reasons:
            for r in reasons[:8]:
                st.success(str(r))
        else:
            st.caption("Ingen detaljer tilgjengelig.")

    with st.expander("Varsler / risiko", expanded=bool(warnings)):
        if warnings:
            for w in warnings[:8]:
                st.warning(str(w))
        else:
            st.caption("Ingen ekstra varsler registrert.")

    st.caption("Dette er analyse og paper trading, ikke investeringsråd.")


def render_mobile_analysis_view(item, ticker, label, decision=None, technical_context=None, chart_renderer=None):
    """
    Mobilvennlig analysevisning v2 chart.
    """
    decision = decision or {}
    technical_context = technical_context or {}
    currency = _currency_for_ticker(ticker)

    fallback_df = _clean_ohlcv(item.get("hist"))
    fallback_stats = _latest_stats(fallback_df, item)

    st.markdown(
        """
        <style>
        .mobile-shell {
            background: radial-gradient(circle at top, rgba(37,99,235,0.16), rgba(2,6,23,0.92));
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 16px;
            padding: 10px;
            margin: 6px 0 12px 0;
            box-shadow: 0 14px 34px rgba(0,0,0,0.20);
        }
        .mobile-title-row {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap: 10px;
            flex-wrap: wrap;
        }
        .mobile-ticker {
            font-size: 1.8rem;
            font-weight: 950;
            color: #f8fafc;
            line-height: 1.05;
        }
        .mobile-company {
            color: #94a3b8;
            font-size: 0.95rem;
            margin-top: 4px;
        }
        .mobile-price {
            font-size: 2.15rem;
            font-weight: 950;
            color: #f8fafc;
            text-align: right;
            line-height: 1.05;
        }
        .mobile-change-pos {
            color: #22c55e;
            font-weight: 900;
            text-align: right;
        }
        .mobile-change-neg {
            color: #ef4444;
            font-weight: 900;
            text-align: right;
        }
        .mobile-chip {
            display:inline-block;
            border: 1px solid rgba(148,163,184,0.35);
            background: rgba(15,23,42,0.85);
            border-radius: 10px;
            padding: 6px 9px;
            margin: 3px 5px 3px 0;
            color: #e2e8f0;
            font-weight: 800;
            font-size: 0.80rem;
        }
        .mobile-chip.green {
            border-color: rgba(34,197,94,0.45);
            color: #86efac;
        }
        .mobile-chip.red {
            border-color: rgba(239,68,68,0.45);
            color: #fecaca;
        }
        .mobile-subcard {
            background: rgba(15,23,42,0.72);
            border: 1px solid rgba(148,163,184,0.22);
            border-radius: 12px;
            padding: 9px;
            height: 100%;
        }
        .mobile-subcard .label {
            color:#94a3b8;
            font-size:0.82rem;
            font-weight:800;
        }
        .mobile-subcard .value {
            color:#f8fafc;
            font-size:1.08rem;
            font-weight:950;
            margin-top:3px;
        }
        @media (max-width: 700px) {
            .mobile-shell { padding: 10px; border-radius: 16px; }
            .mobile-price { text-align:left; font-size:1.9rem; }
            .mobile-change-pos, .mobile-change-neg { text-align:left; }
            .mobile-ticker { font-size:1.6rem; }
        }

        .pro-terminal-head {
            display:flex;
            justify-content:space-between;
            align-items:flex-start;
            gap:10px;
            background:rgba(2,6,23,0.58);
            border:1px solid rgba(148,163,184,0.20);
            border-radius:14px;
            padding:10px;
            margin-bottom:8px;
        }
        .pro-symbol-row {
            display:flex;
            flex-wrap:wrap;
            align-items:center;
            gap:6px;
        }
        .pro-symbol {
            color:#f8fafc;
            font-weight:950;
            font-size:1.55rem;
            letter-spacing:0.02em;
        }
        .pro-market {
            color:#93c5fd;
            font-weight:850;
            font-size:0.78rem;
            padding:4px 7px;
            border:1px solid rgba(147,197,253,0.35);
            border-radius:999px;
        }
        .pro-badge {
            color:#e2e8f0;
            background:rgba(15,23,42,0.95);
            border:1px solid rgba(148,163,184,0.28);
            border-radius:999px;
            padding:4px 8px;
            font-size:0.74rem;
            font-weight:900;
        }
        .pro-badge.green {
            color:#bbf7d0;
            border-color:rgba(34,197,94,0.55);
            background:rgba(22,101,52,0.28);
        }
        .pro-badge.red {
            color:#fecaca;
            border-color:rgba(239,68,68,0.55);
            background:rgba(127,29,29,0.28);
        }
        .pro-company {
            color:#94a3b8;
            font-size:0.82rem;
            margin-top:5px;
        }
        .pro-mini-line {
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            color:#cbd5e1;
            font-size:0.76rem;
            margin-top:6px;
        }
        .pro-price {
            color:#f8fafc;
            font-size:2.05rem;
            line-height:1.0;
            font-weight:950;
            text-align:right;
        }
        .pro-change {
            text-align:right;
            font-size:0.85rem;
            font-weight:900;
            margin-top:5px;
            color:#cbd5e1;
        }
        .pro-change.green { color:#22c55e; }
        .pro-change.red { color:#ef4444; }
        .pro-stat-grid {
            display:grid;
            grid-template-columns: repeat(4, minmax(0,1fr));
            gap:7px;
            margin:7px 0 8px 0;
        }
        .pro-stat {
            background:rgba(15,23,42,0.66);
            border:1px solid rgba(148,163,184,0.18);
            border-radius:12px;
            padding:8px 9px;
            min-height:54px;
        }
        .pro-stat span {
            display:block;
            color:#94a3b8;
            font-size:0.72rem;
            font-weight:800;
        }
        .pro-stat b {
            display:block;
            color:#f8fafc;
            font-size:0.98rem;
            margin-top:3px;
        }
        .pro-action-card {
            position: sticky;
            bottom: 0;
            z-index: 20;
            background:rgba(2,6,23,0.96);
            backdrop-filter: blur(8px);
            border:1px solid rgba(148,163,184,0.25);
            border-radius:14px;
            padding:10px;
            margin-top:8px;
        }
        .pro-section-title {
            font-size:0.92rem;
            font-weight:950;
            margin:10px 0 6px 0;
            color:#f8fafc;
        }
        @media (max-width: 700px) {
            .pro-terminal-head { flex-direction:column; padding:9px; }
            .pro-price { text-align:left; font-size:1.85rem; }
            .pro-change { text-align:left; }
            .pro-stat-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
            .pro-symbol { font-size:1.35rem; }
        }


        /* CONTROLS_FIX_V1: fix dark/black blob on first multiselect chip */
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div[role="button"] {
            box-shadow: none !important;
        }
        div[data-baseweb="tag"] {
            background: #ef4444 !important;
            color: #ffffff !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255,255,255,0.25) !important;
            box-shadow: none !important;
        }
        div[data-baseweb="tag"] span {
            color: #ffffff !important;
        }
        div[data-baseweb="tag"] svg {
            color: #ffffff !important;
            fill: #ffffff !important;
        }
        div[data-baseweb="select"] input {
            color: #f8fafc !important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="pro-section-title">Tidsvalg</div>', unsafe_allow_html=True)
    timeframe = st.session_state.get(f"mobile_timeframe_{label}_{ticker}", "1d")
    tf_cols = st.columns(5)
    for tf, col in zip(["1m", "15m", "1h", "4h", "1d"], tf_cols):
        with col:
            if st.button(tf, key=f"tf_{label}_{ticker}_{tf}", use_container_width=True):
                st.session_state[f"mobile_timeframe_{label}_{ticker}"] = tf
                timeframe = tf
                st.rerun()

    st.caption("Velg chart-type og indikatorer. Synlige indikatorer er aktive; X fjerner dem. Reset/Standard/Full legger dem raskt tilbake.")

    chart_df = fetch_timeframe_data(ticker, timeframe)
    if chart_df.empty:
        chart_df = fallback_df

    stats = _latest_stats(chart_df, item)
    price = stats.get("price") if stats.get("price") is not None else fallback_stats.get("price")
    change_pct = stats.get("change_pct")
    change_class = "mobile-change-pos" if (change_pct or 0) >= 0 else "mobile-change-neg"

    company = item.get("name") or item.get("company") or item.get("longName") or ""
    signal_text = str(decision.get("decision", "HOLD / WAIT"))
    signal_emoji = decision.get("emoji", "⚪")
    confidence = int(decision.get("confidence", 0) or 0)
    score = item.get("score", decision.get("decision_score", "N/A"))
    rsi = technical_context.get("rsi", None)
    rsi_txt = f"{float(rsi):.1f}" if isinstance(rsi, (int, float)) else "N/A"

    st.markdown('<div class="mobile-shell">', unsafe_allow_html=True)

    render_pro_terminal_header(
        ticker=ticker,
        company=company,
        label=label,
        price=price,
        currency=currency,
        change_pct=change_pct,
        stats=stats,
        decision=decision,
        item=item,
        technical_context=technical_context,
    )

    st.markdown('<div class="pro-section-title">Tidsvalg</div>', unsafe_allow_html=True)

    preset_default = render_pro_preset_bar(ticker, label, timeframe)

    chart_type = st.radio(
        "Chart-type",
        ["Candles", "Line", "Area"],
        horizontal=True,
        key=f"chart_type_{label}_{ticker}_{timeframe}",
        help="Candles = kandelvisning. Line = rask linjevisning. Area = linje med fyll.",
    )

    indicator_key = f"mobile_indicators_{label}_{ticker}_{timeframe}"
    reset_cols = st.columns(3)
    with reset_cols[0]:
        if st.button("↩️ Reset indikatorer", key=f"reset_ind_{label}_{ticker}_{timeframe}", use_container_width=True):
            st.session_state[indicator_key] = preset_default
            st.rerun()
    with reset_cols[1]:
        if st.button("✅ Standard", key=f"std_ind_{label}_{ticker}_{timeframe}", use_container_width=True):
            st.session_state[indicator_key] = ["MA", "VOL", "KANAL"]
            st.rerun()
    with reset_cols[2]:
        if st.button("⚡ Full", key=f"full_ind_{label}_{ticker}_{timeframe}", use_container_width=True):
            st.session_state[indicator_key] = ["MA", "EMA", "BOLL", "SAR", "VWAP", "KANAL", "VOL", "MACD", "RSI", "ADX"]
            st.rerun()

    indicators = st.multiselect(
        "Indikatorer",
        ["MA", "EMA", "BOLL", "SAR", "VWAP", "KANAL", "VOL", "MACD", "KDJ", "RSI", "ATR", "OBV", "ADX"],
        default=preset_default,
        key=indicator_key,
        help="Synlig i feltet = aktiv i grafen. X fjerner indikatoren. Bruk Reset/Standard/Full for å legge tilbake raskt.",
    )

    _render_indicator_snapshot(chart_df, indicators, currency=currency)
    render_chart_help()
    fig = build_mobile_chart(chart_df, ticker, timeframe, indicators, chart_type=chart_type)
    if fig is not None:
        # Streamlit trenger unik key for hver Plotly-graf.
        # Uten key kan to like grafer få samme auto-ID og gi StreamlitDuplicateElementId.
        _indicator_key = "_".join([str(x) for x in indicators]) if indicators else "none"
        _chart_key = f"mobile_chart_v3_{label}_{ticker}_{timeframe}_{chart_type}_{_indicator_key}".replace(" ", "_").replace("/", "_").replace(".", "_")

        st.plotly_chart(
            fig,
            use_container_width=True,
            config=CHART_CONFIG,
            key=_chart_key,
        )
    else:
        st.warning("Fant ikke nok kursdata til candlestick-graf.")

    panel_choice = _render_mobile_section_picker(key_prefix=f"{label}_{ticker}_{timeframe}")

    if panel_choice == "Marked":
        render_overview_panel_v4(ticker, price, currency, confidence, decision, item, technical_context, key_prefix=f'{label}_{ticker}_{timeframe}')
    elif panel_choice == "Ordre":
        render_trading_panel_v3(ticker, price, currency, confidence, decision, item, key_prefix=f'{label}_{ticker}_{timeframe}')
    elif panel_choice == "Trades":
        render_trades_panel_v3(ticker)
    else:
        render_info_panel_v3(ticker, price, currency, decision, item, technical_context)

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "timeframe": timeframe,
        "chart_df": chart_df,
        "price": price,
        "volume": stats.get("volume"),
    }
