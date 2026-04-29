import os
PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")
st.write("DEBUG TOKEN:", "OK" if PUSHOVER_APP_TOKEN else "MISSING")
st.write("DEBUG USER:", "OK" if PUSHOVER_USER_KEY else "MISSING")
import pandas as pd
import plotly.graph_objects as go
import requests
from streamlit_autorefresh import st_autorefresh

from technical import calculate_rsi, calculate_macd, calculate_bollinger, detect_trend, technical_signal
from patterns import detect_head_shoulders, detect_inverse_head_shoulders, breakout_scanner, build_signal_alerts

from stocks import get_sp500_tickers, get_norwegian_tickers
from analysis import rank_stocks
from backtest_strategy import run_monthly_score_strategy, add_stats
from ipo import get_ipo_calendar
from news import get_news, simple_finance_sentiment
from trading_engine import build_trading_decision, adjusted_score
from strategy_engine import run_strategy, strategy_stats, optimize_strategy

st.set_page_config(page_title="AI Aksje Analyzer Pro", page_icon="📈", layout="wide")
st_autorefresh(interval=300000, key="refresh")

st.markdown("""
<style>
:root {
    --bg-main: #0f172a;
    --bg-sidebar: #020617;
    --bg-card: #111827;
    --bg-card-2: #1e293b;
    --border: #334155;
    --text-main: #f8fafc;
    --text-soft: #cbd5e1;
    --text-muted: #94a3b8;
    --green: #22c55e;
    --yellow: #f59e0b;
    --red: #ef4444;
    --blue: #38bdf8;
}

.stApp {
    background: var(--bg-main);
    color: var(--text-main);
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
    max-width: 1500px;
}

[data-testid="stSidebar"] {
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
}

html, body, [class*="css"], p, span, div {
    color: var(--text-main);
}

h1, h2, h3, h4 {
    color: var(--text-main) !important;
    font-weight: 800 !important;
}

label, [data-testid="stWidgetLabel"] {
    color: var(--text-soft) !important;
    font-weight: 700 !important;
}

.card {
    background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 12px;
    box-shadow: 0 8px 22px rgba(0,0,0,0.22);
}

.small {
    color: var(--text-soft);
    font-size: 0.95rem;
}

.good {
    color: var(--green);
    font-weight: 900;
}

.mid {
    color: var(--yellow);
    font-weight: 900;
}

.bad {
    color: var(--red);
    font-weight: 900;
}

[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid var(--border);
    padding: 16px;
    border-radius: 16px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.18);
}

[data-testid="stMetricLabel"] {
    color: var(--text-soft) !important;
    font-size: 0.95rem !important;
    font-weight: 800 !important;
}

[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-size: 1.75rem !important;
    font-weight: 900 !important;
}

.stAlert {
    border-radius: 14px;
    font-size: 1rem;
}

.stButton > button {
    border-radius: 14px;
    border: 1px solid var(--border);
    background: #0ea5e9;
    color: white;
    font-weight: 800;
    padding: 0.55rem 1rem;
}

.stButton > button:hover {
    background: #0284c7;
    color: white;
    border-color: #7dd3fc;
}

div[data-baseweb="select"] > div {
    background-color: #1e293b !important;
    color: white !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

input, textarea {
    background-color: #1e293b !important;
    color: white !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 14px;
}

hr {
    border-color: var(--border);
}

/* Make Plotly containers easier to read */
.js-plotly-plot .plotly {
    border-radius: 16px;
}

/* Mobile-first improvements */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
        padding-top: 0.75rem;
    }

    h1 {
        font-size: 1.65rem !important;
        line-height: 1.15 !important;
    }

    h2 {
        font-size: 1.35rem !important;
    }

    h3 {
        font-size: 1.15rem !important;
    }

    .card {
        padding: 14px;
        border-radius: 14px;
    }

    [data-testid="stMetric"] {
        padding: 12px;
        border-radius: 13px;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
    }

    .small {
        font-size: 0.85rem;
    }

    .stButton > button {
        width: 100%;
        padding: 0.7rem 1rem;
        font-size: 1rem;
    }
}
</style>
""", unsafe_allow_html=True)


PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")
PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY")

# fallback hvis Render gir tom string
if not PUSHOVER_APP_TOKEN:
    PUSHOVER_APP_TOKEN = None

if not PUSHOVER_USER_KEY:
    PUSHOVER_USER_KEY = None

