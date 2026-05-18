import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re

load_dotenv()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")


NORDIC_EXCHANGE_KEYWORDS = {
    "Norge": ("oslo", "euronext growth oslo", "euronext oslo", "oslo børs", "oslo bors"),
    "Sverige": ("stockholm", "nasdaq stockholm", "first north", "spotlight", "nordic growth market", "ngm"),
}

RUMORED_IPO_WATCHLIST = [
    {
        "name": "SpaceX",
        "symbol": "Ikke tildelt",
        "region": "USA",
        "status": "Rapportert / ikke kalenderført",
        "expected": "Mulig 2026, men dato/ticker er ikke endelig offentlig kalenderdata",
        "note": "Rapportert konfidensiell IPO-prosess. Vises her fordi selskapet normalt ikke dukker opp i IPO-kalender før børsdato/ticker er bekreftet.",
        "source": "AP / Axios / presseomtale",
    },
    {
        "name": "Starlink",
        "symbol": "Ikke tildelt",
        "region": "USA",
        "status": "Overvåkes",
        "expected": "Ingen bekreftet egen IPO-dato",
        "note": "Kan bli egen notering eller del av SpaceX-prosess, men er ikke en vanlig kalenderført IPO nå.",
        "source": "Presseomtale / selskapsrykter",
    },
    {
        "name": "Databricks",
        "symbol": "Ikke tildelt",
        "region": "USA",
        "status": "IPO-kandidat",
        "expected": "Markedet spekulerer i 2026/2027",
        "note": "Stor privat AI-/dataaktør som ofte nevnes i IPO-pipeline, men vises ikke som bekreftet kalendernotering før dato/ticker finnes.",
        "source": "IPO-pipeline / presseomtale",
    },
    {
        "name": "Stripe",
        "symbol": "Ikke tildelt",
        "region": "USA / Irland",
        "status": "IPO-kandidat",
        "expected": "Ingen bekreftet dato",
        "note": "Stor privat fintech-aktør. Holdes separat fra kalenderlisten fordi dato og børs ikke er bekreftet.",
        "source": "IPO-pipeline / presseomtale",
    },
    {
        "name": "Northvolt",
        "symbol": "Ikke tildelt",
        "region": "Sverige",
        "status": "Historisk IPO-kandidat / høy risiko",
        "expected": "Ingen bekreftet dato",
        "note": "Tidligere omtalt som mulig svensk notering, men status må behandles med høy usikkerhet.",
        "source": "Nordisk IPO-overvåking",
    },
]


def _ipo_row(name, symbol="", ipo_date="", exchange="", market="", source=""):
    return {
        "name": str(name or "").strip() or "Ukjent selskap",
        "symbol": str(symbol or "").strip() or "N/A",
        "date": str(ipo_date or "").strip() or "Ukjent dato",
        "exchange": str(exchange or market or "").strip() or "Ukjent børs",
        "market": str(market or exchange or "").strip(),
        "source": str(source or "").strip(),
    }


def _row_text(row):
    return " ".join(str(row.get(k, "") or "") for k in ("name", "symbol", "exchange", "market")).lower()


def _matches_country(row, country):
    text = _row_text(row)
    return any(keyword in text for keyword in NORDIC_EXCHANGE_KEYWORDS.get(country, ()))


def _looks_like_ipo_or_listing_text(text):
    low = str(text or "").lower()
    include = (
        "ipo",
        "initial public offering",
        "new listing",
        "listing date",
        "admission",
        "admitted to trading",
        "first day of trading",
        "første handelsdag",
        "notering",
        "börsnotering",
        "børsnotering",
    )
    exclude = (
        "bond",
        "bonds",
        "obligation",
        "warrant",
        "warrants",
        "certificate",
        "certificates",
        "structured product",
        "derivative",
        "derivatives",
        "etf",
        "etn",
        "fund",
        "fonds",
        "mutual fund",
        "open-end",
        "rights issue",
        "subscription right",
        "treasury bill",
        "note",
        "notes",
    )
    return any(word in low for word in include) and not any(word in low for word in exclude)


def _extract_dateish(text):
    text = str(text or "")
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b", text)
    return match.group(0) if match else "Se kilde"

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


