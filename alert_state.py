
import json
import os
from datetime import datetime, timedelta
import pytz

LOCAL_ALERT_FILE = "alert_state.json"
DEFAULT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))


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
        from paper_store import get_conn, using_postgres
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
    except Exception:
        return False


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


def get_last_signal(ticker):
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
        except Exception:
            pass

    data = _load_local()
    return data.get(ticker)


def save_signal(ticker, signal, meta=None):
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
        except Exception:
            pass

    data = _load_local()
    data[ticker] = {"signal": signal, "sent_at": sent_at, "meta": meta_raw}
    _save_local(data)
    return False


def should_send_alert(ticker, signal, cooldown_minutes=None):
    """
    Sender kun hvis:
    - signal er nytt/endret, eller
    - cooldown er passert og signalet fortsatt er viktig

    Standard: Ikke spam samme signal innen ALERT_COOLDOWN_MINUTES.
    """
    cooldown_minutes = int(cooldown_minutes or DEFAULT_COOLDOWN_MINUTES)
    last = get_last_signal(ticker)

    if not last:
        return True, "new ticker"

    last_signal = last.get("signal")
    sent_at = last.get("sent_at")

    if last_signal != signal:
        return True, f"signal changed {last_signal} -> {signal}"

    try:
        last_time = datetime.fromisoformat(sent_at)
        now = _now_oslo()
        if last_time.tzinfo is None:
            last_time = pytz.timezone("Europe/Oslo").localize(last_time)

        if now - last_time >= timedelta(minutes=cooldown_minutes):
            # For samme signal etter cooldown: fortsatt begrenset.
            # Bare tillat repeterte varsler for sterke BUY/SELL hvis brukeren ønsker det.
            repeat_enabled = os.getenv("ALLOW_REPEAT_ALERTS_AFTER_COOLDOWN", "false").lower() == "true"
            if repeat_enabled:
                return True, "cooldown passed"
    except Exception:
        pass

    return False, "duplicate/cooldown"


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
        except Exception:
            pass

    _save_local({})
    return False
