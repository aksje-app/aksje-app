
import json
import os
from datetime import datetime
try:
    import pytz
except Exception:
    pytz = None
from datetime import timezone

LOCAL_ALERT_FILE = "alert_state.json"  # legacy fallback only
STORAGE_KEY = "alerts/signal_state.json"


def _storage():
    try:
        from services.storage_service import get_storage_service
        return get_storage_service()
    except Exception:
        return None


def _now_oslo():
    return datetime.now((pytz.timezone if pytz else (lambda _tz: timezone.utc))("Europe/Oslo"))


def normalize_signal(signal):
    s = str(signal or "").upper().strip()
    if "BUY" in s:
        return "BUY"
    if "SELL" in s or "AVOID" in s:
        return "SELL"
    if "HOLD" in s or "WAIT" in s:
        return "HOLD"
    return s or "UNKNOWN"


def _db_ready():
    try:
        from paper_store import init_store, get_conn
        init_store()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS alert_state (
            ticker TEXT PRIMARY KEY,
            signal TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            meta TEXT
        );
        """)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"alert_state DB fallback: {e}")
        return False


def _load_local():
    storage = _storage()
    if storage is not None:
        data = storage.read_json(STORAGE_KEY, default=None)
        if isinstance(data, dict):
            return data

    # One-time legacy migration from old root file if it exists locally.
    if os.path.exists(LOCAL_ALERT_FILE):
        try:
            with open(LOCAL_ALERT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if storage is not None:
                    storage.write_json(STORAGE_KEY, data)
                return data
        except Exception:
            pass
    return {}


def _save_local(data):
    storage = _storage()
    if storage is not None:
        try:
            storage.write_json(STORAGE_KEY, data if isinstance(data, dict) else {})
            return
        except Exception:
            pass
    try:
        with open(LOCAL_ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_last_signal(ticker):
    ticker = str(ticker).upper().strip()

    if _db_ready():
        try:
            from paper_store import get_conn, using_postgres
            conn = get_conn()
            cur = conn.cursor()
            p = "%s" if using_postgres() else "?"
            cur.execute(f"SELECT signal, sent_at, meta FROM alert_state WHERE ticker={p}", (ticker,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            if using_postgres():
                return {"signal": row[0], "sent_at": row[1], "meta": row[2]}
            return {"signal": row["signal"], "sent_at": row["sent_at"], "meta": row["meta"]}
        except Exception as e:
            print(f"get_last_signal DB fallback: {e}")

    return _load_local().get(ticker)


def record_alert(ticker, signal, meta=None):
    ticker = str(ticker).upper().strip()
    signal = normalize_signal(signal)
    sent_at = _now_oslo().isoformat()
    meta_raw = json.dumps(meta or {}, ensure_ascii=False)

    if _db_ready():
        try:
            from paper_store import get_conn, using_postgres
            conn = get_conn()
            cur = conn.cursor()
            if using_postgres():
                cur.execute("""
                INSERT INTO alert_state (ticker, signal, sent_at, meta)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    signal=EXCLUDED.signal,
                    sent_at=EXCLUDED.sent_at,
                    meta=EXCLUDED.meta
                """, (ticker, signal, sent_at, meta_raw))
            else:
                cur.execute("""
                INSERT OR REPLACE INTO alert_state (ticker, signal, sent_at, meta)
                VALUES (?, ?, ?, ?)
                """, (ticker, signal, sent_at, meta_raw))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"record_alert DB fallback: {e}")

    data = _load_local()
    data[ticker] = {"signal": signal, "sent_at": sent_at, "meta": meta_raw}
    _save_local(data)
    return False


def should_send_alert(ticker, signal, **kwargs):
    """
    Clean final anti-spam:
    - Første trade-varsel sendes
    - Nytt varsel sendes bare hvis signal endres
    - Samme BUY -> BUY sendes aldri på nytt
    """
    ticker = str(ticker).upper().strip()
    signal = normalize_signal(signal)
    last = get_last_signal(ticker)

    if not last:
        return True, "first signal"

    last_signal = normalize_signal(last.get("signal"))
    if last_signal != signal:
        return True, f"signal changed {last_signal} -> {signal}"

    return False, f"duplicate blocked {ticker} {signal}"


def reset_alert_state():
    if _db_ready():
        try:
            from paper_store import get_conn
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM alert_state")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"reset_alert_state DB fallback: {e}")

    _save_local({})
    return False


# Compatibility wrappers for old code
def should_send_signal_alert(ticker, decision, meta=None):
    signal = decision.get("decision", decision) if isinstance(decision, dict) else decision
    return should_send_alert(ticker, signal)


def record_signal_alert(ticker, decision, meta=None):
    signal = decision.get("decision", decision) if isinstance(decision, dict) else decision
    return record_alert(ticker, signal, meta)
