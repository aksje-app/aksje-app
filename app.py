
import streamlit as st
import pandas as pd

from paper_store import load_portfolio, reset_portfolio
from trading_engine import auto_trade, portfolio_value, calc_levels

st.set_page_config(page_title="AI Aksje Analyzer", layout="wide")

st.sidebar.title("⚙️ Kontrollpanel")

if st.sidebar.button("Nullstill paper portfolio", key="reset_portfolio_sidebar"):
    reset_portfolio(100000)
    st.sidebar.success("Paper portfolio nullstilt")

st.title("📊 AI Aksje Analyzer Pro")
st.subheader("🚀 Trading Engine v1")

st.info("Dette er stabil testversjon: BUY → paper-kjøp → portefølje → trade-logg.")

# Testsignal
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

latest_prices = {"GOOGL": price}
total_value = portfolio_value(portfolio, latest_prices)

p1, p2, p3 = st.columns(3)
p1.metric("Cash", f"{portfolio['cash']:,.0f} kr")
p2.metric("Porteføljeverdi", f"{total_value:,.0f} kr")
p3.metric("Åpne posisjoner", len(portfolio["positions"]))

st.subheader("📌 Posisjoner")

if portfolio["positions"]:
    rows = []
    for t, pos in portfolio["positions"].items():
        last = latest_prices.get(t, pos.get("last_price", pos["entry_price"]))
        entry = pos["entry_price"]
        pnl_pct = ((last - entry) / entry * 100) if entry else 0
        sl, tp = calc_levels(entry)
        rows.append({
            "Ticker": t,
            "Kjøpt": round(entry, 2),
            "Siste": round(last, 2),
            "Stop loss": sl,
            "Take profit": tp,
            "Antall": round(pos["shares"], 6),
            "PnL %": round(pnl_pct, 2),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("Ingen åpne posisjoner.")

st.subheader("📜 Handelslogg")

if portfolio["trades"]:
    st.dataframe(pd.DataFrame(portfolio["trades"]), use_container_width=True)
else:
    st.info("Ingen handler ennå.")
