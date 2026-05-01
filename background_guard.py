
"""
Background Guard v1

Mål:
- Automatiske/rangeringsbaserte søk skal ikke hente unødvendige data når markedet er stengt.
- Når markedet er stengt brukes cache hvis tilgjengelig.
- Cron/auto-trading skal aldri auto-trade på stengte markeder.
- Manuell analyse kan fortsatt bruke eksisterende app-funksjoner der det trengs.

Cache:
- Lokal pickle-cache på Render-instansen.
- Ikke ment som permanent database, men reduserer kall og gir visning utenfor åpningstid.
"""

from pathlib import Path
from datetime import datetime, timedelta
import pickle

from market_hours import market_status, ticker_market, open_markets

CACHE_DIR = Path("cache")
CACHE_FILE = CACHE_DIR / "score_stock_cache.pkl"
DEFAULT_CACHE_MAX_HOURS = 72


def _now():
    return datetime.utcnow()


def _load_cache():
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"background cache load failed: {e}")
    return {}


def _save_cache(cache):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(cache, f)
        return True
    except Exception as e:
        print(f"background cache save failed: {e}")
        return False


def _cache_key(ticker, use_news=False):
    return f"{str(ticker).upper()}|news={bool(use_news)}"


def get_cached_score(ticker, use_news=False, max_age_hours=DEFAULT_CACHE_MAX_HOURS):
    cache = _load_cache()
    key = _cache_key(ticker, use_news)
    row = cache.get(key)

    if not row:
        return None

    try:
        ts = row.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        if ts and (_now() - ts) <= timedelta(hours=max_age_hours):
            return row.get("item")
    except Exception:
        return row.get("item")

    return None


def put_cached_score(ticker, item, use_news=False):
    if not item:
        return False

    cache = _load_cache()
    cache[_cache_key(ticker, use_news)] = {
        "timestamp": _now().isoformat(),
        "item": item,
    }
    return _save_cache(cache)


def background_fetch_allowed(ticker):
    """
    True bare når tickerens marked faktisk er åpent.
    """
    market = ticker_market(ticker)
    status = market_status(market)
    return bool(status.get("is_open")), market, status


def score_stock_guarded(score_func, ticker, use_news=False, mode="background"):
    """
    Brukes av bakgrunnsrangering / Top Picks.

    Hvis markedet er åpent:
      - hent fersk data
      - oppdater cache

    Hvis markedet er stengt:
      - bruk cache
      - hvis ingen cache: returner None
    """
    allowed, market, status = background_fetch_allowed(ticker)

    if allowed:
        item = score_func(ticker, use_news=use_news)
        if item:
            put_cached_score(ticker, item, use_news=use_news)
        return item

    cached = get_cached_score(ticker, use_news=use_news)
    if cached:
        print(f"{ticker}: {market} stengt ({status.get('reason')}) - bruker cache")
        return cached

    print(f"{ticker}: {market} stengt ({status.get('reason')}) - ingen cache, hopper over bakgrunnskall")
    return None


def filter_open_market_tickers(tickers):
    out = []
    skipped = []
    for ticker in tickers:
        allowed, market, status = background_fetch_allowed(ticker)
        if allowed:
            out.append(ticker)
        else:
            skipped.append((ticker, market, status.get("reason", "stengt")))
    return out, skipped


def market_guard_summary(tickers):
    """
    Kort tekst til UI.
    """
    statuses = {}
    for ticker in tickers:
        market = ticker_market(ticker)
        if market not in statuses:
            statuses[market] = market_status(market)

    parts = []
    for market, status in statuses.items():
        name = status.get("name", market)
        if status.get("is_open"):
            parts.append(f"{name}: åpent ✅")
        else:
            parts.append(f"{name}: stengt ({status.get('reason')}) – bruker cache hvis mulig")

    return " | ".join(parts)


def print_market_guard_summary():
    print("=== MARKET GUARD ===")
    for m in ["USA", "NORGE", "SVERIGE"]:
        s = market_status(m)
        if s.get("is_open"):
            print(f"{s.get('name', m)} åpent ✅ - scanning aktiv")
        else:
            print(f"{s.get('name', m)} stengt: {s.get('reason')} - ingen auto trade / cache ved UI")
    print("====================")
