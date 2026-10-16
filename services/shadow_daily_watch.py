"""Seven-day operational Shadow/learning watch with durable Pushover receipt.

No trades, no parameter changes. Cron calls this after learning maintenance.
"""
from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Any, Mapping

STATE_KEY = "monitoring/shadow_daily_watch_20261017.json"
START = date(2026, 10, 17)
END = date(2026, 10, 23)
ZONE = ZoneInfo("America/Fortaleza")


def assess_day(learning: Mapping[str, Any], shadow: Mapping[str, Any],
               guard: Mapping[str, Any]) -> dict[str, Any]:
    """Operational status, deliberately not an investment performance verdict."""
    checks = {
        "learning_maintenance_finished": bool(learning) and str(learning.get("status", "")).upper() not in {"FAILED", "ERROR", ""},
        "shadow_job_finished": bool(shadow) and str(shadow.get("status", "")).upper() not in {"FAILED", "ERROR", ""},
        "parameter_guard_finished": bool(guard) and str(guard.get("status", "")).upper() not in {"FAILED", "ERROR", ""},
        "no_production_trade_changes": learning.get("production_changed") is not True and shadow.get("production_changed") is not True,
    }
    # A completed check with zero matured outcomes is not proof of profit or failure;
    # it must be visible as a warning, never a false green economic validation.
    maturity = learning.get("matured", learning.get("matured_count"))
    warning = maturity in (0, "0", None)
    color = "RØD" if not all(checks.values()) else ("GUL" if warning else "GRØNN")
    return {"color": color, "checks": checks, "matured_observations": maturity,
            "strategy_validated": False, "warning": "Modne resultater ikke bekreftet" if warning else ""}


def run_daily_watch(learning: Mapping[str, Any], shadow: Mapping[str, Any],
                    guard: Mapping[str, Any], *, now: datetime | None = None,
                    read_state=None, write_state=None, sender=None) -> dict[str, Any]:
    today = (now or datetime.now(ZONE)).astimezone(ZONE).date()
    if not START <= today <= END:
        return {"status": "OUTSIDE_WATCH", "date": today.isoformat()}
    if read_state is None or write_state is None or sender is None:
        raise ValueError("Durable persistence and Pushover sender are required")
    prior = read_state(STATE_KEY) or {}
    if prior.get("date") == today.isoformat() and prior.get("sent") is True:
        return {"status": "ALREADY_SENT", "date": today.isoformat(), "delivery": "CONFIRMED"}
    assessment = assess_day(learning, shadow, guard)
    failures = [name for name, passed in assessment["checks"].items() if not passed]
    message = (
        f"Daglig Shadow/læring {today.isoformat()}: {assessment['color']}\n"
        f"Læring: {learning.get('status', 'UKJENT')} | Shadow: {shadow.get('status', 'UKJENT')}\n"
        f"Modne observasjoner: {assessment['matured_observations']}\n"
        f"Feilkontroller: {', '.join(failures) if failures else 'ingen'}\n"
        f"Strategi dokumentert forbedret: NEI\n"
        f"{assessment['warning']}\n"
        "Driftsstatus er ikke bevis for avkastning."
    )
    # Every day's report carries its date, so notifier fingerprint dedupe can
    # prevent duplicates without suppressing successive daily reports.
    ok, detail = sender(message, title="Shadow og læring: daglig kontroll",
                        priority=1 if assessment["color"] == "RØD" else 0)
    result = {"date": today.isoformat(), "status": assessment["color"],
              "sent": bool(ok), "delivery": "CONFIRMED" if ok else "FAILED",
              "delivery_detail": str(detail or "")[:180], "assessment": assessment}
    write_state(STATE_KEY, result)
    return result
