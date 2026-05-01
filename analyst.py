
import os
import requests
import streamlit as st

API_KEY = os.getenv("FINNHUB_API_KEY", "")

@st.cache_data(ttl=3600, show_spinner=False)
def get_analyst_trend(ticker):
    if not API_KEY:
        return {"score": 0.5, "trend": "neutral", "error": "Mangler FINNHUB_API_KEY"}
    try:
        resp = requests.get("https://finnhub.io/api/v1/stock/recommendation",
                            params={"symbol": ticker, "token": API_KEY}, timeout=12)
        data = resp.json()
        if not data:
            return {"score": 0.5, "trend": "neutral", "error": None}
        latest = data[0]
        strong_buy = latest.get("strongBuy", 0) or 0
        buy = latest.get("buy", 0) or 0
        hold = latest.get("hold", 0) or 0
        sell = latest.get("sell", 0) or 0
        strong_sell = latest.get("strongSell", 0) or 0
        positive = strong_buy * 1.2 + buy
        negative = sell + strong_sell * 1.2
        total = positive + hold + negative
        score = 0.5 if total == 0 else max(0, min(1, 0.5 + (positive - negative) / (total * 2)))
        trend = "up" if score >= 0.65 else "down" if score <= 0.35 else "neutral"
        return {"score": round(score, 3), "trend": trend, "strongBuy": strong_buy, "buy": buy, "hold": hold,
                "sell": sell, "strongSell": strong_sell, "period": latest.get("period"), "error": None}
    except Exception as e:
        return {"score": 0.5, "trend": "neutral", "error": str(e)}
