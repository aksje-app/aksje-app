import logging
from utils import using_postgres  # v18.6.3 centralized helpers

import json, os
from pathlib import Path
from datetime import datetime
try:
    import psycopg2
except Exception:
    psycopg2 = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
STORE_FILE = Path("paper_portfolio.json")  # legacy fallback only; new runtime storage uses StorageService.
STORAGE_KEY = "paper_trading/portfolio.json"
DEFAULT_PORTFOLIO = {"cash": 100000.0, "positions": {}, "trades": [], "fund_savings_plans": []}


def _storage():
    try:
        from services.storage_service import get_storage_service

        return get_storage_service()
    except Exception:
        return None


def _merge_portfolio(data):
    out = json.loads(json.dumps(DEFAULT_PORTFOLIO))
    if isinstance(data, dict):
        out.update(data)
        out.setdefault("cash", 100000.0)
        out.setdefault("positions", {})
        out.setdefault("trades", [])
        out.setdefault("fund_savings_plans", [])
    return out


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
        entry_price REAL,
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

    # Add all possible columns used by old/new versions
    migrations = [
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS entry_price REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS avg_price REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS last_price REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS stop_loss REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS take_profit REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS trailing_stop REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS highest_price REAL;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS confidence INTEGER;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS reason TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS opened_at TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS entry_time TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS entry_signal TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS asset_type TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS units_label TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS currency TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS nav_date TEXT;",
        "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS purchase_mode TEXT;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS confidence INTEGER;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS pnl_pct REAL;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS reason TEXT;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS asset_type TEXT;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS currency TEXT;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS nav_date TEXT;",
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS order_kind TEXT;",
    ]
    for q in migrations:
        cur.execute(q)

    # Compatibility: old DB used avg_price, new code uses entry_price
    cur.execute("""
        UPDATE paper_positions
        SET entry_price = avg_price
        WHERE entry_price IS NULL AND avg_price IS NOT NULL
    """)

    # Compatibility: if highest_price missing, use last_price or entry_price
    cur.execute("""
        UPDATE paper_positions
        SET highest_price = COALESCE(last_price, entry_price, avg_price)
        WHERE highest_price IS NULL
    """)

    cur.execute("SELECT cash FROM paper_state WHERE id=1")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO paper_state (id, cash, updated_at) VALUES (1, %s, %s)",
            (100000.0, datetime.now().isoformat(timespec="seconds")),
        )

    conn.commit()
    conn.close()
    return True


# -------------------------------------------------------------------
# Compatibility aliases
# Older modules import init_store(), newer store uses init_db().
# -------------------------------------------------------------------
def init_store():
    try:
        return init_db()
    except Exception as e:
        print(f"init_store failed: {e}")
        return False

def _load_json():
    storage = _storage()
    if storage is not None:
        data = storage.read_json(STORAGE_KEY, default=None)
        if isinstance(data, dict):
            return _merge_portfolio(data)

    # One-time legacy migration from old root file if it exists locally.
    if STORE_FILE.exists():
        try:
            data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
            merged = _merge_portfolio(data)
            if storage is not None:
                storage.write_json(STORAGE_KEY, merged)
            return merged
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)

    default = _merge_portfolio({})
    if storage is not None:
        storage.write_json(STORAGE_KEY, default)
    return default

def _save_json(portfolio):
    storage = _storage()
    if storage is not None:
        storage.write_json(STORAGE_KEY, _merge_portfolio(portfolio))
        return
    # Last-resort dev fallback only. Render should have StorageService available.
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(_merge_portfolio(portfolio), f, indent=2, ensure_ascii=False)

def load_portfolio():
    if not using_postgres():
        return _load_json()

    try:
        init_db()
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT cash FROM paper_state WHERE id=1")
        row = cur.fetchone()
        cash = float(row[0]) if row else 100000.0

        cur.execute("""
            SELECT ticker, shares, COALESCE(entry_price, avg_price) AS entry_price,
                   last_price, stop_loss, take_profit, trailing_stop,
                   highest_price, confidence, reason, opened_at,
                   COALESCE(asset_type, 'Aksje') AS asset_type,
                   COALESCE(units_label, 'shares') AS units_label,
                   COALESCE(currency, '') AS currency,
                   COALESCE(nav_date, '') AS nav_date,
                   COALESCE(purchase_mode, '') AS purchase_mode
            FROM paper_positions
            ORDER BY ticker
        """)
        positions = {}
        for r in cur.fetchall():
            entry = float(r[2] or r[3] or 0)
            last = float(r[3] or entry)
            positions[r[0]] = {
                "ticker": r[0],
                "shares": float(r[1] or 0),
                "entry_price": entry,
                "last_price": last,
                "stop_loss": float(r[4] or 0),
                "take_profit": float(r[5] or 0),
                "trailing_stop": float(r[6] or 0),
                "highest_price": float(r[7] or last),
                "confidence": int(r[8] or 0),
                "reason": r[9] or "",
                "opened_at": r[10] or "",
                "asset_type": r[11] or "Aksje",
                "units_label": r[12] or "shares",
                "currency": r[13] or "",
                "nav_date": r[14] or "",
                "purchase_mode": r[15] or "",
            }

        cur.execute("""
            SELECT time, type, ticker, price, shares, amount, confidence, pnl_pct, reason,
                   COALESCE(asset_type, '') AS asset_type,
                   COALESCE(currency, '') AS currency,
                   COALESCE(nav_date, '') AS nav_date,
                   COALESCE(order_kind, '') AS order_kind
            FROM paper_trades
            ORDER BY id DESC
            LIMIT 300
        """)
        trades = []
        for r in cur.fetchall():
            trades.append({
                "time": r[0],
                "type": r[1],
                "ticker": r[2],
                "price": float(r[3]),
                "shares": float(r[4]),
                "amount": float(r[5]),
                "confidence": int(r[6] or 0),
                "pnl_pct": None if r[7] is None else float(r[7]),
                "reason": r[8] or "",
                "asset_type": r[9] or "",
                "currency": r[10] or "",
                "nav_date": r[11] or "",
                "order_kind": r[12] or "",
            })

        conn.close()
        portfolio = _merge_portfolio({"cash": cash, "positions": positions, "trades": trades})
        storage = _storage()
        if storage is not None:
            try:
                storage.write_json(STORAGE_KEY, portfolio)
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
        return portfolio
    except Exception as e:
        print(f"paper_portfolio load DB fallback: {e}")
        return _load_json()

