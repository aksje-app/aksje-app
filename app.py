
import streamlit as st
import pandas as pd

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=15000, key="v5_refresh")
except Exception:
    pass

from paper_store import load_portfolio, reset_portfolio, storage_status
from trading_engine import auto_trade, portfolio_value, calc_levels
from top10_engine import get_top10, find_ticker
from chart_engine import price_chart, rsi_chart

st.set_page_config(page_title="AI Aksje Analyzer Pro", layout="wide")

st.markdown("""
<style>
html, body, [class*="css"] { background-color: #0f172a; color: #e5e7eb; }
.block-container { padding-top: 1.4rem; max-width: 1350px; }
[data-testid="stSidebar"] { background-color: #020617; }
h1, h2, h3 { color: #f8fafc; font-weight: 900; }
.pro-card {
    border: 1px solid rgba(148,163,184,.28);
    border-radius: 18px;
    padding: 18px;
    background: linear-gradient(180deg, rgba(15,23,42,.98), rgba(15,23,42,.86));
    box-shadow: 0 10px 28px rgba(0,0,0,.18);
}
.buy { color:#22c55e; font-weight:900; }
.sell { color:#ef4444; font-weight:900; }
.hold { color:#facc15; font-weight:900; }
.muted { color:#94a3b8; font-size:.9rem; }
.big { font-size:1.55rem; font-weight:900; }
.small { font-size:.85rem; color:#94a3b8; }
.badge {
    display:inline-block; padding:4px 10px; border-radius:999px;
    background:#1e293b; border:1px solid rgba(148,163,184,.25);
}
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ Kontrollpanel")
st.sidebar.caption(f"Lagring: {storage_status()}")
st.sidebar.markdown("### 🔔 Varsler")
st.sidebar.caption("Pushover brukes ved BUY/SELL hvis PUSHOVER_APP_TOKEN og PUSHOVER_USER_KEY er satt.")
st.sidebar.markdown("### 🔁 Auto")
st.sidebar.caption("Cron kjører scanner_worker.py og bruker samme database.")

if st.sidebar.button("Nullstill paper portfolio", key="reset_portfolio_sidebar"):
    reset_portfolio(100000)
    st.sidebar.success("Paper portfolio nullstilt")

# Header
st.title("📊 AI Aksje Analyzer Pro")
st.caption("V5 Pro · Pushover · RSI · Trendkanal · Top10 · Paper Trading")

# Data
portfolio = load_portfolio()
latest_prices = {}
for m in ["USA", "NORGE", "SVERIGE"]:
    for item in get_top10(m):
        latest_prices[item["ticker"]] = item["price"]

# Portfolio summary
st.markdown("## 💰 Paper Trading")
total_value = portfolio_value(portfolio, latest_prices)
start_cash = 100000
return_pct = ((total_value - start_cash) / start_cash * 100) if start_cash else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Cash", f"{portfolio['cash']:,.0f} kr")
m2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
m3.metric("Avkastning", f"{return_pct:.2f}%")
m4.metric("Åpne posisjoner", len(portfolio["positions"]))

# Top 10
st.markdown("## 🔥 Automatiske Top Picks")
tab_all, tab_us, tab_no, tab_se = st.tabs(["🌍 Alle", "🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige"])

def signal_class(signal):
    s = str(signal).upper()
    if "BUY" in s:
        return "buy"
    if "SELL" in s:
        return "sell"
    return "hold"

def render_cards(items, prefix):
    cols = st.columns(2)
    for i, item in enumerate(items):
        with cols[i % 2]:
            cls = signal_class(item["signal"])
            st.markdown(f"""
            <div class="pro-card">
                <div class="big">{item['ticker']}</div>
                <div><span class="{cls}">{item['signal']}</span> <span class="badge">Score {item['score']}/10</span></div>
                <div class="muted">Pris: <b>{item['price']}</b> · Confidence: <b>{item['confidence']}%</b> · RSI: <b>{item.get('rsi','N/A')}</b></div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Trade {item['ticker']}", key=f"{prefix}_{item['ticker']}_{i}"):
                ok, msg = auto_trade(item["ticker"], item["price"], item["signal"], item["confidence"], rsi=item.get("rsi"))
                st.success(msg) if ok else st.warning(msg)

with tab_all:
    render_cards(get_top10("ALLE"), "all")
with tab_us:
    render_cards(get_top10("USA"), "us")
with tab_no:
    render_cards(get_top10("NORGE"), "no")
with tab_se:
    render_cards(get_top10("SVERIGE"), "se")

# Positions
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
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("Ingen åpne posisjoner.")

# Interactive analysis
st.markdown("## 📊 Interaktiv analyse")
all_tickers = [x["ticker"] for x in get_top10("ALLE")]
selected = st.selectbox("Velg aksje", all_tickers, key="analysis_select")
item = find_ticker(selected) or get_top10("ALLE")[0]

fig, ch, hist = price_chart(item["ticker"], item["price"])
st.plotly_chart(fig, use_container_width=True, key=f"price_{item['ticker']}")

if ch:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trend-status", f"{ch['emoji']} {ch['status']}")
    c2.metric("Kurs i kanal", f"{ch['position_pct']}%")
    c3.metric("Støtte", f"{ch['lower_now']:.2f}")
    c4.metric("Motstand", f"{ch['upper_now']:.2f}")

rfig, rsi_now, rsi_dir = rsi_chart(item["ticker"], item["price"])
r1, r2, r3 = st.columns(3)
r1.metric("Gjeldende RSI", f"{rsi_now}", rsi_dir)
r2.metric("Overkjøpt nivå", "70 / 80")
r3.metric("Oversolgt nivå", "30")
st.plotly_chart(rfig, use_container_width=True, key=f"rsi_{item['ticker']}")

# Trade log
st.markdown("## 📜 Handelslogg")
if portfolio["trades"]:
    st.dataframe(pd.DataFrame(portfolio["trades"]), use_container_width=True)
else:
    st.info("Ingen handler ennå.")

# Tests
st.markdown("---")
st.markdown("## 🧪 Kontrolltester")
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
