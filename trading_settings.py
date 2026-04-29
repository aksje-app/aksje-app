
import json
import os

DEFAULT_RULES = {
    # BUY
    "min_buy_score": 7.5,
    "min_buy_confidence": 70,
    "max_buy_rsi": 72,
    "max_trades_per_day": 3,

    # HOLD
    "min_hold_days": 1,
    "ignore_small_moves_pct": 2.0,

    # SELL
    "enable_sell_signal_exit": True,
    "stop_loss_pct": 7.0,
    "take_profit_pct": 12.0,
    "rsi_exit_level": 75,
    "rsi_must_fall": True,
}

LOCAL_RULES_FILE = "trading_rules.json"


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
    except Exception:
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
    except Exception:
        return False


def load_rules():
    rules = DEFAULT_RULES.copy()

    db_rules = _load_from_db()
    if db_rules:
        rules.update(db_rules)
        return rules

    if os.path.exists(LOCAL_RULES_FILE):
        try:
            with open(LOCAL_RULES_FILE, "r", encoding="utf-8") as f:
                rules.update(json.load(f))
        except Exception:
            pass

    return rules


def save_rules(rules):
    clean = DEFAULT_RULES.copy()
    clean.update(rules)

    saved_db = _save_to_db(clean)

    # Lokal fallback for kjøring uten DATABASE_URL
    try:
        with open(LOCAL_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return saved_db


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

    if rules.get("enable_sell_signal_exit", True) and ("SELL" in signal or "AVOID" in signal):
        return True, "SELL signal"

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

    return False, "Hold"
