import logging
from utils import using_postgres  # v18.6.3 centralized helpers

import json
import os
import copy
import time
from pathlib import Path

try:
    import psycopg2
except Exception:
    psycopg2 = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SETTINGS_FILE = Path("app_settings.json")  # legacy fallback only
STORAGE_KEY = "settings/app_settings.json"
SETTINGS_CACHE_TTL_SECONDS = 2.0
_SETTINGS_CACHE = None
_SETTINGS_CACHE_AT = 0.0

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
    "background_scanning_enabled": False,
    "market_scanning_enabled": False,
    "drift_scheduler_enabled": False,
    "drift_paper_trading_enabled": False,
    "paper_trading_runtime_enabled": False,
    "paper_storage_enabled": False,
    "drift_background_enabled": False,
    "autonomy_enabled": False,
    "drift_activation_log": [],
    "full_stop_reason": "",
    "vacation_mode_enabled": False,
    "latest_buy_now_candidates": [],
    "live_banner_enabled": True,
    "display_timezone": "AUTO",
    "number_format_decimals": 2,
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


def _settings_repository():
    try:
        from repositories.application import get_repository_registry
        return get_repository_registry().documents
    except Exception:
        return None


def _merge(settings):
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    if isinstance(settings, dict):
        for k, v in settings.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out

def _registry_overlay(settings):
    """Central registry is authoritative; old settings remain the write-through fallback."""
    try:
        from autonomi_core.configuration.registry import migration_in_progress, read
        if migration_in_progress():
            return settings
        groups = {
            "discovery.scanner": ("markets", "max_tickers_per_market", "scan_top_picks_only"),
            "analysis.signals": ("min_buy_confidence", "min_buy_score"),
            "portfolio.paper_trading": ("max_open_positions", "max_trades_per_day", "position_size_pct"),
            "runtime.scanner": ("scan_interval_minutes", "background_scanning_enabled", "vacation_mode_enabled"),
            "notifications": ("pushover_enabled", "notify_paper_trades", "notify_watchlist_signal_changes", "notify_min_confidence"),
            "reporting.ui": ("ui_refresh_minutes", "ui_auto_refresh_enabled"),
        }
        merged = copy.deepcopy(settings)
        for root, keys in groups.items():
            section = read(root, {})
            if isinstance(section, dict):
                for key in keys:
                    if key in section:
                        merged[key] = copy.deepcopy(section[key])
        return merged
    except Exception:
        return settings

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
    global _SETTINGS_CACHE, _SETTINGS_CACHE_AT
    now = time.monotonic()
    if isinstance(_SETTINGS_CACHE, dict) and (now - _SETTINGS_CACHE_AT) <= SETTINGS_CACHE_TTL_SECONDS:
        return _registry_overlay(copy.deepcopy(_SETTINGS_CACHE))

    repository = _settings_repository()
    if repository is not None:
        try:
            stored = repository.read(STORAGE_KEY, default=None)
            if isinstance(stored, dict):
                merged = _merge(stored)
                _SETTINGS_CACHE = copy.deepcopy(merged)
                _SETTINGS_CACHE_AT = now
                return _registry_overlay(merged)
        except Exception as exc:
            logging.warning("Central settings repository read failed: %s", exc)

    # v19.2.0 compatibility migration from the legacy dedicated table.
    if using_postgres():
        try:
            init_settings_store()
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT settings_json FROM app_settings WHERE id=1")
            row = cur.fetchone()
            conn.close()
            if row:
                merged = _merge(json.loads(row[0]))
                if repository is not None:
                    repository.write(STORAGE_KEY, merged)
                _SETTINGS_CACHE = copy.deepcopy(merged)
                _SETTINGS_CACHE_AT = now
                return _registry_overlay(merged)
        except Exception as e:
            logging.warning("Legacy settings table migration failed: %s", e)

    # One-time legacy migration from old root file if present locally.
    if SETTINGS_FILE.exists():
        try:
            legacy = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = _merge(legacy)
            if repository is not None:
                repository.write(STORAGE_KEY, merged)
            _SETTINGS_CACHE = copy.deepcopy(merged)
            _SETTINGS_CACHE_AT = now
            return _registry_overlay(merged)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
    merged = _merge({})
    _SETTINGS_CACHE = copy.deepcopy(merged)
    _SETTINGS_CACHE_AT = now
    return _registry_overlay(merged)

def save_settings(settings):
    global _SETTINGS_CACHE, _SETTINGS_CACHE_AT
    settings = _merge(settings)
    try:
        from autonomi_core.configuration.registry import update
        groups = {
            "discovery.scanner": ("markets", "max_tickers_per_market", "scan_top_picks_only"),
            "analysis.signals": ("min_buy_confidence", "min_buy_score"),
            "portfolio.paper_trading": ("max_open_positions", "max_trades_per_day", "position_size_pct"),
            "runtime.scanner": ("scan_interval_minutes", "background_scanning_enabled", "vacation_mode_enabled"),
            "notifications": ("pushover_enabled", "notify_paper_trades", "notify_watchlist_signal_changes", "notify_min_confidence"),
            "reporting.ui": ("ui_refresh_minutes", "ui_auto_refresh_enabled"),
        }
        changes = {f"{root}.{key}": settings[key] for root, keys in groups.items() for key in keys if key in settings}
        update(changes, reason="Kompatibilitet: settings_store", actor="LEGACY_SETTINGS", compatibility=True)
    except Exception as exc:
        logging.warning("Central configuration write-through failed: %s", exc)
    repository = _settings_repository()
    if repository is not None:
        repository.write(STORAGE_KEY, settings)
        _SETTINGS_CACHE = copy.deepcopy(settings)
        _SETTINGS_CACHE_AT = time.monotonic()

    # Temporary v19.2.x compatibility mirror for deployments using app_settings.
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
            _SETTINGS_CACHE = copy.deepcopy(settings)
            _SETTINGS_CACHE_AT = time.monotonic()
            return True
        except Exception as e:
            print(f"save_settings DB fallback: {e}")
    # Last-resort local dev fallback only.
    if repository is None:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    _SETTINGS_CACHE = copy.deepcopy(settings)
    _SETTINGS_CACHE_AT = time.monotonic()
    return bool(repository and repository.storage.using_postgres())

def reset_settings():
    save_settings(DEFAULT_SETTINGS)
    return load_settings()

def enabled_markets(settings=None):
    s = settings or load_settings()
    return [k for k, v in s.get("markets", {}).items() if v]
