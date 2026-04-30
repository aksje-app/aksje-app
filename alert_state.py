
import json
import os
from datetime import datetime
import pytz

LOCAL_ALERT_FILE = "alert_state.json"


def _now_oslo():
    return datetime.now(pytz.timezone("Europe/Oslo"))


def _db_available():
    try:
        from paper_store import init_store, get_conn
        init_store()
        return True
    except Exception:
        return False


def _init_alert_table():
    try:
        from paper_store import get_conn
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
        print(f"alert_state init warning: {e}")
        return False


def _param():
    try:
        from paper_store import using_postgres
        return "%s" if using_postgres() else "?"
    except Exception:
        return "?"


def _load_local():
    if not os.path.exists(LOCAL_ALERT_FILE):
        return {}
    try:
        with open(LOCAL_ALERT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local(data):
    try:
        with open(LOCAL_ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def normalize_signal(signal):
    s = str(signal or "").upper().strip()
    if "BUY" in s:
        return "BUY"
    if "SELL" in s or "AVOID" in s:
        return "SELL"
    if "HOLD" in s or "WAIT" in s:
        return "HOLD"
    return s or "UNKNOWN"


def get_last_signal(ticker):
    ticker = str(ticker).upper().strip()

    if _db_available() and _init_alert_table():
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
            print(f"get_last_signal db warning: {e}")

    return _load_local().get(ticker)


def save_signal(ticker, signal, meta=None):
    ticker = str(ticker).upper().strip()
    signal = normalize_signal(signal)
    sent_at = _now_oslo().isoformat()
    meta_raw = json.dumps(meta or {}, ensure_ascii=False)

    if _db_available() and _init_alert_table():
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
            print(f"save_signal db warning: {e}")

    data = _load_local()
    data[ticker] = {"signal": signal, "sent_at": sent_at, "meta": meta_raw}
    _save_local(data)
    return False


def should_send_alert(ticker, signal, cooldown_minutes=None, allow_repeat=False):
    """
    STRAM ANTI-SPAM:
    - Sender første gang.
    - Sender når signal endrer seg, f.eks HOLD -> BUY eller BUY -> SELL.
    - Sender IKKE samme BUY på nytt, uansett cooldown.
    """
    ticker = str(ticker).upper().strip()
    signal = normalize_signal(signal)
    last = get_last_signal(ticker)

    if not last:
        return True, "first signal"

    last_signal = normalize_signal(last.get("signal"))

    if last_signal != signal:
        return True, f"signal changed {last_signal} -> {signal}"

    return False, f"duplicate {ticker} {signal}"


def record_alert(ticker, signal, meta=None):
    return save_signal(ticker, signal, meta)


def reset_alert_state():
    if _db_available() and _init_alert_table():
        try:
            from paper_store import get_conn
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM alert_state")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"reset alert db warning: {e}")

    _save_local({})
    return False


def should_send_signal_alert(ticker, decision, meta=None):
    """
    Wrapper for eldre kode som sender direkte signalvarsler.
    Returnerer True bare hvis signalet er nytt/endret.
    """
    signal = decision.get("decision", decision) if isinstance(decision, dict) else decision
    return should_send_alert(ticker, signal)


def record_signal_alert(ticker, decision, meta=None):
    signal = decision.get("decision", decision) if isinstance(decision, dict) else decision
    return record_alert(ticker, signal, meta)
