
import json
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path

try:
    import psycopg2
except Exception:
    psycopg2 = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_FILE = Path(os.getenv("PAPER_SQLITE_FILE", "paper_trading.db"))
_SCHEMA_READY = False


def using_postgres():
    return bool(DATABASE_URL) and psycopg2 is not None


def get_conn():
    if using_postgres():
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(SQLITE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _p():
    return "%s" if using_postgres() else "?"


def _rows(cur, rows):
    if using_postgres():
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]


def init_store():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_state (
        id INTEGER PRIMARY KEY,
        cash REAL NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_positions (
        ticker TEXT PRIMARY KEY,
        shares REAL NOT NULL,
        avg_price REAL NOT NULL,
        last_price REAL NOT NULL,
        highest_price REAL,
        stop_loss REAL,
        take_profit REAL,
        entry_time TEXT,
        entry_signal TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY,
        time TEXT NOT NULL,
        type TEXT NOT NULL,
        ticker TEXT NOT NULL,
        price REAL NOT NULL,
        shares REAL NOT NULL,
        amount REAL NOT NULL,
        pnl_pct REAL,
        reason TEXT,
        decision TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_daily_count (
        day TEXT PRIMARY KEY,
        count INTEGER NOT NULL
    );
    """)

    if using_postgres():
        for q in [
            "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS highest_price REAL;",
            "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS stop_loss REAL;",
            "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS take_profit REAL;",
            "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS entry_time TEXT;",
            "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS entry_signal TEXT;",
            "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS pnl_pct REAL;",
            "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS reason TEXT;",
            "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS decision TEXT;",
        ]:
            cur.execute(q)
    else:
        cur.execute("PRAGMA table_info(paper_positions)")
        cols = [r[1] for r in cur.fetchall()]
        for col, typ in [
            ("highest_price", "REAL"),
            ("stop_loss", "REAL"),
            ("take_profit", "REAL"),
            ("entry_time", "TEXT"),
            ("entry_signal", "TEXT"),
        ]:
            if col not in cols:
                cur.execute(f"ALTER TABLE paper_positions ADD COLUMN {col} {typ}")

        cur.execute("PRAGMA table_info(paper_trades)")
        cols = [r[1] for r in cur.fetchall()]
        for col, typ in [("pnl_pct", "REAL"), ("reason", "TEXT"), ("decision", "TEXT")]:
            if col not in cols:
                cur.execute(f"ALTER TABLE paper_trades ADD COLUMN {col} {typ}")

    cur.execute("SELECT cash FROM paper_state WHERE id=1")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO paper_state (id, cash, updated_at) VALUES (1, %s, %s)" if using_postgres() else
            "INSERT INTO paper_state (id, cash, updated_at) VALUES (1, ?, ?)",
            (float(os.getenv("PAPER_START_CASH", "100000")), datetime.utcnow().isoformat())
        )

    conn.commit()
    conn.close()
    _SCHEMA_READY = True


def force_schema_migration():
    global _SCHEMA_READY
    _SCHEMA_READY = False
    init_store()
    return True


def fetchall(query, params=()):
    init_store()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    out = _rows(cur, rows)
    conn.close()
    return out


def execute(query, params=()):
    init_store()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()


def get_cash():
    rows = fetchall("SELECT cash FROM paper_state WHERE id=1")
    return float(rows[0]["cash"]) if rows else 0.0


def set_cash(cash):
    p = _p()
    execute(f"UPDATE paper_state SET cash={p}, updated_at={p} WHERE id=1", (float(cash), datetime.utcnow().isoformat()))


def get_positions():
    rows = fetchall("SELECT * FROM paper_positions ORDER BY ticker")
    return {r["ticker"]: r for r in rows}


def get_position(ticker):
    p = _p()
    rows = fetchall(f"SELECT * FROM paper_positions WHERE ticker={p}", (ticker,))
    return rows[0] if rows else None


def upsert_position(ticker, pos):
    init_store()
    conn = get_conn()
    cur = conn.cursor()

    if using_postgres():
        q = """
        INSERT INTO paper_positions
        (ticker, shares, avg_price, last_price, highest_price, stop_loss, take_profit, entry_time, entry_signal)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (ticker) DO UPDATE SET
            shares=EXCLUDED.shares,
            avg_price=EXCLUDED.avg_price,
            last_price=EXCLUDED.last_price,
            highest_price=EXCLUDED.highest_price,
            stop_loss=EXCLUDED.stop_loss,
            take_profit=EXCLUDED.take_profit,
            entry_time=EXCLUDED.entry_time,
            entry_signal=EXCLUDED.entry_signal
        """
    else:
        q = """
        INSERT OR REPLACE INTO paper_positions
        (ticker, shares, avg_price, last_price, highest_price, stop_loss, take_profit, entry_time, entry_signal)
        VALUES (?,?,?,?,?,?,?,?,?)
        """

    cur.execute(q, (
        ticker,
        float(pos.get("shares", 0)),
        float(pos.get("avg_price", 0)),
        float(pos.get("last_price", 0)),
        float(pos.get("highest_price", pos.get("last_price", 0))),
        float(pos.get("stop_loss", 0) or 0),
        float(pos.get("take_profit", 0) or 0),
        pos.get("entry_time"),
        json.dumps(pos.get("entry_signal", {}), ensure_ascii=False),
    ))

    conn.commit()
    conn.close()


def delete_position(ticker):
    p = _p()
    execute(f"DELETE FROM paper_positions WHERE ticker={p}", (ticker,))


def add_trade(trade):
    init_store()
    conn = get_conn()
    cur = conn.cursor()
    p = _p()

    cur.execute(
        f"""
        INSERT INTO paper_trades
        (time, type, ticker, price, shares, amount, pnl_pct, reason, decision)
        VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
        """,
        (
            trade.get("time", datetime.utcnow().isoformat()),
            trade["type"],
            trade["ticker"],
            float(trade["price"]),
            float(trade["shares"]),
            float(trade["amount"]),
            trade.get("pnl_pct"),
            trade.get("reason"),
            json.dumps(trade.get("decision", {}), ensure_ascii=False),
        )
    )

    conn.commit()
    conn.close()


def get_trades(limit=100):
    return fetchall(f"SELECT * FROM paper_trades ORDER BY id DESC LIMIT {int(limit)}")


def today_key():
    return date.today().isoformat()


def trades_today():
    p = _p()
    rows = fetchall(f"SELECT count FROM paper_daily_count WHERE day={p}", (today_key(),))
    return int(rows[0]["count"]) if rows else 0


def inc_trade_count():
    day = today_key()
    if using_postgres():
        execute("""
        INSERT INTO paper_daily_count (day, count) VALUES (%s, 1)
        ON CONFLICT (day) DO UPDATE SET count=paper_daily_count.count+1
        """, (day,))
    else:
        rows = fetchall("SELECT count FROM paper_daily_count WHERE day=?", (day,))
        if rows:
            execute("UPDATE paper_daily_count SET count=count+1 WHERE day=?", (day,))
        else:
            execute("INSERT INTO paper_daily_count (day, count) VALUES (?, 1)", (day,))


def reset_all(start_cash=None):
    init_store()
    start_cash = float(start_cash or os.getenv("PAPER_START_CASH", "100000"))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM paper_positions")
    cur.execute("DELETE FROM paper_trades")
    cur.execute("DELETE FROM paper_daily_count")
    cur.execute(
        "UPDATE paper_state SET cash=%s, updated_at=%s WHERE id=1" if using_postgres() else
        "UPDATE paper_state SET cash=?, updated_at=? WHERE id=1",
        (start_cash, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