def get_finnhub_nordic_ipo_calendar(days_back=365, days_forward=180):
    rows, error = get_ipo_calendar(days_back=days_back, days_forward=days_forward)
    if error:
        return {"Norge": [], "Sverige": []}, error

    grouped = {"Norge": [], "Sverige": []}
    for row in rows or []:
        normalized = _ipo_row(
            row.get("name"),
            row.get("symbol"),
            row.get("date"),
            row.get("exchange"),
            source="Finnhub",
        )
        for country in grouped:
            if _matches_country(normalized, country):
                grouped[country].append(normalized)
    return grouped, None


def get_euronext_oslo_ipos(limit=20):
    """
    Henter Oslo-noteringer fra Euronext sin offentlige IPO-side.
    Dette er en ekstra nordisk kilde, fordi mange Oslo-noteringer ikke dukker opp
    i den vanlige amerikansk-orienterte IPO-kalenderen.
    """
    urls = [
        "https://live.euronext.com/en/ipo-showcase/1061",
        "https://live.euronext.com/en/products/equities/ipos",
    ]
    last_error = None
    response = None
    for url in urls:
        try:
            response = requests.get(url, timeout=12, headers={"User-Agent": "smart-ai-trading-app/1.0"})
            response.raise_for_status()
            break
        except Exception as e:
            last_error = e
            response = None
    if response is None:
        return [], f"Euronext Oslo-kilde feilet: {last_error}"

    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    seen = set()
    for card in soup.find_all(["article", "div", "tr"]):
        text = " ".join(card.get_text(" ", strip=True).split())
        if not text or "Oslo" not in text:
            continue
        if not _looks_like_ipo_or_listing_text(text):
            continue
        key = text[:180]
        if key in seen:
            continue
        seen.add(key)
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in card.find_all(["td", "th"])]
        if cells:
            ipo_date = cells[0]
            name = cells[1] if len(cells) > 1 else text[:80]
            symbol = ""
            market = "Euronext Oslo"
            for cell in cells[2:]:
                low = cell.lower()
                if "oslo" in low or "euronext" in low:
                    market = cell
                elif not symbol and len(cell) <= 12 and any(ch.isalpha() for ch in cell):
                    symbol = cell
        else:
            ipo_date = _extract_dateish(text)
            name = text[:100]
            symbol = ""
            market = "Euronext Oslo"
        rows.append(_ipo_row(name, symbol=symbol, ipo_date=ipo_date, exchange="Oslo", market=market, source="Euronext"))

    return rows[:limit], None


def get_euronext_oslo_ipos_legacy(limit=20):
    url = "https://live.euronext.com/en/products/equities/ipos"
    try:
        response = requests.get(url, timeout=12, headers={"User-Agent": "smart-ai-trading-app/1.0"})
        response.raise_for_status()
    except Exception as e:
        return [], f"Euronext Oslo-kilde feilet: {e}"

    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        joined = " | ".join(cells)
        if "Oslo" not in joined:
            continue
        if not _looks_like_ipo_or_listing_text(joined):
            continue

        ipo_date = cells[0]
        name = cells[1] if len(cells) > 1 else "Ukjent selskap"
        symbol = ""
        exchange = "Oslo"
        market = "Euronext Oslo"
        for cell in cells[2:]:
            low = cell.lower()
            if "oslo" in low or "euronext" in low:
                market = cell
            elif not symbol and len(cell) <= 12 and any(ch.isalpha() for ch in cell):
                symbol = cell
        rows.append(_ipo_row(name, symbol=symbol, ipo_date=ipo_date, exchange=exchange, market=market, source="Euronext"))

    return rows[:limit], None


def get_nordic_ipo_calendar():
    grouped, finnhub_error = get_finnhub_nordic_ipo_calendar()
    oslo_rows, oslo_error = get_euronext_oslo_ipos()

    seen = set()
    merged_norway = []
    for row in list(oslo_rows or []) + list(grouped.get("Norge") or []):
        key = (str(row.get("date", "")), str(row.get("name", "")).lower(), str(row.get("symbol", "")).upper())
        if key in seen:
            continue
        seen.add(key)
        merged_norway.append(row)

    return {
        "Norge": merged_norway,
        "Sverige": grouped.get("Sverige", []),
        "errors": [err for err in (finnhub_error, oslo_error) if err],
    }


def get_rumored_ipo_watchlist():
    return list(RUMORED_IPO_WATCHLIST)
