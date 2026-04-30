
import streamlit as st
import pandas as pd

from paper_store import load_portfolio, reset_portfolio, storage_status
from trading_engine import auto_trade, portfolio_value, calc_levels

st.set_page_config(page_title="AI Aksje Analyzer", layout="wide")

st.sidebar.title("⚙️ Kontrollpanel")
st.sidebar.caption(f"Lagring: {storage_status()}")

if st.sidebar.button("Nullstill paper portfolio", key="reset_portfolio_sidebar"):
    reset_portfolio(100000)
    st.sidebar.success("Paper portfolio nullstilt")

st.title("📊 AI Aksje Analyzer Pro")
st.subheader("🚀 Trading Engine v2")

st.info("Auto trading v2: felles lagring, BUY/SELL, stop-loss, take-profit og trailing stop.")

ticker = "GOOGL"
price = 349.94
signal = "BUY"
confidence = 76

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ticker", ticker)
c2.metric("Signal", signal)
c3.metric("Pris", f"{price:.2f} $")
c4.metric("Confidence", f"{confidence}%")

if st.button("Kjør test trade nå", key="run_test_trade_btn"):
    ok, msg = auto_trade(ticker, price, signal, confidence)
    if ok:
        st.success(msg)
    else:
        st.warning(msg)

portfolio = load_portfolio()

st.markdown("---")
st.subheader("💰 Paper Trading")

latest_prices = {"GOOGL": 349.94, "AAPL": 190.10, "MSFT": 412.20}
total_value = portfolio_value(portfolio, latest_prices)
start_cash = 100000
return_pct = ((total_value - start_cash) / start_cash * 100) if start_cash else 0

p1, p2, p3, p4 = st.columns(4)
p1.metric("Cash", f"{portfolio['cash']:,.0f} kr")
p2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
p3.metric("Avkastning", f"{return_pct:.2f}%")
p4.metric("Åpne posisjoner", len(portfolio["positions"]))

st.subheader("📌 Posisjoner")
if portfolio["positions"]:
    rows = []
    for t, pos in portfolio["positions"].items():
        last = latest_prices.get(t, pos.get("last_price", pos["entry_price"]))
        entry = pos["entry_price"]
        pnl_pct = ((last - entry) / entry * 100) if entry else 0
        sl, tp, tr = calc_levels(entry, pos.get("highest_price", entry))
        rows.append({"Ticker": t, "Kjøpt": round(entry, 2), "Siste": round(last, 2),
                     "Stop loss": sl, "Take profit": tp, "Trailing stop": tr,
                     "Antall": round(pos["shares"], 6), "PnL %": round(pnl_pct, 2),
                     "Status": "🟢 gevinst" if pnl_pct >= 0 else "🔴 tap"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("Ingen åpne posisjoner.")

st.subheader("📜 Handelslogg")
if portfolio["trades"]:
    st.dataframe(pd.DataFrame(portfolio["trades"]), use_container_width=True)
else:
    st.info("Ingen handler ennå.")

st.markdown("---")
st.subheader("🧪 SELL-test")
st.caption("Bruk dette for å teste stop-loss/take-profit uten å vente på markedet.")
sell_col1, sell_col2 = st.columns(2)
with sell_col1:
    test_sell_ticker = st.text_input("Ticker å teste salg på", "AAPL")
with sell_col2:
    test_sell_price = st.number_input("Testpris", value=220.00, step=1.0)
if st.button("Kjør SELL/TP/SL-test", key="sell_test_btn"):
    ok, msg = auto_trade(test_sell_ticker, test_sell_price, "HOLD", 70)
    if ok:
        st.success(msg)
    else:
        st.warning(msg)
