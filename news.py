import requests
import streamlit as st
import time

API_KEY = st.secrets.get("NEWSAPI_KEY", None)

# ⏱️ Cache i 30 min
@st.cache_data(ttl=1800)
def get_news(company):

    if not API_KEY:
        return [], "Ingen API-nøkkel"

    url = f"https://newsapi.org/v2/everything?q={company}&apiKey={API_KEY}&language=en"

    try:
        response = requests.get(url)
        data = response.json()

        # ❌ API limit nådd
        if data.get("status") != "ok":
            return [], "API-grense nådd (NewsAPI)"

        articles = data.get("articles", [])[:5]

        titles = []
        for a in articles:
            titles.append({
                "title": a.get("title"),
                "source": a.get("source", {}).get("name"),
                "published": a.get("publishedAt")
            })

        # ⏳ Liten delay (unngå spam)
        time.sleep(1)

        return titles, None

    except Exception as e:
        return [], f"Feil: {e}"