
import os
import requests
import datetime as dt
import streamlit as st
from runtime_env import data_source_env_status, env_value, load_app_env, redact_secrets

load_app_env()
API_KEY = env_value("FINNHUB_API_KEY")

@st.cache_data(ttl=3600, show_spinner=False)
def get_earnings(ticker, months=4):
    api_key = env_value("FINNHUB_API_KEY")
    if not api_key:
        return {"days_until": None, "date": None, "error": "Mangler FINNHUB_API_KEY"}
    try:
        today = dt.date.today()
        future = today + dt.timedelta(days=max(31, int(float(months or 4) * 31)))
        resp = requests.get("https://finnhub.io/api/v1/calendar/earnings",
                            params={"symbol": ticker, "from": today.isoformat(), "to": future.isoformat(), "token": api_key},
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
        return {"days_until": None, "date": None, "error": redact_secrets(str(e))}


def earnings_api_status():
    status = data_source_env_status()
    return {
        "provider": "Finnhub earnings calendar",
        "has_key": bool(status.get("finnhub_key")),
        "env_loaded": bool(status.get("env_loaded")),
        "env_sources": list(status.get("env_sources") or []),
    }
