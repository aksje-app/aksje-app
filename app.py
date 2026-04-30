
import streamlit as st
import pandas as pd

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=15000, key="v6_refresh")
except Exception:
    pass

from paper_store import load_portfolio, reset_portfolio, storage_status
from trading_engine import auto_trade, portfolio_value, calc_levels
from top10_engine import get_top10, find_ticker
from chart_engine import price_chart, rsi_chart

st.set_page_config(page_title="AI Aksje Analyzer Pro", layout="wide")

# ---------------- CSS / OLD PRO LOOK RESTORE ----------------
st.markdown("""
<style>
:root {
    --bg: #07111f;
    --panel: #0f172a;
    --panel2: #111c31;
    --border: rgba(148,163,184,.22);
    --text: #e5e7eb;
    --muted: #94a3b8;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #facc15;
    --blue: #38bdf8;
}
html, body, [class*="css"] {
    background: radial-gradient(circle at top left, #13223c 0%, #07111f 45%, #020617 100%);
    color: var(--text);
}
.block-container { padding-top: 1.2rem; max-width: 1450px; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
    border-right: 1px solid var(--border);
}
h1, h2, h3 { color: #f8fafc; font-weight: 900; letter-spacing: -.02em; }
.pro-hero {
    border: 1px solid var(--border);
    border-radius: 24px;
    padding: 22px 26px;
    background: linear-gradient(135deg, rgba(14,165,233,.16), rgba(34,197,94,.08), rgba(15,23,42,.95));
    box-shadow: 0 20px 50px rgba(0,0,0,.28);
    margin-bottom: 18px;
}
.pro-card {
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 18px;
    background: linear-gradient(180deg, rgba(15,23,42,.98), rgba(17,24,39,.90));
    box-shadow: 0 14px 36px rgba(0,0,0,.22);
    min-height: 162px;
}
.pro-card:hover {
    border-color: rgba(56,189,248,.45);
    box-shadow: 0 18px 42px rgba(56,189,248,.10);
}
.ticker { font-size: 1.45rem; font-weight: 950; color: #f8fafc; }
.price { font-size: 1.35rem; font-weight: 900; margin-top: 4px; }
.muted { color: var(--muted); font-size: .88rem; }
.buy { color: var(--green); font-weight: 950; }
.sell { color: var(--red); font-weight: 950; }
.hold { color: var(--yellow); font-weight: 950; }
.badge {
    display:inline-block; padding:4px 10px; border-radius:999px;
    background:#1e293b; border:1px solid rgba(148,163,184,.28);
    font-size:.82rem; margin-right: 4px;
}
.section-card {
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 18px;
    background: rgba(15,23,42,.76);
    margin-bottom: 18px;
}
hr { border-color: rgba(148,163,184,.18); }
</style>
""", unsafe_allow_html=True)

# ---------------- SIDEBAR ----------------
st.sidebar.title("⚙️ AI Aksje Analyzer")
st.sidebar.caption(f"Lagring: {storage_status()}")

st.sidebar.markdown("### 🔁 Auto trading")
auto_enabled = st.sidebar.toggle("Auto trading aktiv", value=True)
st.sidebar.caption("Cron bruker scanner_worker.py og samme DATABASE_URL.")

st.sidebar.markdown("### 🔔 Varsler")
pushover_enabled = st.sidebar.toggle("Pushover-varsler", value=True)
st.sidebar.caption("Bruker PUSHOVER_APP_TOKEN og PUSHOVER_USER_KEY.")

st.sidebar.markdown("### 🧪 Test / reset")
if st.sidebar.button("Nullstill paper portfolio", key="reset_portfolio_sidebar"):
    reset_portfolio(100000)
    st.sidebar.success("Paper portfolio nullstilt")

st.sidebar.markdown("### 📌 Markeder")
market_filter = st.sidebar.radio("Vis marked", ["Alle", "USA", "Norge", "Sverige"], index=0)

# ---------------- HEADER ----------------
st.markdown("""
<div class="pro-hero">
    <div style="font-size:2.1rem; font-weight:950;">📊 AI Aksje Analyzer Pro</div>
    <div class="muted">V6 Restore · gammel dashboard-look + stabil trading engine · Top Picks · RSI · Trendkanal · Paper Trading</div>
</div>
""", unsafe_allow_html=True)

# ---------------- DATA ----------------
portfolio = load_portfolio()
latest_prices = {}
for m in ["USA", "NORGE", "SVERIGE"]:
    for item in get_top10(m):
        latest_prices[item["ticker"]] = item["price"]

# ---------------- PORTFOLIO DASHBOARD ----------------
total_value = portfolio_value(portfolio, latest_prices)
start_cash = 100000
return_pct = ((total_value - start_cash) / start_cash * 100) if start_cash else 0

st.markdown("## 💼 Paper Trading Dashboard")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Cash", f"{portfolio['cash']:,.0f} kr")
m2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
m3.metric("Avkastning", f"{return_pct:.2f}%")
m4.metric("Åpne posisjoner", len(portfolio["positions"]))
m5.metric("Handler", len(portfolio["trades"]))

# ---------------- TOP PICKS OLD STYLE ----------------
st.markdown("## 🔥 Top Picks / Beste kjøp nå")

def signal_class(signal):
    s = str(signal).upper()
    if "BUY" in s:
        return "buy"
    if "SELL" in s:
        return "sell"
    return "hold"