def send_pushover_alert(message, title="AI Aksje Analyzer"):
    """
    Sender Pushover-varsel.
    Krever Environment Variables:
    - PUSHOVER_APP_TOKEN
    - PUSHOVER_USER_KEY
    """
    if not PUSHOVER_APP_TOKEN or not PUSHOVER_USER_KEY:
        return False, "Mangler PUSHOVER_APP_TOKEN eller PUSHOVER_USER_KEY"

    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_APP_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": title,
                "message": message,
            },
            timeout=10,
        )

        if response.status_code == 200:
            return True, None

        return False, response.text

    except Exception as e:
        return False, str(e)


def maybe_send_signal_alert(ticker, decision):
    """
    Sender kun varsel hvis signalet har endret seg.
    Hindrer spam.
    """
    if "last_signal" not in st.session_state:
        st.session_state.last_signal = {}

    current_signal = decision.get("decision", "UNKNOWN")
    previous_signal = st.session_state.last_signal.get(ticker)

    if previous_signal == current_signal:
        return

    st.session_state.last_signal[ticker] = current_signal

    if current_signal in ["BUY", "SELL / AVOID"]:
        msg = (
            f"{decision.get('emoji', '')} {current_signal}: {ticker}\n"
            f"Confidence: {decision.get('confidence', 'N/A')}%\n"
            f"Signal-score: {decision.get('decision_score', 'N/A')}"
        )
        send_pushover_alert(msg)


def score_color(score):
    if score >= 7: return "good", "🟢"
    if score >= 4: return "mid", "🟡"
    return "bad", "🔴"

def plot_price(hist, title):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Close"))
    fig.update_layout(title=title, template="plotly_dark", height=420, paper_bgcolor="#0b111c", plot_bgcolor="#0b111c")
    return fig


def add_pattern_markers(fig, pattern, name):
    points = pattern.get("points", {}) if pattern else {}
    if not points:
        return fig

    ordered_keys = ["left_shoulder", "head", "right_shoulder"]
    xs = []
    ys = []

    for key in ordered_keys:
        point = points.get(key)
        if point and len(point) == 2:
            xs.append(point[0])
            ys.append(point[1])

    if xs and ys:
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers+lines+text",
            name=name,
            text=["Venstre", "Hode", "Høyre"],
            textposition="top center",
            marker=dict(size=10),
            line=dict(width=3, dash="dash"),
        ))

    return fig


