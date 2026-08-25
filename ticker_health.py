"""Durable ticker health registry with temporary, automatically expiring quarantine."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path


KEY = "market_data/ticker_health.json"
PATH = runtime_data_path("market_data", "ticker_health.json")


def canonical_ticker(value: object) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict:
    value = read_json(KEY, PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def _save(value: dict) -> None:
    write_json(KEY, PATH, value)


def quarantine_status(ticker: object) -> dict:
    key = canonical_ticker(ticker)
    row = dict(_load().get(key) or {})
    raw_until = str(row.get("quarantined_until") or "")
    active = False
    if raw_until:
        try:
            until = datetime.fromisoformat(raw_until.replace("Z", "+00:00"))
            active = until.replace(tzinfo=until.tzinfo or timezone.utc) > _now()
        except ValueError:
            active = False
    return {"ticker": key, "active": active, **row}


def record_ticker_success(ticker: object) -> None:
    key = canonical_ticker(ticker)
    rows = _load()
    rows[key] = {
        **dict(rows.get(key) or {}), "consecutive_failures": 0,
        "last_success_at": _now().isoformat(timespec="seconds"),
        "quarantined_until": "", "last_error": "",
    }
    _save(rows)


def record_ticker_failure(ticker: object, reason: str) -> dict:
    key = canonical_ticker(ticker)
    rows = _load()
    row = dict(rows.get(key) or {})
    failures = int(row.get("consecutive_failures") or 0) + 1
    threshold = max(2, int(os.getenv("TICKER_QUARANTINE_FAILURES", "2") or 2))
    hours = max(1, int(os.getenv("TICKER_QUARANTINE_HOURS", "24") or 24))
    row.update({
        "consecutive_failures": failures, "failure_count": int(row.get("failure_count") or 0) + 1,
        "last_failure_at": _now().isoformat(timespec="seconds"), "last_error": str(reason or "NO_MARKET_DATA")[:300],
    })
    if failures >= threshold:
        row["quarantined_until"] = (_now() + timedelta(hours=hours)).isoformat(timespec="seconds")
        row["quarantine_reason"] = "REPEATED_NO_MARKET_DATA"
    rows[key] = row
    _save(rows)
    return {"ticker": key, **row}
