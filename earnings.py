
import os
import requests
import datetime as dt
import streamlit as st

API_KEY = os.getenv("FINNHUB_API_KEY", "")

@st.cache_data(ttl=3600, show_spinner=False)
def get_earnings(ticker):
    if not API_KEY:
        return {"days_until": None, "date": None, "error": "Mangler FINNHUB_API_KEY"}
    try:
        today = dt.date.today()
        future = today + dt.timedelta(days=120)
        resp = requests.get("https://finnhub.io/api/v1/calendar/earnings",
                            params={"symbol": ticker, "from": today.isoformat(), "to": future.isoformat(), "token": API_KEY},
                            timeout=12)
        data = resp.json().get("earningsCalendar", [])
        if not data:
            return {"days_until": None, "date": None, "error": None}
        date_str = data[0].get("date")
        if not date_str:
            return {"days_until": None, "date": None, "error": None}
        earnings_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        return {"days_until": (earnings_date - today).days, "date": date_str,
                "epsEstimate": data[0].get("epsEstimate"), "revenueEstimate": data[0].get("revenueEstimate"), "error": None}
    except Exception as e:
        return {"days_until": None, "date": None, "error": str(e)}