def render_decision_banner(decision, item, adj_score):
    decision_text = decision.get("decision", "HOLD / WAIT")
    emoji = decision.get("emoji", "🟡")
    color = decision.get("color", "orange")

    if decision_text == "BUY":
        st.success(f"{emoji} BUY-signal | Confidence: {decision.get('confidence', 'N/A')}%")
    elif decision_text == "SELL / AVOID":
        st.error(f"{emoji} SELL / AVOID | Confidence: {decision.get('confidence', 'N/A')}%")
    else:
        st.warning(f"{emoji} HOLD / WAIT | Confidence: {decision.get('confidence', 'N/A')}%")

    st.markdown(
        f"""
        <div class="card">
            <h3 style="color:{color}; margin-bottom: 0.4rem;">{emoji} {decision_text}</h3>
            <p style="font-size:1.05rem; margin-bottom:0.2rem;">
                Original score: <b>{item['score']}/10</b> · Pattern-justert score: <b>{adj_score}/10</b>
            </p>
            <p class="small">Dette er analysehjelp, ikke investeringsråd.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_ranking(results, title):
    st.subheader(title)
    if not results:
        st.warning("Fant ingen data.")
        return
    best = results[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Beste aksje", f"{best['ticker']} {best['score']}/10")
    c2.metric("Analyserte", len(results))
    c3.metric("Beste 6m", f"{best['ret_6m']*100:.1f}%")
    c4.metric("Auto-refresh", "5 min")

    for item in results[:10]:
        css, emoji = score_color(item["score"])
        left, right = st.columns([1.2, 2.2])
        with left:
            st.markdown(f"""
            <div class="card">
                <h3>{emoji} {item['ticker']}</h3>
                <div class="{css}" style="font-size:1.25rem;">{item['score']}/10</div>
                <div class="small">{item['name']}</div>
            </div>
            """, unsafe_allow_html=True)
        with right:
            st.progress(min(item["score"] / 10, 1.0))
            st.caption(
                f"1y: {item['ret_1y']*100:.1f}% · "
                f"6m: {item['ret_6m']*100:.1f}% · "
                f"3m: {item['ret_3m']*100:.1f}% · "
                f"Vol: {item['volatility']:.4f} · "
                f"DD: {item['max_drawdown']*100:.1f}%"
            )

def render_analysis(results, label):
    st.subheader("📊 Interaktiv analyse")
    if not results:
        return

    selected = st.selectbox(f"Velg aksje ({label})", [r["ticker"] for r in results], key=f"select_{label}")
    item = next(r for r in results if r["ticker"] == selected)
    df = item["hist"].copy()

    st.plotly_chart(plot_price(df, f"{selected} - prisutvikling"), use_container_width=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score", f"{item['score']}/10")
    m2.metric("P/E", item.get("forward_pe") or item.get("trailing_pe") or "N/A")
    m3.metric("Revenue growth", f"{item['revenue_growth']*100:.1f}%" if isinstance(item.get("revenue_growth"), (int,float)) else "N/A")
    m4.metric("Max drawdown", f"{item['max_drawdown']*100:.1f}%")

    st.markdown("#### 📈 Teknisk analyse")

    rsi = calculate_rsi(df)
    macd, macd_signal, macd_hist = calculate_macd(df)
    bb_ma, bb_upper, bb_lower = calculate_bollinger(df)
    trend = detect_trend(df)

    latest_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
    latest_macd = macd.dropna().iloc[-1] if not macd.dropna().empty else 0
    latest_macd_signal = macd_signal.dropna().iloc[-1] if not macd_signal.dropna().empty else 0
    latest_close = df["Close"].iloc[-1]
    latest_upper = bb_upper.dropna().iloc[-1] if not bb_upper.dropna().empty else latest_close
    latest_lower = bb_lower.dropna().iloc[-1] if not bb_lower.dropna().empty else latest_close

    hs = detect_head_shoulders(df)
    inv_hs = detect_inverse_head_shoulders(df)
    breakout = breakout_scanner(df)
    alerts = build_signal_alerts(latest_rsi, latest_macd, latest_macd_signal, breakout, hs, inv_hs)

    technical_context = {
        "rsi": latest_rsi,
        "macd_bullish": latest_macd > latest_macd_signal,
        "breakout_type": breakout.get("type", "neutral"),
        "head_shoulders_found": hs.get("found", False),
        "inverse_head_shoulders_found": inv_hs.get("found", False),
    }

    decision = build_trading_decision(item, technical_context)
    adj_score = adjusted_score(item, decision)

    # 📱 Send Pushover-varsel hvis BUY/SELL-signalet endrer seg
    maybe_send_signal_alert(selected, decision)

    st.markdown("#### 🤖 Trading engine")
    d1, d2, d3 = st.columns(3)
    d1.metric("Beslutning", f"{decision['emoji']} {decision['decision']}")
    d2.metric("Signal-score", decision["decision_score"])
    d3.metric("Confidence", f"{decision['confidence']}%")

    render_decision_banner(decision, item, adj_score)

    with st.expander("Hvorfor dette signalet?"):
        for reason in decision["reasons"]:
            st.write("•", reason)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("RSI", f"{latest_rsi:.1f}")
    t2.metric("Trend", trend)
    t3.metric("MACD", "Bullish 🟢" if latest_macd > latest_macd_signal else "Bearish 🔴")
    t4.metric("Breakout", breakout.get("signal", "N/A"))

    st.markdown("#### 🔔 Signal alerts")
    for title, desc, kind in alerts:
        if kind == "bullish":
            st.success(f"🟢 {title}: {desc}")
        elif kind == "bearish":
            st.error(f"🔴 {title}: {desc}")
        else:
            st.info(f"⚪ {title}: {desc}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Motstand", breakout.get("resistance", "N/A"))
    c2.metric("Støtte", breakout.get("support", "N/A"))
    c3.metric("Volum boost", breakout.get("volume_boost", "N/A"))

    st.markdown("#### 🧩 Pattern detection")
    p1, p2 = st.columns(2)
    with p1:
        if hs.get("found"):
            st.warning(f"{hs['label']} | confidence: {hs['confidence']}")
        else:
            st.info(hs.get("label", "Ingen pattern"))
    with p2:
        if inv_hs.get("found"):
            st.success(f"{inv_hs['label']} | confidence: {inv_hs['confidence']}")
        else:
            st.info(inv_hs.get("label", "Ingen pattern"))

    fig_ta = go.Figure()
    fig_ta.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Pris", mode="lines"))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_ma, name="BB midt", mode="lines", line=dict(dash="dot")))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_upper, name="BB øvre", mode="lines", line=dict(dash="dot")))
    fig_ta.add_trace(go.Scatter(x=df.index, y=bb_lower, name="BB nedre", mode="lines", line=dict(dash="dot")))

    if breakout.get("support") != "N/A":
        fig_ta.add_hline(y=breakout.get("support"), line_dash="dash", annotation_text="Støtte")
    if breakout.get("resistance") != "N/A":
        fig_ta.add_hline(y=breakout.get("resistance"), line_dash="dash", annotation_text="Motstand")

    if hs.get("found"):
        fig_ta = add_pattern_markers(fig_ta, hs, "Hode/skulder")
    if inv_hs.get("found"):
        fig_ta = add_pattern_markers(fig_ta, inv_hs, "Invertert hode/skulder")

    fig_ta.update_layout(
        title=f"{selected} - Bollinger, støtte/motstand, patterns og breakout",
        template="plotly_dark",
        height=480,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
    )
    st.plotly_chart(fig_ta, use_container_width=True)

    fig_macd = go.Figure()
    fig_macd.add_trace(go.Scatter(x=df.index, y=macd, name="MACD", mode="lines"))
    fig_macd.add_trace(go.Scatter(x=df.index, y=macd_signal, name="Signal", mode="lines"))
    fig_macd.add_trace(go.Bar(x=df.index, y=macd_hist, name="Histogram"))
    fig_macd.update_layout(
        title=f"{selected} - MACD",
        template="plotly_dark",
        height=300,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
    )
    st.plotly_chart(fig_macd, use_container_width=True)

    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI", mode="lines"))
    fig_rsi.add_hline(y=70, line_dash="dash", annotation_text="Overkjøpt")
    fig_rsi.add_hline(y=30, line_dash="dash", annotation_text="Oversolgt")
    fig_rsi.update_layout(
        title=f"{selected} - RSI",
        template="plotly_dark",
        height=260,
        paper_bgcolor="#0b111c",
        plot_bgcolor="#0b111c",
        yaxis=dict(range=[0, 100]),
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

    st.markdown("#### 🧪 Strategi-test (historisk simulering)")

    if st.button(f"Kjør strategi-test for {selected}", key=f"strategy_{label}_{selected}"):

        df_strategy = item["hist"].copy()

        # Legg til indikatorer
        df_strategy["rsi"] = calculate_rsi(df_strategy)
        macd_strategy, signal_strategy, _ = calculate_macd(df_strategy)
        df_strategy["macd"] = macd_strategy
        df_strategy["macd_signal"] = signal_strategy

        value, trades, equity = run_strategy(df_strategy)
        stats = strategy_stats(equity, trades)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Sluttverdi", f"{value:,.0f} kr")
        s2.metric("Total avkastning", f"{stats['total_return']}%")
        s3.metric("Max drawdown", f"{stats['max_drawdown']}%")
        s4.metric("Win rate", f"{stats['win_rate']}%")

        s5, s6, s7 = st.columns(3)
        s5.metric("Antall trades", stats["num_trades"])
        s6.metric("Avg win/loss", f"{stats['avg_win']}% / {stats['avg_loss']}%")
        s7.metric("Profit factor", stats["profit_factor"])

        if equity:
            eq_df = pd.DataFrame(equity, columns=["date", "value"])

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=eq_df["date"],
                y=eq_df["value"],
                mode="lines",
                name="Portefølje"
            ))

            # Marker BUY/SELL punkter på grafen
            if trades:
                buy_x = [t["date"] for t in trades if t["type"] == "BUY"]
                buy_y = [t["value"] for t in trades if t["type"] == "BUY"]
                sell_x = [t["date"] for t in trades if t["type"] == "SELL"]
                sell_y = [t["value"] for t in trades if t["type"] == "SELL"]

                if buy_x:
                    fig_eq.add_trace(go.Scatter(
                        x=buy_x,
                        y=buy_y,
                        mode="markers",
                        name="BUY",
                        marker=dict(size=10, symbol="triangle-up")
                    ))

                if sell_x:
                    fig_eq.add_trace(go.Scatter(
                        x=sell_x,
                        y=sell_y,
                        mode="markers",
                        name="SELL",
                        marker=dict(size=10, symbol="triangle-down")
                    ))

            fig_eq.update_layout(
                title="📈 Strategi utvikling (equity curve)",
                template="plotly_dark",
                height=420,
                paper_bgcolor="#0b111c",
                plot_bgcolor="#0b111c",
            )

            st.plotly_chart(fig_eq, use_container_width=True)

        st.markdown("#### Siste trades")
        if trades:
            st.dataframe(pd.DataFrame(trades[-20:]), use_container_width=True)
        else:
            st.info("Ingen trades ble trigget med disse reglene.")

        st.markdown("#### ⚙️ Strategi-optimalisering")
        st.caption("Tester flere RSI/MACD-varianter og rangerer dem etter avkastning, risiko og win-rate.")

        opt_df = optimize_strategy(df_strategy)

        if opt_df.empty:
            st.warning("Klarte ikke å optimalisere strategien.")
        else:
            st.dataframe(opt_df.head(10), use_container_width=True)

            best = opt_df.iloc[0]
            st.success(
                f"Beste variant: BUY RSI < {best['buy_rsi']}, "
                f"SELL RSI > {best['sell_rsi']}, "
                f"MACD: {best['use_macd']} | "
                f"Return: {best['total_return']}% | "
                f"Max DD: {best['max_drawdown']}%"
            )

    st.markdown("#### 🧠 Score-forklaring")
    parts = item.get("score_parts", {})
    if parts:
        for k, v in parts.items():
            st.progress(float(v))
            st.caption(f"{k}: {v}")

    st.markdown("#### 📰 Nyheter")
    st.caption("For å spare NewsAPI-kall hentes nyheter bare for valgt aksje når du trykker knappen.")

    if not use_news:
        st.info("Nyheter/sentiment er slått av i sidepanelet.")
    elif st.button(f"Hent nyheter for {selected}", key=f"news_btn_{label}_{selected}"):
        articles, error = get_news(selected.replace(".OL", ""), limit=6)

        if error:
            st.warning(f"Nyheter midlertidig utilgjengelig: {error}")
        elif not articles:
            st.info("Ingen relevante nyheter funnet.")
        else:
            live_sentiment = simple_finance_sentiment(articles)
            st.metric("Live nyhets-sentiment", live_sentiment)

            for a in articles:
                st.markdown(
                    f"- **{a.get('title','Uten tittel')}**  \n"
                    f"  <span class='small'>{a.get('source','')} · {a.get('published','')}</span>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Trykk på knappen over for å hente nyheter for valgt aksje.")

def render_ipo():
    st.subheader("🚀 Nye og kommende børsnoteringer")
    ipo_list, error = get_ipo_calendar()
    if error:
        st.info(error)
        return
    if not ipo_list:
        st.info("Fant ingen IPO-data akkurat nå.")
        return
    for ipo in ipo_list[:12]:
        st.markdown(f"**{ipo.get('name','Ukjent selskap')}** ({ipo.get('symbol','N/A')})")
        st.caption(f"{ipo.get('date','Ukjent dato')} · {ipo.get('exchange','Ukjent børs')}")
        st.divider()

def render_strategy_backtest(tickers, label):
    st.subheader("🧪 Smartere strategi-backtest")
    st.caption("Månedlig rebalansering, transaksjonskostnader, drawdown og benchmark.")

    col_a, col_b, col_c = st.columns(3)
    months = col_a.slider("Antall måneder", 6, 36, 24, key=f"months_{label}")
    top_n = col_b.slider("Topp N aksjer", 2, 10, 5, key=f"topn_{label}")
    cost = col_c.slider("Transaksjonskostnad", 0.0, 1.0, 0.2, step=0.1, key=f"cost_{label}") / 100

    use_stop = st.checkbox("Bruk enkel stop-loss", value=False, key=f"stop_{label}")
    stop_loss = st.slider("Stop-loss %", 3, 25, 10, key=f"sl_{label}") / 100 if use_stop else None

    benchmark = "^GSPC" if label == "USA" else "OSEBX.OL"

    if st.button(f"Kjør smartere backtest ({label})"):
        with st.spinner("Kjører backtest..."):
            strategy, bench, error = run_monthly_score_strategy(
                tickers,
                months=months,
                top_n=top_n,
                benchmark=benchmark,
                transaction_cost=cost,
                stop_loss=stop_loss,
            )

        if error:
            st.error(error)
            return

        strategy, stats = add_stats(strategy)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total avkastning", f"{stats['total_return']*100:.1f}%")
        c2.metric("Maks drawdown", f"{stats['max_drawdown']*100:.1f}%")
        c3.metric("Win-rate", f"{stats['win_rate']*100:.0f}%")
        c4.metric("Sharpe-ish", f"{stats['sharpe_like']:.2f}")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=strategy["date"], y=strategy["value"], name="Score-strategi", mode="lines+markers"))
        if not bench.empty:
            fig.add_trace(go.Scatter(x=bench["date"], y=bench["benchmark_value"], name="Benchmark", mode="lines"))
        fig.update_layout(title="Strategi vs benchmark", template="plotly_dark", height=430)
        st.plotly_chart(fig, use_container_width=True)

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=strategy["date"], y=strategy["drawdown"], fill="tozeroy", name="Drawdown"))
        fig_dd.update_layout(title="Drawdown", template="plotly_dark", height=300)
        st.plotly_chart(fig_dd, use_container_width=True)

        st.markdown("#### Valgte aksjer per måned")
        st.dataframe(strategy[["date", "monthly_return", "gross_return", "cost", "selected"]], use_container_width=True)

st.sidebar.title("⚙️ Innstillinger")
st.sidebar.markdown("### 🎨 Visning")
st.sidebar.caption("Mobilvennlig kontrast og større tekst er aktivert.")
st.sidebar.markdown("### 📱 Varsler")
pushover_enabled = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
st.sidebar.write("Pushover:", "✅ Aktiv" if pushover_enabled else "❌ Ikke konfigurert")
if pushover_enabled and st.sidebar.button("Send test-varsel"):
    ok, err = send_pushover_alert("✅ Testvarsel fra AI Aksje Analyzer")
    if ok:
        st.sidebar.success("Testvarsel sendt")
    else:
        st.sidebar.error(f"Feil: {err}")
st.sidebar.caption("Legg PUSHOVER_APP_TOKEN og PUSHOVER_USER_KEY i Render Environment Variables.")

mode = st.sidebar.radio("Marked", ["USA / S&P 500", "Norge / Oslo Børs", "Begge"])
max_count = st.sidebar.slider("Antall aksjer å analysere", 5, 60, 15)
use_news = st.sidebar.checkbox("Bruk nyheter/sentiment", value=True)
search = st.sidebar.text_input("Søk ticker manuelt", placeholder="F.eks. AAPL, EQNR.OL")

st.title("📈 AI Aksje Analyzer Pro")
st.caption("Smartere scoring med momentum, trend, risiko, P/E, kvalitet, vekst, gjeld, nyheter og backtesting.")

if search.strip():
    tickers_us = [search.strip().upper()]
    tickers_no = []
else:
    tickers_us = get_sp500_tickers(limit=max_count)
    tickers_no = get_norwegian_tickers()[:max_count]

tabs = st.tabs(["🇺🇸 USA", "🇳🇴 Norske aksjer", "🚀 IPO", "🧪 Backtesting"])

with tabs[0]:
    if mode in ["USA / S&P 500", "Begge"] or search.strip():
        us_results = rank_stocks(tickers_us, max_count=max_count, use_news=use_news)
        render_ranking(us_results, "🏆 Topp rangerte USA/S&P 500")
        render_analysis(us_results, "USA")
    else:
        st.info("USA er slått av i sidepanelet.")

with tabs[1]:
    if mode in ["Norge / Oslo Børs", "Begge"] and not search.strip():
        no_results = rank_stocks(tickers_no, max_count=max_count, use_news=use_news)
        render_ranking(no_results, "🇳🇴 Topp 10 norske aksjer")
        render_analysis(no_results, "Norge")
    else:
        st.info("Velg Norge eller Begge i sidepanelet.")

with tabs[2]:
    render_ipo()

with tabs[3]:
    bt_market = st.radio("Backtest-marked", ["USA", "Norge"], horizontal=True)
    bt_tickers = tickers_us if bt_market == "USA" else get_norwegian_tickers()[:max_count]
    render_strategy_backtest(bt_tickers, bt_market)