def save_portfolio(portfolio):
    portfolio = _merge_portfolio(portfolio)
    if not using_postgres():
        _save_json(portfolio)
        return False

    try:
        init_db()
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "UPDATE paper_state SET cash=%s, updated_at=%s WHERE id=1",
            (float(portfolio.get("cash", 0)), datetime.now().isoformat(timespec="seconds")),
        )

        cur.execute("DELETE FROM paper_positions")
        for ticker, pos in portfolio.get("positions", {}).items():
            entry = float(pos.get("entry_price", 0))
            cur.execute("""
                INSERT INTO paper_positions
                (ticker, shares, entry_price, avg_price, last_price, stop_loss, take_profit,
                 trailing_stop, highest_price, confidence, reason, opened_at, asset_type, units_label, currency, nav_date, purchase_mode)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                ticker,
                float(pos.get("shares", 0)),
                entry,
                entry,
                float(pos.get("last_price", 0)),
                float(pos.get("stop_loss", 0)),
                float(pos.get("take_profit", 0)),
                float(pos.get("trailing_stop", 0)),
                float(pos.get("highest_price", pos.get("last_price", 0))),
                int(pos.get("confidence", 0)),
                pos.get("reason", ""),
                pos.get("opened_at", ""),
                pos.get("asset_type", "Aksje"),
                pos.get("units_label", "shares"),
                pos.get("currency", ""),
                pos.get("nav_date", ""),
                pos.get("purchase_mode", ""),
            ))

        conn.commit()
        conn.close()
        storage = _storage()
        if storage is not None:
            try:
                storage.write_json(STORAGE_KEY, portfolio)
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
        return True
    except Exception as e:
        print(f"paper_portfolio save DB fallback: {e}")
        _save_json(portfolio)
        return False

def add_trade(portfolio, trade):
    trade["time"] = datetime.now().isoformat(timespec="seconds")
    portfolio["trades"].insert(0, trade)

    if using_postgres():
        init_db()
        conn = get_conn()
        cur = conn.cursor()
        # Compatibility with old Render Postgres table where id is NOT NULL without SERIAL default.
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM paper_trades")
        next_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO paper_trades
            (id, time, type, ticker, price, shares, amount, confidence, pnl_pct, reason, asset_type, currency, nav_date, order_kind)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            next_id,
            trade["time"],
            trade["type"],
            trade["ticker"],
            float(trade["price"]),
            float(trade["shares"]),
            float(trade["amount"]),
            int(trade.get("confidence", 0) or 0),
            trade.get("pnl_pct"),
            trade.get("reason", ""),
            trade.get("asset_type", ""),
            trade.get("currency", ""),
            trade.get("nav_date", ""),
            trade.get("order_kind", ""),
        ))
        conn.commit()
        conn.close()
        save_portfolio(portfolio)
    else:
        save_portfolio(portfolio)

def reset_portfolio(start_cash=100000.0):
    p = {"cash": float(start_cash), "positions": {}, "trades": [], "fund_savings_plans": []}
    if using_postgres():
        init_db()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM paper_positions")
        cur.execute("DELETE FROM paper_trades")
        cur.execute(
            "UPDATE paper_state SET cash=%s, updated_at=%s WHERE id=1",
            (float(start_cash), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        conn.close()
    else:
        save_portfolio(p)
    return p

def storage_status():
    try:
        from services.storage_service import storage_status_label
        return storage_status_label()
    except Exception:
        return "Postgres/DATABASE_URL ✅" if using_postgres() else "Lokal JSON fallback ⚠️"

def force_schema_fix():
    return init_db()


# -------------------------------------------------------------------
# Compatibility fix for scanner_worker.py
# Some restored cron versions import:
#   from paper_store import force_schema_migration
# This keeps old and new code compatible.
# -------------------------------------------------------------------
def force_schema_migration():
    """
    Kjører DB schema/migration trygt.
    Returnerer True/False, men krasjer ikke appen hvis DB ikke er aktiv.
    """
    try:
        if "init_db" in globals():
            return bool(init_db())
        if "force_schema_fix" in globals():
            return bool(force_schema_fix())
        return True
    except Exception as e:
        print(f"force_schema_migration failed: {e}")
        return False


def force_schema_fix():
    """
    Alias brukt av noen UI-versjoner.
    """
    return force_schema_migration()
