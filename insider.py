
import os
import requests
import datetime as dt
import streamlit as st

API_KEY = os.getenv("FINNHUB_API_KEY", "")

@st.cache_data(ttl=3600, show_spinner=False)
def get_insider_data(ticker, days=120):
    if not API_KEY:
        return {"score": 0.5, "error": "Mangler FINNHUB_API_KEY"}
    try:
        to_date = dt.date.today()
        from_date = to_date - dt.timedelta(days=days)
        resp = requests.get(
            "https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": ticker, "from": from_date.isoformat(), "to": to_date.isoformat(), "token": API_KEY},
            timeout=12,
        )
        data = resp.json().get("data", [])
        buy_shares = sell_shares = 0
        buy_count = sell_count = 0
        for row in data:
            try:
                change = float(row.get("change") or 0)
            except Exception:
                change = 0
            if change > 0:
                buy_shares += change
                buy_count += 1
            elif change < 0:
                sell_shares += abs(change)
                sell_count += 1
        total = buy_shares + sell_shares
        score = 0.5 if total == 0 else buy_shares / total
        if buy_count >= 3 and score > 0.55:
            score = min(1.0, score + 0.10)
        return {"score": round(score, 3), "buy_shares": round(buy_shares, 0), "sell_shares": round(sell_shares, 0),
                "buy_count": buy_count, "sell_count": sell_count, "transactions": len(data), "error": None}
    except Exception as e:
        return {"score": 0.5, "error": str(e)}
