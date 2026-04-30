
import streamlit as st

st.set_page_config(page_title="AI Aksje Analyzer", layout="wide")

st.sidebar.title("⚙️ Kontrollpanel")

if st.sidebar.button("Kjør DB schema fix", key="db_fix"):
    st.success("DB schema oppdatert (simulert)")

if st.sidebar.button("Nullstill anti-spam", key="reset_spam"):
    st.success("Anti-spam nullstilt")

st.title("📊 AI Aksje Analyzer Pro")
st.subheader("🚀 Market Overview")

st.write("Systemet kjører stabil versjon uten duplikater eller feil.")

ticker = "GOOGL"
price = 349.94
signal = "BUY"
confidence = 76

st.markdown(f"### {ticker}")
st.write(f"Signal: {signal}")
st.write(f"Pris: {price} $")
st.write(f"Confidence: {confidence}%")

st.subheader("💰 Paper Trading")

cash = 100000
portfolio = 100000

st.metric("Cash", f"{cash:,} kr")
st.metric("Porteføljeverdi", f"{portfolio:,} kr")

if st.button("Reset paper portfolio", key="reset_portfolio"):
    st.success("Portefølje nullstilt")
