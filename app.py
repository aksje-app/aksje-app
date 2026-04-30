
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from paper_store import load_portfolio, reset_portfolio, storage_status
from trading_engine import auto_trade, portfolio_value, calc_levels
from analysis_engine import analyze

st.set_page_config(page_title="AI Aksje Analyzer Pro", layout="wide")

# -------------------------
# READABLE PRO CSS
# -------------------------
st.markdown("""
<style>
:root {
    --bg: #f5f7fb;
    --panel: #ffffff;
    --card: #ffffff;
    --text: #111827;
    --muted: #4b5563;
    --border: #d6dce8;
    --blue: #2563eb;
    --green: #059669;
    --red: #dc2626;
    --orange: #d97706;
}
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--text) !important;
}
.block-container {
    max-width: 1200px;
    padding-top: 1.5rem;
}
section[data-testid="stSidebar"] {
    background: #0b1220 !important;
    color: #f8fafc !important;
}
section[data-testid="stSidebar"] * {
    color: #f8fafc !important;
}
h1, h2, h3, h4, h5, h6, p, span, label, div {
    color: var(--text);
}
[data-testid="stMetric"] {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}
[data-testid="stMetricLabel"] p {
    color: var(--muted) !important;
    font-weight: 700;
}
[data-testid="stMetricValue"] {
    color: var(--text) !important;
}
.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.08);
    margin-bottom: 12px;
}
.good { color: var(--green) !important; font-weight: 900; }
.bad { color: var(--red) !important; font-weight: 900; }
.warn { color: var(--orange) !important; font-weight: 900; }
.muted { color: var(--muted) !important; }
.stButton>button {
    background: #ffffff !important;
    color: #111827 !important;
    border: 1px solid #9ca3af !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
}
.stButton>button:hover {
    border-color: var(--blue) !important;
    color: var(--blue) !important;
}
div[data-testid="stDataFrame"] {
    background: white !important;
    border-radius: 12px;
    border: 1px solid var(--border);
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# DATA
# -------------------------
WATCHLIST = [
    {"ticker": "NHY.OL", "price": 101.80, "signal": "BUY", "confidence": 80, "score": 8.0, "market": "Norge"},
    {"ticker": "GOOGL", "price": 349.94, "signal": "BUY", "confidence": 76, "score": 7.67, "market": "USA"},
    {"ticker": "AAPL", "price": 190.10, "signal": "BUY", "confidence": 75, "score": 7.5, "market": "USA"},
    {"ticker": "YAR.OL", "price": 531.60, "signal": "BUY", "confidence": 72, "score": 7.1, "market": "Norge"},
    {"ticker": "VOLV-B.ST", "price": 319.10, "signal": "HOLD", "confidence": 73, "score": 7.3, "market": "Sverige"},
    {"ticker": "EQNR.OL", "price": 369.00, "signal": "HOLD", "confidence": 60, "score": 6.6, "market": "Norge"},
    {"ticker": "MSFT", "price": 412.20, "signal": "HOLD", "confidence": 64, "score": 6.4, "market": "USA"},
    {"ticker": "NVDA", "price": 210.93, "signal": "HOLD", "confidence": 63, "score": 6.3, "market": "USA"},
    {"ticker": "ERIC-B.ST", "price": 108.35, "signal": "HOLD", "confidence": 62, "score": 6.2, "market": "Sverige"},
    {"ticker": "AMZN", "price": 258.77, "signal": "HOLD", "confidence": 61, "score": 6.1, "market": "USA"},
]

latest_prices = {x["ticker"]: x["price"] for x in WATCHLIST}

# -------------------------
# SIDEBAR
# -------------------------
st.sidebar.title("⚙️ Kontrollpanel")
st.sidebar.caption(f"Lagring: {storage_status()}")

if st.sidebar.button("Nullstill paper portfolio", key="reset_portfolio_sidebar"):
    reset_portfolio(100000)
    st.sidebar.success("Paper portfolio nullstilt")

st.sidebar.markdown("---")
st.sidebar.markdown("### Markeder")
show_all = st.sidebar.checkbox("Alle", value=True)
show_usa = st.sidebar.checkbox("USA", value=True)
show_no = st.sidebar.checkbox("Norge", value=True)
show_se = st.sidebar.checkbox("Sverige", value=True)

# -------------------------
# HEADER
# -------------------------
st.title("📊 AI Aksje Analyzer Pro")
st.caption("Recovery Pro: lesbar UI, teknisk analyse, RSI-boks, trendkanal, paper trading og Top Picks.")

portfolio = load_portfolio()
total_value = portfolio_value(portfolio, latest_prices)
start_cash = 100000
return_pct = ((total_value - start_cash) / start_cash * 100) if start_cash else 0

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Cash", f"{portfolio['cash']:,.0f} kr")
m2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
m3.metric("Avkastning", f"{return_pct:.2f}%")
m4.metric("Åpne posisjoner", len(portfolio["positions"]))
m5.metric("Handler", len(portfolio["trades"]))

# -------------------------
# TOP PICKS
# -------------------------
st.markdown("## 🔥 Top Picks / Beste kjøp nå")

filtered = []
for x in WATCHLIST:
    if show_all or (x["market"] == "USA" and show_usa) or (x["market"] == "Norge" and show_no) or (x["market"] == "Sverige" and show_se):
        filtered.append(x)
filtered = sorted(filtered, key=lambda x: x["score"], reverse=True)

cols = st.columns(3)
for i, item in enumerate(filtered[:9]):
    with cols[i % 3]:
        signal_class = "good" if item["signal"] == "BUY" else "bad" if item["signal"] == "SELL" else "warn"
        st.markdown(
            f"""
            <div class="card">
                <h3>{item['ticker']}</h3>
                <div class="{signal_class}">{item['signal']} · Score {item['score']}/10</div>
                <p><b>Kurs:</b> {item['price']}</p>
                <p class="muted">Confidence: {item['confidence']}% · {item['market']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        if c1.button("Analyser", key=f"analyze_{item['ticker']}_{i}"):
            st.session_state["selected_ticker"] = item["ticker"]
        if c2.button("Trade", key=f"trade_{item['ticker']}_{i}"):
            ok, msg = auto_trade(item["ticker"], item["price"], item["signal"], item["confidence"])
            st.success(msg) if ok else st.warning(msg)

# -------------------------
# POSITIONS
# -------------------------
st.markdown("---")
st.markdown("## 📌 Åpne posisjoner")

if portfolio["positions"]:
    rows = []
    for t, pos in portfolio["positions"].items():
        last = latest_prices.get(t, pos.get("last_price", pos["entry_price"]))
        entry = float(pos["entry_price"])
        pnl_pct = ((last - entry) / entry * 100) if entry else 0
        pnl_kr = (last - entry) * float(pos["shares"])
        sl, tp, tr = calc_levels(entry, pos.get("highest_price", entry))
        rows.append({
            "Ticker": t,
            "Kjøpt": round(entry, 2),
            "Siste": round(last, 2),
            "Stop loss": sl,
            "Take profit": tp,
            "Trailing stop": tr,
            "Antall": round(pos["shares"], 6),
            "PnL %": round(pnl_pct, 2),
            "PnL kr": round(pnl_kr, 2),
            "Status": "🟢 gevinst" if pnl_pct >= 0 else "🔴 tap",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("Ingen åpne posisjoner.")

# -------------------------
# INTERACTIVE TECH ANALYSIS
# -------------------------
st.markdown("## 📊 Interaktiv teknisk analyse")

all_tickers = [x["ticker"] for x in WATCHLIST]
default = st.session_state.get("selected_ticker", all_tickers[0])
if default not in all_tickers:
    default = all_tickers[0]

selected = st.selectbox("Velg aksje", all_tickers, index=all_tickers.index(default))
item = next(x for x in WATCHLIST if x["ticker"] == selected)
a = analyze(selected, item["price"])

a1, a2, a3, a4, a5 = st.columns(5)
a1.metric("Signal", item["signal"])
a2.metric("Score", f"{item['score']}/10")
a3.metric("Kurs", a["current"])
a4.metric("Confidence", f"{item['confidence']}%")
a5.metric("RSI", f"{a['rsi']}")

st.markdown("### Pris + trendkanal")
hist = a["history"]
fig = go.Figure()
fig.add_trace(go.Scatter(x=hist["date"], y=hist["close"], mode="lines", name="Pris"))
fig.add_trace(go.Scatter(x=hist["date"], y=a["trend_upper"], mode="lines", name="Øvre kanal", line=dict(dash="dash")))
fig.add_trace(go.Scatter(x=hist["date"], y=a["trend_mid"], mode="lines", name="Trend midt", line=dict(dash="dot")))
fig.add_trace(go.Scatter(x=hist["date"], y=a["trend_lower"], mode="lines", name="Nedre kanal", line=dict(dash="dash")))
fig.add_hline(y=a["resistance"], line_dash="dot", annotation_text=f"Motstand {a['resistance']}")
fig.add_hline(y=a["support"], line_dash="dot", annotation_text=f"Støtte {a['support']}")
fig.update_layout(height=430, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig, use_container_width=True)

b1, b2, b3, b4, b5 = st.columns(5)
b1.metric("Trend-status", a["trend_status"])
b2.metric("Kurs i kanal", f"{a['channel_pos']}%")
b3.metric("Støtte", a["support"])
b4.metric("Motstand", a["resistance"])
b5.metric("RSI-status", a["rsi_status"])

st.markdown("### RSI-boks")
rsi_fig = go.Figure()
rsi_series = []
# Smooth synthetic RSI series around current RSI for visual channel
for i in range(len(hist)):
    rsi_series.append(max(0, min(100, a["rsi"] + 12 * __import__("math").sin(i / 10))))
rsi_fig.add_trace(go.Scatter(x=hist["date"], y=rsi_series, mode="lines", name="RSI"))
rsi_fig.add_hline(y=80, line_dash="dot", annotation_text="80 ekstremt")
rsi_fig.add_hline(y=70, line_dash="dash", annotation_text="70 overkjøpt")
rsi_fig.add_hline(y=30, line_dash="dash", annotation_text="30 oversolgt")
rsi_fig.update_yaxes(range=[0, 100])
rsi_fig.update_layout(height=260, template="plotly_white", margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(rsi_fig, use_container_width=True)

# -------------------------
# TRADE LOG
# -------------------------
st.markdown("## 📜 Handelslogg")
if portfolio["trades"]:
    st.dataframe(pd.DataFrame(portfolio["trades"]), use_container_width=True)
else:
    st.info("Ingen handler ennå.")

# -------------------------
# CONTROL
# -------------------------
st.markdown("## 🧪 Trading-kontroll")
c1, c2, c3, c4 = st.columns(4)

if c1.button("BUY GOOGL", key="buy_googl"):
    ok, msg = auto_trade("GOOGL", 349.94, "BUY", 76)
    st.success(msg) if ok else st.warning(msg)

if c2.button("SELL AAPL", key="sell_aapl"):
    ok, msg = auto_trade("AAPL", 190.10, "SELL", 70)
    st.success(msg) if ok else st.warning(msg)

if c3.button("TP AAPL @ 220", key="tp_aapl"):
    ok, msg = auto_trade("AAPL", 220.00, "HOLD", 70)
    st.success(msg) if ok else st.warning(msg)

if c4.button("SL AAPL @ 170", key="sl_aapl"):
    ok, msg = auto_trade("AAPL", 170.00, "HOLD", 70)
    st.success(msg) if ok else st.warning(msg)
