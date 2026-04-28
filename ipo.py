import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

def get_ipo_calendar(days_back=30, days_forward=60):
    if not FINNHUB_API_KEY or FINNHUB_API_KEY.startswith("din_"):
        return [], "Mangler Finnhub API-nøkkel. Legg FINNHUB_API_KEY i .env"

    today = date.today()
    start = today - timedelta(days=days_back)
    end = today + timedelta(days=days_forward)

    try:
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/ipo",
            params={"from": start.isoformat(), "to": end.isoformat(), "token": FINNHUB_API_KEY},
            timeout=12,
        )
        data = r.json()
        if r.status_code != 200:
            return [], data.get("error", f"Finnhub-feil: {r.status_code}")
        return data.get("ipoCalendar", []), None
    except Exception as e:
        return [], str(e)
