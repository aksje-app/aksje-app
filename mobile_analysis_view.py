
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
from trading_engine import paper_buy, paper_sell
from paper_trading import load_portfolio


TIMEFRAME_CONFIG = {
    "1m": {"period": "1d", "interval": "1m"},
    "15m": {"period": "5d", "interval": "15m"},
    "1h": {"period": "1mo", "interval": "1h"},
    "4h": {"period": "3mo", "interval": "1h"},
    "1d": {"period": "1y", "interval": "1d"},
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
    # yfinance can return MultiIndex in some situations
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

    needed = ["Open", "High", "Low", "Close"]
    for col in needed:
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
        hist = yf.Ticker(ticker).history(period=cfg["period"], interval=cfg["interval"], auto_adjust=False)
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

    # For daily data this is latest session. For intraday this approximates last visible day/session.
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


def _add_indicators(fig, df, indicators):
    close = df["Close"]

    if "MA" in indicators:
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma5, name="MA(5)", mode="lines", line=dict(width=1.6)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ma10, name="MA(10)", mode="lines", line=dict(width=1.4)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ma20, name="MA(20)", mode="lines", line=dict(width=1.4)), row=1, col=1)

    if "EMA" in indicators:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ema12, name="EMA(12)", mode="lines", line=dict(width=1.5, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ema26, name="EMA(26)", mode="lines", line=dict(width=1.5, dash="dot")), row=1, col=1)

    if "BOLL" in indicators:
        bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
        fig.add_trace(go.Scatter(x=df.index, y=bb_upper, name="BOLL øvre", mode="lines", line=dict(width=1, dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=bb_lower, name="BOLL nedre", mode="lines", line=dict(width=1, dash="dash")), row=1, col=1)

    return fig


def build_mobile_chart(df, ticker, timeframe, indicators):
    df = _clean_ohlcv(df)
    if df.empty:
        return None

    max_points = 260
    if len(df) > max_points:
        df = df.tail(max_points)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.03,
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
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
        ),
        row=1,
        col=1,
    )

    fig = _add_indicators(fig, df, indicators)

    vol_colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="VOL",
            marker=dict(color=vol_colors),
            opacity=0.75,
        ),
        row=2,
        col=1,
    )

    if "MACD" in indicators:
        macd, macd_signal, macd_hist = calculate_macd(df)
        fig.add_trace(go.Scatter(x=df.index, y=macd, name="MACD", mode="lines", line=dict(width=1.4)), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=macd_signal, name="Signal", mode="lines", line=dict(width=1.2)), row=2, col=1)

    if "RSI" in indicators:
        rsi = calculate_rsi(df)
        # Normalize RSI to the volume-panel scale so it is visible without a third panel.
        try:
            vmax = max(float(df["Volume"].max()), 1.0)
            rsi_scaled = (rsi / 100.0) * vmax
            fig.add_trace(go.Scatter(x=df.index, y=rsi_scaled, name="RSI (skalert)", mode="lines", line=dict(width=1.4, dash="dot")), row=2, col=1)
        except Exception:
            pass

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
        height=560,
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        margin=dict(l=8, r=42, t=42, b=20),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            bgcolor="rgba(7,17,31,0.75)",
        ),
    )
    fig.update_yaxes(side="right", row=1, col=1)
    fig.update_yaxes(side="right", row=2, col=1)
    return fig


