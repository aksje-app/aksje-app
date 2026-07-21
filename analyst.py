
import os
import requests
import streamlit as st
from runtime_env import data_source_env_status, env_value, load_app_env, redact_secrets

load_app_env()

@st.cache_data(ttl=3600, show_spinner=False)
def get_analyst_trend(ticker):
    api_key = env_value("FINNHUB_API_KEY")
    if not api_key:
        return {"score": 0.5, "trend": "neutral", "error": "Mangler FINNHUB_API_KEY"}
    try:
        resp = requests.get("https://finnhub.io/api/v1/stock/recommendation",
                            params={"symbol": ticker, "token": api_key}, timeout=12)
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
        return {"score": 0.5, "trend": "neutral", "error": redact_secrets(str(e))}


def analyst_api_status():
    status = data_source_env_status()
    return {
        "provider": "Finnhub stock/recommendation",
        "has_key": bool(status.get("finnhub_key")),
        "env_loaded": bool(status.get("env_loaded")),
        "env_sources": list(status.get("env_sources") or []),
    }
