
import streamlit as st
import pandas as pd

from paper_store import load_portfolio, reset_portfolio, storage_status
from trading_engine import auto_trade, portfolio_value, calc_levels
from top10_engine import get_top10
from ai_model import ai_score_signal
from backtest_engine import run_simple_backtest, demo_prices

st.set_page_config(page_title="AI Aksje Analyzer Pro", layout="wide")

# ---------- CSS ----------

st.markdown("""
<style>
/* V5 mobile/iPhone style */
body, .stApp {
    background: #0b1220 !important;
}
.block-container {
    max-width: 980px;
    padding-top: 1.5rem;
}
section[data-testid="stSidebar"] {
    background: #020617 !important;
}
div[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 18px;
    padding: 14px;
}
.stButton button {
    border-radius: 999px !important;
    font-weight: 700 !important;
}
@media (max-width: 768px) {
    .block-container {
        padding-left: .7rem;
        padding-right: .7rem;
    }
    div[data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }
    div[data-testid="stMetric"] {
        margin-bottom: .5rem;
    }
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
.block-container { padding-top: 2rem; }
.metric-card {
    border: 1px solid rgba(120,140,180,.25);
    border-radius: 16px;
    padding: 18px;
    background: rgba(15,23,42,.05);
}
.good { color: #16a34a; font-weight: 800; }
.bad { color: #dc2626; font-weight: 800; }
.small { opacity: .75; font-size: .85rem; }
</style>
""", unsafe_allow_html=True)

# ---------- Sidebar ----------
st.sidebar.title("⚙️ Kontrollpanel")
st.sidebar.caption(f"Lagring: {storage_status()}")

if st.sidebar.button("Nullstill paper portfolio", key="reset_portfolio_sidebar"):
    reset_portfolio(100000)
    st.sidebar.success("Paper portfolio nullstilt")

st.sidebar.markdown("---")
st.sidebar.subheader("🔁 Auto")
st.sidebar.caption("Cron kjører scanner_worker.py og bruker samme database.")

# ---------- Header ----------
st.title("📊 AI Aksje Analyzer Pro")
st.subheader("🚀 V4 Pro: UI + TOP10 + AUTO + FIX ALL")
st.info("Felles database, auto BUY/SELL, stop-loss, take-profit, trailing stop, Top10 og bedre UI.")

# ---------- Top 10 ----------
st.markdown("## 🔥 Top 10 kjøp nå")

tab_all, tab_us, tab_no, tab_se = st.tabs(["🌍 Alle", "🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige"])

def render_top10(items, key_prefix):
    selected = None
    cols = st.columns(2)
    for i, item in enumerate(items):
        with cols[i % 2]:
            signal = item["signal"]
            color_class = "good" if signal == "BUY" else "bad" if "SELL" in signal else ""
            with st.container(border=True):
                st.markdown(f"### {item['ticker']}")
                st.markdown(f"<span class='{color_class}'>{signal}</span> · Score **{item['score']}/10**", unsafe_allow_html=True)
                st.markdown(f"Pris: **{item['price']}** · Confidence: **{item['confidence']}%**")
                ai = ai_score_signal(item)
                st.markdown(f"AI score: **{ai['ai_score']}/100** · **{ai['decision']}**")
                with st.expander("Hvorfor?"):
                    for r in ai["reasons"]:
                        st.write("• " + r)
                if st.button(f"Trade {item['ticker']}", key=f"{key_prefix}_{item['ticker']}_{i}"):
                    ok, msg = auto_trade(item["ticker"], item["price"], item["signal"], item["confidence"])
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
                    selected = item["ticker"]
    return selected

with tab_all:
    render_top10(get_top10("ALLE"), "all")
with tab_us:
    render_top10(get_top10("USA"), "usa")
with tab_no:
    render_top10(get_top10("NORGE"), "no")
with tab_se:
    render_top10(get_top10("SVERIGE"), "se")

# ---------- Portfolio ----------
portfolio = load_portfolio()
latest_prices = {}
for m in ["USA", "NORGE", "SVERIGE"]:
    for item in get_top10(m):
        latest_prices[item["ticker"]] = item["price"]

st.markdown("---")
st.markdown("## 💰 Paper Trading Dashboard")

total_value = portfolio_value(portfolio, latest_prices)
start_cash = 100000
return_pct = ((total_value - start_cash) / start_cash * 100) if start_cash else 0

p1, p2, p3, p4 = st.columns(4)
p1.metric("Cash", f"{portfolio['cash']:,.0f} kr")
p2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
p3.metric("Avkastning", f"{return_pct:.2f}%")
p4.metric("Åpne posisjoner", len(portfolio["positions"]))

# ---------- Positions ----------
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
    df_pos = pd.DataFrame(rows)
    st.dataframe(df_pos, use_container_width=True)
else:
    st.info("Ingen åpne posisjoner.")

# ---------- Trade log ----------
st.markdown("## 📜 Handelslogg")

if portfolio["trades"]:
    st.dataframe(pd.DataFrame(portfolio["trades"]), use_container_width=True)
else:
    st.info("Ingen handler ennå.")

# ---------- Manual tests ----------
st.markdown("---")
st.markdown("## 🧪 Test og kontroll")

c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("BUY-test")
    if st.button("Kjøp GOOGL test", key="buy_googl_test"):
        ok, msg = auto_trade("GOOGL", 349.94, "BUY", 76)
        st.success(msg) if ok else st.warning(msg)

with c2:
    st.subheader("Take-profit")
    if st.button("TP AAPL @ 220", key="tp_aapl_test"):
        ok, msg = auto_trade("AAPL", 220.00, "HOLD", 70)
        st.success(msg) if ok else st.warning(msg)

with c3:
    st.subheader("Stop-loss")
    if st.button("SL AAPL @ 170", key="sl_aapl_test"):
        ok, msg = auto_trade("AAPL", 170.00, "HOLD", 70)
        st.success(msg) if ok else st.warning(msg)

st.markdown("### 🔴 Direkte SELL")
s1, s2 = st.columns(2)
with s1:
    sell_ticker = st.text_input("Ticker", "AAPL", key="manual_sell_ticker")
with s2:
    sell_price = st.number_input("SELL-pris", value=190.10, step=1.0, key="manual_sell_price")

if st.button("Kjør direkte SELL", key="manual_sell_btn"):
    ok, msg = auto_trade(sell_ticker, sell_price, "SELL", 70)
    st.success(msg) if ok else st.warning(msg)


st.markdown("---")
st.markdown("## 🧪 Backtest / historiske data")

bt_col1, bt_col2, bt_col3 = st.columns(3)
with bt_col1:
    bt_ticker = st.selectbox("Backtest ticker", list(latest_prices.keys()), key="bt_ticker")
with bt_col2:
    buy_th = st.slider("BUY terskel", 50, 90, 65)
with bt_col3:
    sell_th = st.slider("SELL terskel", 20, 60, 45)

prices = demo_prices(latest_prices.get(bt_ticker, 100), 180)
bt = run_simple_backtest(prices, buy_threshold=buy_th, sell_threshold=sell_th)

b1, b2, b3 = st.columns(3)
b1.metric("Sluttverdi", f"{bt['final_value']:,.0f} kr")
b2.metric("Avkastning", f"{bt['return_pct']}%")
b3.metric("Win rate", f"{bt['win_rate']}%")

st.line_chart(pd.DataFrame({"Pris": prices}))
if bt["trades"]:
    st.dataframe(pd.DataFrame(bt["trades"]), use_container_width=True)
else:
    st.info("Ingen backtest-trades med disse tersklene.")
