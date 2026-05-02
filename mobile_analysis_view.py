
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

TIMEFRAME_CONFIG = {
    "1m": {"period": "1d", "interval": "1m", "max_points": 390},
    "15m": {"period": "5d", "interval": "15m", "max_points": 260},
    "1h": {"period": "1mo", "interval": "1h", "max_points": 260},
    "4h": {"period": "3mo", "interval": "1h", "max_points": 260},
    "1d": {"period": "1y", "interval": "1d", "max_points": 260},
}

CHART_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
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


@st.cache_data(ttl=180, show_spinner=False)
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


def build_mobile_chart(df, ticker, timeframe, indicators):
    df = _clean_ohlcv(df)
    if df.empty:
        return None

    cfg = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1d"])
    max_points = cfg.get("max_points", 260)
    if len(df) > max_points:
        df = df.tail(max_points)

    indicators = indicators or ["MA", "VOL"]
    rows = 2
    row_titles = ["Pris", "Volum"]
    extra_rows = []

    if "MACD" in indicators:
        extra_rows.append("MACD")
    if "RSI" in indicators:
        extra_rows.append("RSI")
    if "KDJ" in indicators:
        extra_rows.append("KDJ")

    rows += len(extra_rows)
    row_titles += extra_rows

    if rows == 2:
        row_heights = [0.74, 0.26]
        height = 560
    elif rows == 3:
        row_heights = [0.60, 0.20, 0.20]
        height = 660
    elif rows == 4:
        row_heights = [0.52, 0.16, 0.16, 0.16]
        height = 760
    else:
        row_heights = [0.46, 0.14, 0.13, 0.13, 0.14]
        height = 850

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.025,
        subplot_titles=row_titles,
        specs=[[{"secondary_y": False}] for _ in range(rows)],
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Candles",
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
            increasing_fillcolor="#22c55e",
            decreasing_fillcolor="#ef4444",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Open: %{open:.2f}<br>"
                "High: %{high:.2f}<br>"
                "Low: %{low:.2f}<br>"
                "Close: %{close:.2f}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    fig = _add_main_indicators(fig, df, indicators)

    vol_colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="VOL",
            marker=dict(color=vol_colors),
            opacity=0.75,
            hovertemplate="<b>Volum</b><br>%{x}<br>%{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    current_row = 3

    if "MACD" in indicators:
        macd, macd_signal, macd_hist = calculate_macd(df)
        hist_colors = ["#22c55e" if float(v or 0) >= 0 else "#ef4444" for v in macd_hist.fillna(0)]
        fig.add_trace(go.Bar(x=df.index, y=macd_hist, name="MACD hist", marker=dict(color=hist_colors), opacity=0.55), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=macd, name="MACD", mode="lines", line=dict(color="#3b82f6", width=1.5)), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=macd_signal, name="Signal", mode="lines", line=dict(color="#ef4444", width=1.3)), row=current_row, col=1)
        current_row += 1

    if "RSI" in indicators:
        rsi = calculate_rsi(df)
        fig.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI", mode="lines", line=dict(color="#a78bfa", width=1.6)), row=current_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(239,68,68,0.75)", row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="rgba(34,197,94,0.75)", row=current_row, col=1)
        fig.update_yaxes(range=[0, 100], row=current_row, col=1)
        current_row += 1

    if "KDJ" in indicators:
        k, d, j = calculate_kdj(df)
        fig.add_trace(go.Scatter(x=df.index, y=k, name="K", mode="lines", line=dict(color="#3b82f6", width=1.4)), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=d, name="D", mode="lines", line=dict(color="#f59e0b", width=1.4)), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=j, name="J", mode="lines", line=dict(color="#e879f9", width=1.2)), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="rgba(239,68,68,0.65)", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="rgba(34,197,94,0.65)", row=current_row, col=1)

    last_price = float(df["Close"].dropna().iloc[-1])
    last_x = df.index[-1]
    fig.add_hline(y=last_price, line_dash="dot", line_color="rgba(34,197,94,0.75)", row=1, col=1)
    fig.add_annotation(
        x=last_x,
        y=last_price,
        text=_fmt_price(last_price),
        showarrow=False,
        xanchor="left",
        yanchor="middle",
        bgcolor="rgba(34,197,94,0.85)",
        bordercolor="#22c55e",
        borderwidth=1,
        font=dict(color="white", size=12),
        row=1,
        col=1,
    )

    fig.update_layout(
        title=f"{ticker} · {timeframe}",
        template="plotly_dark",
        height=height,
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        margin=dict(l=8, r=48, t=54, b=28),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        dragmode="pan",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0,
            bgcolor="rgba(7,17,31,0.75)",
        ),
    )

    for i in range(1, rows + 1):
        fig.update_yaxes(side="right", row=i, col=1, gridcolor="rgba(148,163,184,0.12)")
        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", row=i, col=1, gridcolor="rgba(148,163,184,0.10)")
        fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", row=i, col=1)

    return fig


