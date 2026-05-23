from utils import _safe_float  # v18.6.3 centralized helpers

import os
from datetime import datetime, timedelta, timezone
import requests
from runtime_env import data_source_env_status, env_value, load_app_env, redact_secrets

load_app_env()
FINNHUB_API_KEY = env_value("FINNHUB_API_KEY")
FINNHUB_TIMEOUT_SECONDS = float(os.getenv("FINNHUB_TIMEOUT_SECONDS", "5") or 5)




def _safe_int(v, default=0):
    try:
        if v is None:
            return default
        return int(float(v))
    except Exception:
        return default


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _days_ago(value):
    d = _parse_date(value)
    if not d:
        return None
    return max(0, (datetime.now(timezone.utc).date() - d.date()).days)


def _transaction_type(row):
    """
    Finnhub bruker ofte positive 'change' for kjøp og negative for salg.
    Noen datasett kan også ha transactionCode/type.
    """
    change = _safe_float(row.get("change", 0))
    if change > 0:
        return "BUY"
    if change < 0:
        return "SELL"

    code = str(row.get("transactionCode") or row.get("type") or "").upper()
    if code in {"P", "BUY", "PURCHASE"}:
        return "BUY"
    if code in {"S", "SELL", "SALE"}:
        return "SELL"
    return "UNKNOWN"


def fetch_insider_transactions(ticker, months=6, limit=25):
    """
    Henter siste insider-transaksjoner fra Finnhub hvis nøkkel finnes.
    Returnerer normaliserte rader for UI og scoring.
    """
    api_key = env_value("FINNHUB_API_KEY")
    if not api_key:
        return {
            "transactions": [],
            "error": "FINNHUB_API_KEY mangler",
            "source": "Finnhub insider-transactions",
        }

    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=int(months * 31))

    url = "https://finnhub.io/api/v1/stock/insider-transactions"
    params = {
        "symbol": ticker,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "token": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=FINNHUB_TIMEOUT_SECONDS)
        response.raise_for_status()
        raw = response.json()
        data = raw.get("data", []) if isinstance(raw, dict) else []

        rows = []
        for row in data:
            tx_type = _transaction_type(row)
            date_value = row.get("transactionDate") or row.get("filingDate") or row.get("date")
            change = _safe_float(row.get("change", 0))
            shares = abs(change) if change else abs(_safe_float(row.get("share", 0)))
            price = _safe_float(row.get("transactionPrice", row.get("price", 0)))
            value = shares * price if price else None
            name = row.get("name") or row.get("insiderName") or row.get("ownerName") or ""
            relation = row.get("transactionCode") or row.get("relation") or row.get("officerTitle") or ""

            rows.append({
                "date": str(date_value)[:10] if date_value else "",
                "type": tx_type,
                "shares": shares,
                "price": price,
                "value": value,
                "name": name,
                "relation": relation,
                "days_ago": _days_ago(date_value),
            })

        rows.sort(key=lambda x: x.get("date", ""), reverse=True)
        return {
            "transactions": rows[:limit],
            "error": None,
            "source": "Finnhub insider-transactions",
        }

    except Exception as e:
        return {
            "transactions": [],
            "error": redact_secrets(f"Insider API-feil: {type(e).__name__}: {e}"),
            "source": "Finnhub insider-transactions",
        }


def insider_score_from_transactions(transactions):
    """
    Score 0..1.
    Vekting:
    - Ferske handler teller mer.
    - Åpne markedskjøp får positiv vekt.
    - Salg teller negativt, men mindre hardt fordi mange salg skyldes skatt/opsjoner/diversifisering.
    """
    if not transactions:
        return {
            "score": 0.50,
            "label": "Ingen data",
            "buy_shares": 0,
            "sell_shares": 0,
            "buy_count": 0,
            "sell_count": 0,
            "net_recent_score": 0.0,
        }

    weighted_buy = 0.0
    weighted_sell = 0.0
    buy_shares = 0.0
    sell_shares = 0.0
    buy_count = 0
    sell_count = 0

    for tx in transactions:
        tx_type = tx.get("type")
        shares = abs(_safe_float(tx.get("shares", 0)))
        days = tx.get("days_ago")
        days = 180 if days is None else max(0, float(days))

        # Recency decay: 0 dager = 1.0, 180 dager ≈ 0.25
        recency_weight = max(0.25, 1.0 - (days / 240.0))
        size_weight = max(1.0, min(8.0, (shares ** 0.5) / 100.0))

        w = recency_weight * size_weight

        if tx_type == "BUY":
            buy_count += 1
            buy_shares += shares
            weighted_buy += w
        elif tx_type == "SELL":
            sell_count += 1
            sell_shares += shares
            # Salg teller, men ikke like tungt som kjøp
            weighted_sell += w * 0.65

    total = weighted_buy + weighted_sell
    if total <= 0:
        score = 0.50
    else:
        score = weighted_buy / total

    if score >= 0.65:
        label = "Positivt insiderbilde"
    elif score <= 0.35:
        label = "Negativt insiderbilde"
    else:
        label = "Blandet insiderbilde"

    return {
        "score": round(score, 2),
        "label": label,
        "buy_shares": round(buy_shares, 2),
        "sell_shares": round(sell_shares, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "net_recent_score": round(weighted_buy - weighted_sell, 3),
    }


def get_insider_signal(ticker, months=6):
    """
    Hovedfunksjon brukt av app/signal engine.
    Returnerer både aggregat og siste transaksjoner.
    """
    data = fetch_insider_transactions(ticker, months=months, limit=25)
    transactions = data.get("transactions", [])
    score_data = insider_score_from_transactions(transactions)

    latest = transactions[:8]
    latest_type = latest[0]["type"] if latest else "NONE"
    latest_date = latest[0]["date"] if latest else None

    return {
        **score_data,
        "transactions": len(transactions),
        "latest_transactions": latest,
        "latest_type": latest_type,
        "latest_date": latest_date,
        "error": data.get("error"),
        "source": data.get("source"),
        "months": months,
    }


# Compatibility aliases used by older code
def insider_signal(ticker):
    return get_insider_signal(ticker)


def fetch_insider(ticker):
    return get_insider_signal(ticker)


# --- BACKWARD COMPATIBILITY V2 ---
# Eldre app.py/signal_engine.py importerer get_insider_data.
# Nye insider-funksjoner bruker get_insider_signal.
# Disse aliasene gjør at gammel og ny kode fungerer samtidig.

def get_insider_data(ticker, months=6):
    return get_insider_signal(ticker, months=months)


def get_insider(ticker, months=6):
    return get_insider_signal(ticker, months=months)


def get_insider_transactions(ticker, months=6):
    return fetch_insider_transactions(ticker, months=months).get("transactions", [])


# --- INSIDER HARD HOTFIX V3 ---
# Backward compatible functions expected by app.py and older modules.

def get_insider_data(ticker, months=6):
    return get_insider_signal(ticker, months=months)


def get_insider(ticker, months=6):
    return get_insider_signal(ticker, months=months)


def get_insider_transactions(ticker, months=6):
    try:
        result = fetch_insider_transactions(ticker, months=months)
        return result.get("transactions", [])
    except Exception:
        data = get_insider_signal(ticker, months=months)
        return data.get("latest_transactions", [])


def insider_api_status():
    status = data_source_env_status()
    return {
        "provider": "Finnhub insider-transactions",
        "has_key": bool(status.get("finnhub_key")),
        "env_loaded": bool(status.get("env_loaded")),
        "env_sources": list(status.get("env_sources") or []),
    }
