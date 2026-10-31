"""Seven-day read-only Shadow / learning watchdog with Pushover receipts."""
from __future__ import annotations
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from durable_runtime import read_events, read_json, write_json
from storage_architecture import runtime_data_path

START = date(2026, 10, 17)
END = date(2026, 10, 23)
LEDGER = "controlled_learning/daily_shadow_receipts.json"
LEDGER_PATH = runtime_data_path("controlled_learning", "daily_shadow_receipts.json")


def evaluate(now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Fortaleza")).date()
    audit = read_events("controlled_learning/outcome_audit.jsonl",
                        runtime_data_path("controlled_learning", "outcome_audit.jsonl"), limit=400)
    window = []
    for row in audit:
        try:
            at = datetime.fromisoformat(str(row.get("at") or "").replace("Z", "+00:00"))
            if 0 <= (now - at).total_seconds() <= 86400:
                window.append(row)
        except (TypeError, ValueError):
            continue
    registered = [r for r in window if r.get("event") == "OBSERVATIONS_REGISTERED"]
    evaluated = [r for r in window if r.get("event") == "OUTCOMES_EVALUATED"]
    acceptance = read_json("controlled_learning/acceptance_latest.json",
                           runtime_data_path("controlled_learning", "acceptance_latest.json"), {})
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    failures = []
    if not registered: failures.append("Ingen observasjonsregistrering siste 24 t")
    if not evaluated: failures.append("Ingen utfallsevaluering siste 24 t")
    if not acceptance: failures.append("Ingen aksept-/kvalitetsrapport")
    latest = max(evaluated, key=lambda r: str(r.get("at") or ""), default={})
    production_changed = any(r.get("production_changed") is True for r in window)
    if production_changed: failures.append("Uventet endring i produksjon registrert")
    status = "RØD" if failures else ("GUL" if acceptance.get("strategy_readiness") != "VALIDATED" else "GRØNN")
    return {"date": today.isoformat(), "status": status, "failures": failures,
            "registrations": len(registered), "evaluations": len(evaluated),
            "active": latest.get("active"), "matured": latest.get("matured"),
            "strategy_readiness": acceptance.get("strategy_readiness", "UKJENT"),
            "production_changed": production_changed}


def send_daily_if_due(*, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Fortaleza")).date()
    if not START <= today <= END:
        return {"status": "OUTSIDE_MONITORING_WINDOW"}
    if now.astimezone(ZoneInfo("America/Fortaleza")).hour < 8:
        return {"status": "NOT_DUE_YET", "date": today.isoformat()}
    ledger = read_json(LEDGER, LEDGER_PATH, {})
    ledger = dict(ledger) if isinstance(ledger, dict) else {}
    prior = ledger.get(today.isoformat(), {})
    if isinstance(prior, dict) and prior.get("sent") is True:
        return {"status": "ALREADY_SENT", "date": today.isoformat()}
    report = evaluate(now)
    from notifier import send_pushover_alert, normalize_notification_result
    text = (f"Shadow og læring {report['date']}: {report['status']}\n"
            f"Registreringer 24t: {report['registrations']}; evalueringer: {report['evaluations']}\n"
            f"Aktive: {report['active']}; modne: {report['matured']}\n"
            f"Strategi: {report['strategy_readiness']}; prod endret: {report['production_changed']}\n"
            f"Avvik: {', '.join(report['failures']) if report['failures'] else 'Ingen manglende kjøringer'}")
    try:
        ok, detail = normalize_notification_result(send_pushover_alert(
            text, title=f"Shadow/læring daglig {report['status']}", relevance_event={"category": "routine"} if not report["failures"] else None))
    except Exception as exc:
        ok, detail = False, type(exc).__name__
    # A deduplicated notification is NOT proof of a new Pushover delivery.
    delivery = str(detail or "")
    actual_delivery = bool(ok) and "duplicate" not in delivery.lower()
    report.update({"sent": actual_delivery, "delivery": delivery[:180],
                   "delivery_status": "SENT" if actual_delivery else
                   ("DUPLICATE_SUPPRESSED" if ok else "FAILED")})
    ledger[today.isoformat()] = report
    write_json(LEDGER, LEDGER_PATH, ledger)
    return report