def render_chart_help():
    st.caption("Graf: dra for pan, bruk musehjul/pinch for zoom, dobbelttrykk for reset. Velg flere indikatorer for egne paneler.")





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


def render_trading_panel_v3(ticker, price, currency, confidence, decision, item, key_prefix=''):
    """
    Step 3 trading panel.
    Bruker samme paper_buy/paper_sell som resten av systemet.
    Endrer ikke auto-buy/Cron.
    """
    _panel_key = _safe_key("order_panel_v3", key_prefix, ticker)
    portfolio = load_portfolio()
    position = _get_position_for_ticker(portfolio, ticker)
    metrics = _position_metrics(position, price)
    price = _safe_float(price)

    try:
        stop_loss, take_profit, trailing_stop = calc_levels(price)
    except Exception:
        stop_loss, take_profit, trailing_stop = None, None, None

    st.markdown("### 🧾 Trading-panel")
    st.caption("Dette er paper trading. Panelet bruker samme paper_buy/paper_sell som auto-motoren.")

    pos_cols = st.columns(4)
    pos_cols[0].metric("Åpen posisjon", "Ja" if position else "Nei")
    pos_cols[1].metric("Antall", f"{metrics.get('shares', 0):.4f}" if position else "0")
    pos_cols[2].metric("Inngang", _fmt_price(metrics.get("entry"), currency) if position else "N/A")
    pos_cols[3].metric(
        "P/L",
        _fmt_price(metrics.get("pnl", 0), currency) if position else "N/A",
        delta=f"{metrics.get('pnl_pct', 0):+.2f}%" if position else None,
    )

    risk_cols = st.columns(3)
    risk_cols[0].metric("Stop-loss", _fmt_price(stop_loss, currency) if stop_loss else "N/A")
    risk_cols[1].metric("Take-profit", _fmt_price(take_profit, currency) if take_profit else "N/A")
    risk_cols[2].metric("Trailing stop", _fmt_price(trailing_stop, currency) if trailing_stop else "N/A")

    st.markdown("#### Ordre")
    mode = st.radio(
        "Ordretype",
        ["Kjøp for beløp", "Kjøp antall", "Selg antall"],
        horizontal=True,
        key=f"order_mode_v3_{_panel_key}",
    )

    default_cash = _safe_float(portfolio.get("cash", 0))
    c1, c2 = st.columns(2)

    with c1:
        order_price = st.number_input(
            f"Pris ({currency})",
            min_value=0.0,
            value=float(price or 0),
            step=0.1,
            key=f"order_price_v3_{_panel_key}",
        )

    with c2:
        if mode == "Kjøp for beløp":
            default_amount = min(max(default_cash * 0.10, 1000), default_cash) if default_cash else 1000
            amount = st.number_input(
                f"Beløp ({currency})",
                min_value=0.0,
                value=float(round(default_amount, 2)),
                step=500.0,
                key=f"order_amount_v3_{_panel_key}",
            )
            qty = amount / order_price if order_price else 0
        else:
            max_sell = metrics.get("shares", 0) if position else 100.0
            qty = st.number_input(
                "Antall aksjer",
                min_value=0.0,
                value=float(min(10.0, max_sell) if max_sell else 10.0),
                step=1.0,
                key=f"order_qty_v3_{_panel_key}",
            )
            amount = qty * order_price

    st.caption(
        f"Estimert antall: {qty:.4f} · Estimert verdi: {_fmt_price(amount, currency)} · "
        f"Cash: {_fmt_price(default_cash, currency)}"
    )

    signal_text = str(decision.get("decision", "HOLD / WAIT"))
    risk = decision.get("risk", "N/A")
    score = item.get("score", decision.get("decision_score", "N/A"))

    st.markdown(
        f"""
        <div style="background:rgba(15,23,42,0.75); border:1px solid rgba(148,163,184,0.25); border-radius:14px; padding:12px; margin:8px 0;">
            <b>Ordregrunnlag</b><br>
            Signal: <b>{signal_text}</b> · Confidence: <b>{confidence}%</b> · Score: <b>{score}</b> · Risiko: <b>{risk}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns(2)

    with b1:
        buy_disabled = mode == "Selg antall" or order_price <= 0 or amount <= 0
        if st.button(f"🟢 Paper-kjøp {ticker}", key=f"buy_v3_{_panel_key}", use_container_width=True, disabled=buy_disabled):
            ok, msg = paper_buy(ticker, order_price, confidence, "Mobil analysepanel v3")
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)

    with b2:
        sell_disabled = not position or qty <= 0 or order_price <= 0
        if st.button(f"🔴 Paper-selg {ticker}", key=f"sell_v3_{_panel_key}", use_container_width=True, disabled=sell_disabled):
            ok, msg = paper_sell(ticker, order_price, "Mobil analysepanel v3")
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)

    if not position:
        st.caption("Selg-knappen er deaktivert fordi du ikke har åpen paper-posisjon i denne aksjen.")


def render_trades_panel_v3(ticker):
    portfolio = load_portfolio()
    rows = _trade_rows_for_ticker(portfolio, ticker)

    st.markdown("### 📜 Trades")
    if not rows:
        st.info("Ingen paper trades for denne aksjen ennå.")
        return

    df = pd.DataFrame(rows[-30:])
    st.dataframe(df, use_container_width=True, hide_index=True)

    buy_count = sum(1 for r in rows if str(r.get("Type", "")).upper() == "BUY")
    sell_count = sum(1 for r in rows if str(r.get("Type", "")).upper() == "SELL")
    total_amount = sum(_safe_float(r.get("Beløp", 0)) for r in rows)

    c1, c2, c3 = st.columns(3)
    c1.metric("Kjøp", buy_count)
    c2.metric("Salg", sell_count)
    c3.metric("Omsatt", f"{total_amount:,.0f}".replace(",", " "))


def render_info_panel_v3(ticker, price, currency, decision, item, technical_context):
    portfolio = load_portfolio()
    position = _get_position_for_ticker(portfolio, ticker)
    metrics = _position_metrics(position, price)

    st.markdown("### ℹ️ Informasjon")

    i1, i2, i3 = st.columns(3)
    i1.metric("Siste pris", _fmt_price(price, currency))
    i2.metric("Score", item.get("score", decision.get("decision_score", "N/A")))
    i3.metric("Confidence", f"{int(decision.get('confidence', 0) or 0)}%")

    i4, i5, i6 = st.columns(3)
    i4.metric("RSI", f"{float(technical_context.get('rsi')):.1f}" if isinstance(technical_context.get("rsi"), (int, float)) else "N/A")
    i5.metric("Risiko", decision.get("risk", "N/A"))
    i6.metric("Posisjonsverdi", _fmt_price(metrics.get("value_now", 0), currency) if position else "N/A")

    reasons = decision.get("reasons", []) or []
    warnings = decision.get("warnings", []) or []

    if reasons:
        st.markdown("**Hvorfor signalet?**")
        for r in reasons[:5]:
            st.success(str(r))

    if warnings:
        st.markdown("**Varsler / risiko**")
        for w in warnings[:5]:
            st.warning(str(w))

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
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 22px;
            padding: 16px;
            margin: 12px 0 20px 0;
            box-shadow: 0 18px 42px rgba(0,0,0,0.22);
        }
        .mobile-title-row {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap: 12px;
            flex-wrap: wrap;
        }
        .mobile-ticker {
            font-size: 2.0rem;
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
            font-size: 2.4rem;
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
            border-radius: 12px;
            padding: 7px 10px;
            margin: 3px 5px 3px 0;
            color: #e2e8f0;
            font-weight: 800;
            font-size: 0.84rem;
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
            border-radius: 16px;
            padding: 12px;
            height: 100%;
        }
        .mobile-subcard .label {
            color:#94a3b8;
            font-size:0.82rem;
            font-weight:800;
        }
        .mobile-subcard .value {
            color:#f8fafc;
            font-size:1.22rem;
            font-weight:950;
            margin-top:3px;
        }
        @media (max-width: 700px) {
            .mobile-shell { padding: 12px; border-radius: 18px; }
            .mobile-price { text-align:left; font-size:2.0rem; }
            .mobile-change-pos, .mobile-change-neg { text-align:left; }
            .mobile-ticker { font-size:1.8rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    timeframe = st.session_state.get(f"mobile_timeframe_{label}_{ticker}", "1d")
    tf_cols = st.columns(5)
    for tf, col in zip(["1m", "15m", "1h", "4h", "1d"], tf_cols):
        with col:
            if st.button(tf, key=f"tf_{label}_{ticker}_{tf}", use_container_width=True):
                st.session_state[f"mobile_timeframe_{label}_{ticker}"] = tf
                timeframe = tf
                st.rerun()

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
    st.markdown(
        f"""
        <div class="mobile-title-row">
            <div>
                <div class="mobile-ticker">{ticker} ⭐</div>
                <div class="mobile-company">{company}</div>
                <span class="mobile-chip green">{label}</span>
                <span class="mobile-chip">Analyse v2</span>
            </div>
            <div>
                <div class="mobile-price">{_fmt_price(price, currency)}</div>
                <div class="{change_class}">{_fmt_pct(change_pct)} · valgt periode</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(
            f"<div class='mobile-subcard'><div class='label'>24t høy</div><div class='value'>{_fmt_price(stats.get('high'), currency)}</div></div>",
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"<div class='mobile-subcard'><div class='label'>24t lav</div><div class='value'>{_fmt_price(stats.get('low'), currency)}</div></div>",
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"<div class='mobile-subcard'><div class='label'>Volum</div><div class='value'>{_fmt_volume(stats.get('volume'))}</div></div>",
            unsafe_allow_html=True,
        )

    signal_class = "green" if ("BUY" in signal_text.upper() or "KJØP" in signal_text.upper()) else "red" if ("SELL" in signal_text.upper() or "SALG" in signal_text.upper()) else ""
    st.markdown(
        f"""
        <div style="margin-top:12px;">
            <span class="mobile-chip {signal_class}">{signal_emoji} Signal: {signal_text}</span>
            <span class="mobile-chip">Score: {score}</span>
            <span class="mobile-chip green">Confidence: {confidence}%</span>
            <span class="mobile-chip">RSI: {rsi_txt}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    indicators = st.multiselect(
        "Indikatorer",
        ["MA", "EMA", "BOLL", "SAR", "VOL", "MACD", "KDJ", "RSI"],
        default=["MA", "VOL"],
        key=f"mobile_indicators_{label}_{ticker}",
        help="Velg indikatorer. MACD, RSI og KDJ får egne paneler under volum.",
    )

    render_chart_help()
    fig = build_mobile_chart(chart_df, ticker, timeframe, indicators)
    if fig is not None:
        # Streamlit trenger unik key for hver Plotly-graf.
        # Uten key kan to like grafer få samme auto-ID og gi StreamlitDuplicateElementId.
        _indicator_key = "_".join([str(x) for x in indicators]) if indicators else "none"
        _chart_key = f"mobile_chart_v3_{label}_{ticker}_{timeframe}_{_indicator_key}".replace(" ", "_").replace("/", "_").replace(".", "_")

        st.plotly_chart(
            fig,
            use_container_width=True,
            config=CHART_CONFIG,
            key=_chart_key,
        )
    else:
        st.warning("Fant ikke nok kursdata til candlestick-graf.")

    order_tab, trades_tab, info_tab = st.tabs(["Ordre", "Trades", "Informasjon"])

    with order_tab:
        render_trading_panel_v3(ticker, price, currency, confidence, decision, item, key_prefix=f'{label}_{ticker}_{timeframe}')

    with trades_tab:
        render_trades_panel_v3(ticker)

    with info_tab:
        render_info_panel_v3(ticker, price, currency, decision, item, technical_context)

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "timeframe": timeframe,
        "chart_df": chart_df,
        "price": price,
        "volume": stats.get("volume"),
    }
