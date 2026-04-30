
import streamlit as st


def _price_change(item):
    try:
        hist = item.get("hist")
        close = hist["Close"].dropna()
        if len(close) < 2:
            return None, None
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change = (price - prev) / prev * 100 if prev else 0
        return price, change
    except Exception:
        return item.get("price"), item.get("change_pct")


def _currency(ticker):
    if str(ticker).endswith(".OL"):
        return "kr"
    if str(ticker).endswith(".ST"):
        return "SEK"
    return "$"


def render_top10_cards(title, items, key_prefix="top10"):
    st.markdown(f"### {title}")

    if not items:
        st.info("Ingen aksjer funnet.")
        return None

    selected = None
    cols = st.columns(2)

    for i, item in enumerate(items[:10]):
        ticker = item.get("ticker", "N/A")
        score = float(item.get("score", item.get("decision_score", 0)) or 0)
        price, change = _price_change(item)
        decision = item.get("decision", {})
        if isinstance(decision, dict):
            signal = decision.get("decision", "HOLD")
        else:
            signal = str(decision or "HOLD")

        change = 0 if change is None else float(change)
        price_text = "N/A" if price is None else f"{float(price):.2f} {_currency(ticker)}"
        color = "#22c55e" if change >= 0 else "#ef4444"
        dot = "🟢" if change >= 0 else "🔴"

        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="font-size:1.05rem; font-weight:900;">{dot} {ticker}</div>
                        <div style="opacity:0.75;">#{i+1}</div>
                    </div>
                    <div style="font-size:1.35rem; font-weight:900; margin-top:6px;">{price_text}</div>
                    <div style="color:{color}; font-weight:800;">{change:+.2f}%</div>
                    <div style="margin-top:6px;">Score: <b>{score:.2f}/10</b></div>
                    <div style="opacity:0.8;">Signal: {signal}</div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Analyser", key=f"{key_prefix}_{ticker}_{i}"):
                    selected = ticker

    return selected


def render_market_top10_block(usa=None, norge=None, sverige=None, alle=None):
    st.markdown("## 🔥 Beste kjøp akkurat nå")

    tab_all, tab_us, tab_no, tab_se = st.tabs(["🌍 Alle", "🇺🇸 USA", "🇳🇴 Norge", "🇸🇪 Sverige"])

    selected = None
    with tab_all:
        selected = render_top10_cards("🌍 Top 10 alle markeder", alle or [], "all") or selected
    with tab_us:
        selected = render_top10_cards("🇺🇸 Top 10 USA", usa or [], "usa") or selected
    with tab_no:
        selected = render_top10_cards("🇳🇴 Top 10 Norge", norge or [], "no") or selected
    with tab_se:
        selected = render_top10_cards("🇸🇪 Top 10 Sverige", sverige or [], "se") or selected

    if selected:
        st.session_state["selected_ticker_from_top10"] = selected

    return selected