def render_mobile_analysis_view(item, ticker, label, decision=None, technical_context=None, chart_renderer=None):
    """
    Mobilvennlig analysevisning v1.
    Fungerer som toppseksjon i Interaktiv analyse.
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

    st.markdown('<div class="mobile-shell">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="mobile-title-row">
            <div>
                <div class="mobile-ticker">{ticker} ⭐</div>
                <div class="mobile-company">{company}</div>
                <span class="mobile-chip green">{label}</span>
                <span class="mobile-chip">Analyse</span>
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

    st.markdown(
        f"""
        <div style="margin-top:12px;">
            <span class="mobile-chip {'green' if 'BUY' in signal_text.upper() or 'KJØP' in signal_text.upper() else 'red' if 'SELL' in signal_text.upper() or 'SALG' in signal_text.upper() else ''}">
                {signal_emoji} Signal: {signal_text}
            </span>
            <span class="mobile-chip">Score: {score}</span>
            <span class="mobile-chip green">Confidence: {confidence}%</span>
            <span class="mobile-chip">RSI: {float(rsi):.1f if isinstance(rsi, (int, float)) else 'N/A'}</span>
        </div>
        """.replace("{float(rsi):.1f if isinstance(rsi, (int, float)) else 'N/A'}", f"{float(rsi):.1f}" if isinstance(rsi, (int, float)) else "N/A"),
        unsafe_allow_html=True,
    )

    default_indicators = ["MA", "VOL"]
    indicators = st.multiselect(
        "Indikatorer",
        ["MA", "EMA", "BOLL", "SAR", "VOL", "MACD", "KDJ", "RSI"],
        default=[x for x in default_indicators if x in ["MA", "VOL"]],
        key=f"mobile_indicators_{label}_{ticker}",
        help="SAR og KDJ er lagt inn som valg, men full beregning kommer i neste indikatorrunde.",
    )

    unsupported = [x for x in indicators if x in {"SAR", "KDJ"}]
    if unsupported:
        st.caption(f"{', '.join(unsupported)} er valgt, men full beregning kommer i neste indikatorrunde.")

    fig = build_mobile_chart(chart_df, ticker, timeframe, indicators)
    if fig is not None:
        if chart_renderer:
            chart_renderer(fig, key=f"mobile_chart_{label}_{ticker}_{timeframe}_{'_'.join(indicators)}")
        else:
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Fant ikke nok kursdata til candlestick-graf.")

    order_tab, trades_tab, info_tab = st.tabs(["Ordre", "Trades", "Informasjon"])

    with order_tab:
        st.markdown("#### Paper ordre")
        c1, c2 = st.columns(2)
        with c1:
            qty = st.number_input("Antall aksjer", min_value=0.0, value=10.0, step=1.0, key=f"mobile_qty_{label}_{ticker}")
        with c2:
            order_price = st.number_input(
                f"Pris ({currency})",
                min_value=0.0,
                value=float(price or 0),
                step=0.1,
                key=f"mobile_price_{label}_{ticker}",
            )

        est_value = qty * order_price
        st.caption(f"Estimert verdi: {_fmt_price(est_value, currency)}")

        b1, b2 = st.columns(2)
        with b1:
            if st.button(f"🟢 Paper-kjøp {ticker}", key=f"mobile_buy_{label}_{ticker}", use_container_width=True):
                ok, msg = paper_buy(ticker, order_price, confidence, "Mobil analysevisning")
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)
        with b2:
            if st.button(f"🔴 Paper-selg {ticker}", key=f"mobile_sell_{label}_{ticker}", use_container_width=True):
                ok, msg = paper_sell(ticker, order_price, "Mobil analysevisning")
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

    with trades_tab:
        portfolio = load_portfolio()
        trades = portfolio.get("trades", [])
        ticker_trades = [t for t in trades if str(t.get("ticker", "")).upper() == str(ticker).upper()]
        if ticker_trades:
            st.dataframe(pd.DataFrame(ticker_trades[-20:]), use_container_width=True, hide_index=True)
        else:
            st.info("Ingen paper trades for denne aksjen ennå.")

    with info_tab:
        p = load_portfolio()
        positions = p.get("positions", {})
        pos = positions.get(ticker) or positions.get(str(ticker).upper())
        info_cols = st.columns(3)
        info_cols[0].metric("Cash", _fmt_price(p.get("cash", 0), "kr"))
        info_cols[1].metric("Åpen posisjon", "Ja" if pos else "Nei")
        info_cols[2].metric("Portefølje trades", len(p.get("trades", [])))
        if pos:
            st.json(pos, expanded=False)
        st.caption("Dette er paper trading. Ikke investeringsråd.")

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "timeframe": timeframe,
        "chart_df": chart_df,
        "price": price,
        "volume": stats.get("volume"),
    }
