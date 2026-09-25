"""Small durable screen snapshots and bounded, opt-in retention."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path


ROOT = "quality_valuation"
LATEST = f"{ROOT}/latest"


def _path(key: str) -> Path:
    return runtime_data_path(*key.split("/"))


def load_latest() -> dict[str, Any]:
    value = read_json(LATEST, _path(LATEST), {})
    return dict(value) if isinstance(value, dict) else {}


def recent_report_summary(*, max_age_hours: int = 24) -> dict[str, Any]:
    """A dated manual snapshot, never a claim that the scheduled job rescreened."""
    latest = load_latest()
    if not latest or latest.get("state") != "COMPLETED":
        return {}
    try:
        generated = datetime.fromisoformat(str(latest["generated_at"]).replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
        if age < timedelta(0) or age > timedelta(hours=max_age_hours):
            return {}
    except (ValueError, KeyError, TypeError):
        return {}
    groups = latest.get("groups") or {}
    return {
        "generated_at": latest["generated_at"], "run_key": latest.get("run_key"),
        "status": latest.get("state"), "manual_shadow": True,
        "changes": dict(latest.get("changes") or {}),
        "top": [{"ticker": row.get("ticker"), "group": name,
                 "entry_range_scenario": row.get("entry_range_scenario"),
                 "financial_date": row.get("financial_date")}
                for name in ("Attraktivt priset kandidat", "Kvalitetsselskap", "Dyr kvalitet / følges")
                for row in (groups.get(name) or [])[:3]],
    }


def persist_screen(result: dict[str, Any]) -> str:
    generated = datetime.fromisoformat(str(result["generated_at"]).replace("Z", "+00:00"))
    run_key = f"{ROOT}/runs/{generated.strftime('%Y%m%dT%H%M%S%f')}"
    previous = load_latest()
    old = {name: {row["ticker"] for row in (previous.get("groups") or {}).get(name, [])}
           for name in ("Attraktivt priset kandidat", "Kvalitetsselskap", "Dyr kvalitet / følges")}
    new = {name: {row["ticker"] for row in (result.get("groups") or {}).get(name, [])}
           for name in old}
    comparable = (bool(previous) and previous.get("state") == result.get("state") == "COMPLETED"
                  and previous.get("assumed_pe") == result.get("assumed_pe")
                  and set(previous.get("selected_symbols") or []) == set(result.get("selected_symbols") or []))
    changes = ({"comparable": True,
                "new_attractive": sorted(new["Attraktivt priset kandidat"] - old["Attraktivt priset kandidat"]),
                "lost_attractive": sorted(old["Attraktivt priset kandidat"] - new["Attraktivt priset kandidat"])}
               if comparable else {"comparable": False, "reason": "Første kjøring, andre aksjer, endret P/E-forutsetning eller ufullstendig kjøring"})
    snapshot = {**result, "run_key": run_key, "changes": changes}
    # Only completed/partial bounded runs. A failed latest write leaves the
    # immutable run accessible in storage diagnostics, never a false success.
    write_json(run_key, _path(run_key), snapshot)
    write_json(LATEST, _path(LATEST), snapshot)
    return run_key


def preview_expired_run_keys(names: list[str], *, days: int = 90, now: datetime | None = None) -> list[str]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max(1, days))
    expired: list[str] = []
    for name in names:
        if not name.startswith(f"{ROOT}/runs/"):
            continue
        stamp = name.removeprefix(f"{ROOT}/runs/")
        try:
            date = datetime.strptime(stamp, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if date < cutoff:
            expired.append(name)
    return sorted(expired)
