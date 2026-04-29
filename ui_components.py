import streamlit as st

def market_pulse(data):
    if not data:
        return
    avg = sum([x.get("change_pct",0) for x in data]) / len(data)
    if avg > 1:
        txt, col = "🚀 Bullish", "#00ff88"
    elif avg < -1:
        txt, col = "🔻 Bearish", "#ff4d4d"
    else:
        txt, col = "⚖️ Neutral", "#ffaa00"
    st.markdown(f"<b>Market Pulse:</b> <span style='color:{col}'>{txt} ({avg:.2f}%)</span>", unsafe_allow_html=True)

def top_movers(data):
    gain = sorted(data, key=lambda x: x.get("change_pct",0), reverse=True)[:5]
    loss = sorted(data, key=lambda x: x.get("change_pct",0))[:5]
    c1, c2 = st.columns(2)
    with c1:
        st.write("📈 Gainers")
        for x in gain:
            st.write(f"{x['ticker']} +{x.get('change_pct',0):.2f}%")
    with c2:
        st.write("📉 Losers")
        for x in loss:
            st.write(f"{x['ticker']} {x.get('change_pct',0):.2f}%")
