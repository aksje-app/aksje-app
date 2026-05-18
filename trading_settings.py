import logging

import json
import os

DEFAULT_RULES = {
    # Portfolio / execution
    "start_cash": 100000.0,
    "position_size_pct": 10.0,
    "max_open_positions": 5,
    "max_trades_per_day": 3,

    # BUY
    "min_buy_score": 7.5,
    "min_buy_confidence": 70,
    "max_buy_rsi": 72,

    # HOLD
    "min_hold_days": 1,
    "use_noise_filter": False,
    "ignore_small_moves_pct": 1.0,

    # SELL
    "enable_sell_signal_exit": True,
    "stop_loss_pct": 7.0,
    "take_profit_pct": 12.0,
    "trailing_stop_pct": 8.0,
    "rsi_exit_level": 75,
    "rsi_must_fall": True,
}

LOCAL_RULES_FILE = "trading_rules.json"  # legacy fallback only
STORAGE_KEY = "settings/trading_rules.json"


def _storage():
    try:
        from services.storage_service import get_storage_service
        return get_storage_service()
    except Exception:
        return None


def _load_from_db():
    try:
        from paper_store import init_store, get_conn, using_postgres
        init_store()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trading_rules (
            id INTEGER PRIMARY KEY,
            rules TEXT NOT NULL
        );
        """)
        cur.execute("SELECT rules FROM trading_rules WHERE id=1")
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        raw = row[0] if using_postgres() else row["rules"]
        return json.loads(raw)
    except Exception as e:
        print(f"trading_rules load DB failed: {e}")
        return None


def _save_to_db(rules):
    try:
        from paper_store import init_store, get_conn, using_postgres
        init_store()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trading_rules (
            id INTEGER PRIMARY KEY,
            rules TEXT NOT NULL
        );
        """)
        raw = json.dumps(rules, ensure_ascii=False)
        if using_postgres():
            cur.execute("""
            INSERT INTO trading_rules (id, rules) VALUES (1, %s)
            ON CONFLICT (id) DO UPDATE SET rules=EXCLUDED.rules
            """, (raw,))
        else:
            cur.execute("INSERT OR REPLACE INTO trading_rules (id, rules) VALUES (1, ?)", (raw,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"trading_rules save DB failed: {e}")
        return False


def load_rules():
    rules = DEFAULT_RULES.copy()
    db_rules = _load_from_db()
    if db_rules:
        rules.update(db_rules)
        return rules

    storage = _storage()
    if storage is not None:
        stored = storage.read_json(STORAGE_KEY, default=None)
        if isinstance(stored, dict):
            rules.update(stored)
            return rules

    # One-time legacy migration from old root file if present locally.
    if os.path.exists(LOCAL_RULES_FILE):
        try:
            with open(LOCAL_RULES_FILE, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            if isinstance(legacy, dict):
                rules.update(legacy)
                if storage is not None:
                    storage.write_json(STORAGE_KEY, rules)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return rules


def save_rules(rules):
    clean = DEFAULT_RULES.copy()
    clean.update(rules)
    saved_db = _save_to_db(clean)
    if saved_db:
        try:
            storage = _storage()
            if storage is not None:
                storage.write_json(STORAGE_KEY, clean)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
        return True
    storage = _storage()
    if storage is not None:
        try:
            storage.write_json(STORAGE_KEY, clean)
            return False
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    try:
        with open(LOCAL_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return False


def calc_stop_take(entry_price, rules=None):
    rules = rules or load_rules()
    entry_price = float(entry_price)
    stop_loss = entry_price * (1 - float(rules["stop_loss_pct"]) / 100)
    take_profit = entry_price * (1 + float(rules["take_profit_pct"]) / 100)
    return round(stop_loss, 2), round(take_profit, 2)


def should_buy(decision, rsi, rules=None):
    rules = rules or load_rules()
    signal = decision.get("decision", "")
    score = float(decision.get("decision_score", decision.get("score", 0)) or 0)
    confidence = int(decision.get("confidence", 0) or 0)

    return (
        "BUY" in signal
        and score >= float(rules["min_buy_score"])
        and confidence >= int(rules["min_buy_confidence"])
        and float(rsi or 50) <= float(rules["max_buy_rsi"])
    )


def should_sell(decision, position, current_price, rsi=None, prev_rsi=None, rules=None):
    rules = rules or load_rules()
    signal = decision.get("decision", "")
    entry = float(position.get("avg_price", position.get("entry_price", current_price)) or current_price)
    current_price = float(current_price)
    pnl_pct = ((current_price - entry) / entry * 100) if entry else 0

    # Risikoutganger skal alltid ha prioritet og skal aldri blokkeres av støyfilter.
    if pnl_pct <= -float(rules["stop_loss_pct"]):
        return True, f"Stop-loss {pnl_pct:.2f}%"

    if pnl_pct >= float(rules["take_profit_pct"]):
        return True, f"Take-profit {pnl_pct:.2f}%"

    rsi = float(rsi or 50)
    if rsi >= float(rules["rsi_exit_level"]):
        if not rules.get("rsi_must_fall", True):
            return True, f"RSI exit {rsi:.1f}"
        if prev_rsi is not None and rsi < float(prev_rsi):
            return True, f"RSI > {rules['rsi_exit_level']} og faller"

    # Støyfilter er valgfritt og gjelder kun SELL/AVOID-signal ved helt små bevegelser.
    # Det skal ikke hindre stop-loss, take-profit eller RSI-exit over.
    if rules.get("enable_sell_signal_exit", True) and ("SELL" in signal or "AVOID" in signal):
        if rules.get("use_noise_filter", False):
            noise_pct = abs(float(rules.get("ignore_small_moves_pct", 1.0) or 0))
            if abs(pnl_pct) < noise_pct:
                return False, f"Støyfilter: ignorerer liten bevegelse {pnl_pct:.2f}%"
        return True, "SELL/AVOID signal"

    return False, "Hold"