def market_name_to_key(name):
    return {"Alle": "ALLE", "USA": "USA", "Norge": "NORGE", "Sverige": "SVERIGE"}.get(name, "ALLE")

def render_top_cards(items, prefix):
    selected = None
    cols = st.columns(3)
    for i, item in enumerate(items[:12]):
        cls = signal_class(item["signal"])
        with cols[i % 3]:
            st.markdown(f"""
            <div class="pro-card">
                <div class="ticker">{item['ticker']}</div>
                <div><span class="{cls}">{item['signal']}</span> <span class="badge">Score {item['score']}/10</span></div>
                <div class="price">{item['price']}</div>
                <div class="muted">Confidence: <b>{item['confidence']}%</b> · RSI: <b>{item.get('rsi','N/A')}</b></div>
                <div class="muted">SL/TP styres av trading engine</div>
            </div>
            """, unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Analyser", key=f"analyze_{prefix}_{item['ticker']}_{i}"):
                    st.session_state["selected_analysis_ticker"] = item["ticker"]
                    selected = item["ticker"]
            with c2:
                if st.button("Trade", key=f"trade_{prefix}_{item['ticker']}_{i}"):
                    ok, msg = auto_trade(item["ticker"], item["price"], item["signal"], item["confidence"], rsi=item.get("rsi"))
                    st.success(msg) if ok else st.warning(msg)
    return selected

tab_all, tab_us, tab_no, tab_se = st.tabs(["🌍 Alle", "🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige"])
with tab_all:
    render_top_cards(get_top10("ALLE"), "all")
with tab_us:
    render_top_cards(get_top10("USA"), "us")
with tab_no:
    render_top_cards(get_top10("NORGE"), "no")
with tab_se:
    render_top_cards(get_top10("SVERIGE"), "se")

# ---------------- POSITIONS ----------------
st.markdown("---")
st.markdown("## 📌 Åpne posisjoner")

if portfolio["positions"]:
    rows = []
    for t, pos in portfolio["positions"].items():
        item = find_ticker(t) or {}
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
            "RSI": item.get("rsi", ""),
            "Antall": round(pos["shares"], 6),
            "PnL %": round(pnl_pct, 2),
            "PnL kr": round(pnl_kr, 2),
            "Status": "🟢 gevinst" if pnl_pct >= 0 else "🔴 tap",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Ingen åpne posisjoner.")

# ---------------- INTERACTIVE ANALYSIS ----------------
st.markdown("## 📊 Interaktiv analyse")

all_tickers = [x["ticker"] for x in get_top10("ALLE")]
default_ticker = st.session_state.get("selected_analysis_ticker", all_tickers[0])
default_index = all_tickers.index(default_ticker) if default_ticker in all_tickers else 0

selected = st.selectbox("Velg aksje", all_tickers, index=default_index, key="analysis_select")
item = find_ticker(selected) or get_top10("ALLE")[0]

a1, a2, a3, a4 = st.columns(4)
a1.metric("Signal", item["signal"])
a2.metric("Score", f"{item['score']}/10")
a3.metric("Kurs", item["price"])
a4.metric("Confidence", f"{item['confidence']}%")

fig, ch, hist = price_chart(item["ticker"], item["price"])
st.plotly_chart(fig, use_container_width=True, key=f"price_{item['ticker']}")

if ch:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trend-status", f"{ch['emoji']} {ch['status']}")
    c2.metric("Kurs i kanal", f"{ch['position_pct']}%")
    c3.metric("Støtte", f"{ch['lower_now']:.2f}")
    c4.metric("Motstand", f"{ch['upper_now']:.2f}")

rfig, rsi_now, rsi_dir = rsi_chart(item["ticker"], item["price"])
r1, r2, r3, r4 = st.columns(4)
r1.metric("Gjeldende RSI", f"{rsi_now}", rsi_dir)
r2.metric("Oversolgt", "30")
r3.metric("Overkjøpt", "70")
r4.metric("Ekstrem", "80")
st.plotly_chart(rfig, use_container_width=True, key=f"rsi_{item['ticker']}")

# ---------------- TRADE LOG ----------------
st.markdown("## 📜 Handelslogg")
if portfolio["trades"]:
    st.dataframe(pd.DataFrame(portfolio["trades"]), use_container_width=True, hide_index=True)
else:
    st.info("Ingen handler ennå.")

# ---------------- TEST CONTROL ----------------
st.markdown("---")
st.markdown("## 🧪 Trading-kontroll")
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("BUY GOOGL", key="buy_googl"):
        ok, msg = auto_trade("GOOGL", 349.94, "BUY", 76, rsi=62)
        st.success(msg) if ok else st.warning(msg)
with c2:
    if st.button("SELL AAPL", key="sell_aapl"):
        ok, msg = auto_trade("AAPL", 190.10, "SELL", 70)
        st.success(msg) if ok else st.warning(msg)
with c3:
    if st.button("TP AAPL @ 220", key="tp_aapl"):
        ok, msg = auto_trade("AAPL", 220.00, "HOLD", 70)
        st.success(msg) if ok else st.warning(msg)
with c4:
    if st.button("SL AAPL @ 170", key="sl_aapl"):
        ok, msg = auto_trade("AAPL", 170.00, "HOLD", 70)
        st.success(msg) if ok else st.warning(msg)
