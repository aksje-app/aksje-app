
from datetime import datetime
import pytz


def now_oslo():
    return datetime.now(pytz.timezone("Europe/Oslo"))


def open_markets():
    now = now_oslo()

    if now.weekday() >= 5:
        return []

    h = now.hour
    m = now.minute

    markets = []

    # Norge / Oslo Børs ca 09:00–16:25
    if h >= 9 and (h < 16 or (h == 16 and m <= 25)):
        markets.append("NORGE")

    # Sverige / Stockholm ca 09:00–17:30
    if h >= 9 and (h < 17 or (h == 17 and m <= 30)):
        markets.append("SVERIGE")

    # USA / NYSE/Nasdaq 15:30–22:00 norsk tid, forenklet DST-praktisk regel
    if (h > 15 or (h == 15 and m >= 30)) and h < 22:
        markets.append("USA")

    return markets


def ticker_market(ticker):
    ticker = str(ticker).upper()
    if ticker.endswith(".OL"):
        return "NORGE"
    if ticker.endswith(".ST"):
        return "SVERIGE"
    return "USA"


def is_market_open_for_ticker(ticker):
    return ticker_market(ticker) in open_markets()


def should_process_ticker(ticker):
    return is_market_open_for_ticker(ticker)
