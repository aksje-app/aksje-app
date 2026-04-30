
import json, os
from pathlib import Path
from datetime import datetime
try:
    import psycopg2
except Exception:
    psycopg2 = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
STORE_FILE = Path("paper_portfolio.json")
DEFAULT_PORTFOLIO = {"cash": 100000.0, "positions": {}, "trades": []}

def using_postgres():
    return bool(DATABASE_URL) and psycopg2 is not None

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not using_postgres():
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_state (
        id INTEGER PRIMARY KEY,
        cash REAL NOT NULL,
        updated_at TEXT NOT NULL
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_positions (
        ticker TEXT PRIMARY KEY,
        shares REAL NOT NULL,
        entry_price REAL NOT NULL,
        last_price REAL NOT NULL,
        stop_loss REAL,
        take_profit REAL,
        trailing_stop REAL,
        highest_price REAL,
        confidence INTEGER,
        reason TEXT,
        opened_at TEXT
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trades (
        id SERIAL PRIMARY KEY,
        time TEXT NOT NULL,
        type TEXT NOT NULL,
        ticker TEXT NOT NULL,
        price REAL NOT NULL,
        shares REAL NOT NULL,
        amount REAL NOT NULL,
        confidence INTEGER,
        pnl_pct REAL,
        reason TEXT
    );""")
    for q in [
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS stop_loss REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS take_profit REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS trailing_stop REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS highest_price REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS confidence INTEGER;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS reason TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS opened_at TEXT;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS confidence INTEGER;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS pnl_pct REAL;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS reason TEXT;",
    ]:
        cur.execute(q)
    cur.execute("SELECT cash FROM paper_state WHERE id=1")
    if cur.fetchone() is None:
        cur.execute("INSERT INTO paper_state (id, cash, updated_at) VALUES (1, %s, %s)",
                    (100000.0, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    return True

def _load_json():
    if not STORE_FILE.exists():
        save_portfolio(DEFAULT_PORTFOLIO.copy())
        return DEFAULT_PORTFOLIO.copy()
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = DEFAULT_PORTFOLIO.copy()
    data.setdefault("cash", 100000.0)
    data.setdefault("positions", {})
    data.setdefault("trades", [])
    return data

def _save_json(portfolio):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)

def load_portfolio():
    if not using_postgres():
        return _load_json()
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT cash FROM paper_state WHERE id=1")
    row = cur.fetchone()
    cash = float(row[0]) if row else 100000.0
    cur.execute("""SELECT ticker, shares, entry_price, last_price, stop_loss, take_profit,
                          trailing_stop, highest_price, confidence, reason, opened_at
                   FROM paper_positions ORDER BY ticker""")
    positions = {}
    for r in cur.fetchall():
        positions[r[0]] = {
            "ticker": r[0], "shares": float(r[1]), "entry_price": float(r[2]),
            "last_price": float(r[3]), "stop_loss": float(r[4] or 0),
            "take_profit": float(r[5] or 0), "trailing_stop": float(r[6] or 0),
            "highest_price": float(r[7] or r[3]), "confidence": int(r[8] or 0),
            "reason": r[9] or "", "opened_at": r[10] or ""
        }
    cur.execute("""SELECT time, type, ticker, price, shares, amount, confidence, pnl_pct, reason
                   FROM paper_trades ORDER BY id DESC LIMIT 300""")
    trades = []
    for r in cur.fetchall():
        trades.append({"time": r[0], "type": r[1], "ticker": r[2], "price": float(r[3]),
                       "shares": float(r[4]), "amount": float(r[5]), "confidence": int(r[6] or 0),
                       "pnl_pct": None if r[7] is None else float(r[7]), "reason": r[8] or ""})
    conn.close()
    return {"cash": cash, "positions": positions, "trades": trades}

def save_portfolio(portfolio):
    if not using_postgres():
        _save_json(portfolio)
        return
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE paper_state SET cash=%s, updated_at=%s WHERE id=1",
                (float(portfolio.get("cash", 0)), datetime.now().isoformat(timespec="seconds")))
    cur.execute("DELETE FROM paper_positions")
    for ticker, pos in portfolio.get("positions", {}).items():
        cur.execute("""INSERT INTO paper_positions
            (ticker, shares, entry_price, last_price, stop_loss, take_profit, trailing_stop,
             highest_price, confidence, reason, opened_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (ticker, float(pos.get("shares",0)), float(pos.get("entry_price",0)),
             float(pos.get("last_price",0)), float(pos.get("stop_loss",0)),
             float(pos.get("take_profit",0)), float(pos.get("trailing_stop",0)),
             float(pos.get("highest_price", pos.get("last_price",0))), int(pos.get("confidence",0)),
             pos.get("reason",""), pos.get("opened_at","")))
    conn.commit()
    conn.close()

def add_trade(portfolio, trade):
    trade["time"] = datetime.now().isoformat(timespec="seconds")
    portfolio["trades"].insert(0, trade)
    if using_postgres():
        init_db()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""INSERT INTO paper_trades
            (time, type, ticker, price, shares, amount, confidence, pnl_pct, reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (trade["time"], trade["type"], trade["ticker"], float(trade["price"]),
             float(trade["shares"]), float(trade["amount"]), int(trade.get("confidence",0) or 0),
             trade.get("pnl_pct"), trade.get("reason","")))
        conn.commit()
        conn.close()
        save_portfolio(portfolio)
    else:
        save_portfolio(portfolio)

def reset_portfolio(start_cash=100000.0):
    p = {"cash": float(start_cash), "positions": {}, "trades": []}
    if using_postgres():
        init_db()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM paper_positions")
        cur.execute("DELETE FROM paper_trades")
        cur.execute("UPDATE paper_state SET cash=%s, updated_at=%s WHERE id=1",
                    (float(start_cash), datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
    else:
        save_portfolio(p)
    return p

def storage_status():
    return "Postgres/DATABASE_URL ✅" if using_postgres() else "Lokal JSON fallback ⚠️"
