
import json
import os
from pathlib import Path

try:
    import psycopg2
except Exception:
    psycopg2 = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SETTINGS_FILE = Path("app_settings.json")  # legacy fallback only
STORAGE_KEY = "settings/app_settings.json"

DEFAULT_SETTINGS = {
    "auto_trading_enabled": False,
    "auto_trading_paused": False,
    "auto_trading_emergency_stop": False,
    "auto_trading_safe_edit_mode": True,
    "auto_buy_safety_mode": True,
    "markets": {"USA": True, "NORGE": True, "SVERIGE": True},
    "max_tickers_per_market": 20,
    "min_buy_confidence": 70,
    "min_buy_score": 7.2,
    "max_open_positions": 5,
    "max_trades_per_day": 3,
    "position_size_pct": 10.0,
    "cooldown_minutes": 60,
    "pushover_enabled": True,
    "notify_paper_trades": True,
    "notify_watchlist_signal_changes": True,
    "notify_high_confidence_only": True,
    "notify_min_confidence": 80,
    "scan_top_picks_only": True,
    "last_scan_at": None,
    "pause_scanning_until": None,
    "scan_interval_minutes": 15,
    "background_scanning_enabled": True,
    "full_stop_reason": "",
    "vacation_mode_enabled": False,
    "latest_buy_now_candidates": [],
    "live_banner_enabled": True,
    "ui_refresh_minutes": 5,
    "ui_auto_refresh_enabled": False,
    "chart_auto_update_enabled": False,
    "live_banner_speed_seconds": 70,
    "live_banner_tickers": {
        "USA": "^GSPC, ^IXIC, ^DJI, AAPL, MSFT, NVDA",
        "Norge": "EQNR.OL, DNB.OL, NHY.OL, YAR.OL",
        "Sverige": "ATCO-A.ST, VOLV-B.ST, ERIC-B.ST, ABB.ST"
    }
}


def _storage():
    try:
        from services.storage_service import get_storage_service
        return get_storage_service()
    except Exception:
        return None

def using_postgres():
    return bool(DATABASE_URL) and psycopg2 is not None

def _merge(settings):
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    if isinstance(settings, dict):
        for k, v in settings.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out

def init_settings_store():
    if not using_postgres():
        return False
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY,
            settings_json TEXT NOT NULL
        );
    """)
    cur.execute("SELECT settings_json FROM app_settings WHERE id=1")
    if cur.fetchone() is None:
        cur.execute("INSERT INTO app_settings (id, settings_json) VALUES (1, %s)", (json.dumps(DEFAULT_SETTINGS),))
    conn.commit()
    conn.close()
    return True

def load_settings():
    if using_postgres():
        try:
            init_settings_store()
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT settings_json FROM app_settings WHERE id=1")
            row = cur.fetchone()
            conn.close()
            if row:
                return _merge(json.loads(row[0]))
        except Exception as e:
            print(f"load_settings DB fallback: {e}")
    storage = _storage()
    if storage is not None:
        stored = storage.read_json(STORAGE_KEY, default=None)
        if isinstance(stored, dict):
            return _merge(stored)

    # One-time legacy migration from old root file if present locally.
    if SETTINGS_FILE.exists():
        try:
            legacy = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = _merge(legacy)
            if storage is not None:
                storage.write_json(STORAGE_KEY, merged)
            return merged
        except Exception:
            pass
    return _merge({})

def save_settings(settings):
    settings = _merge(settings)
    if using_postgres():
        try:
            init_settings_store()
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO app_settings (id, settings_json)
                VALUES (1, %s)
                ON CONFLICT (id) DO UPDATE SET settings_json=EXCLUDED.settings_json
            """, (json.dumps(settings),))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"save_settings DB fallback: {e}")
    storage = _storage()
    if storage is not None:
        try:
            storage.write_json(STORAGE_KEY, settings)
            return False
        except Exception:
            pass
    # Last-resort local dev fallback only.
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    return False

def reset_settings():
    save_settings(DEFAULT_SETTINGS)
    return load_settings()

def enabled_markets(settings=None):
    s = settings or load_settings()
    return [k for k, v in s.get("markets", {}).items() if v]
