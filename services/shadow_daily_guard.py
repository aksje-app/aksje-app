"""Continuous daily read-only Shadow / learning watchdog with Pushover receipts."""
from __future__ import annotations
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from durable_runtime import read_events, read_json, write_json
from storage_architecture import runtime_data_path

START = date(2026, 10, 17)
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
    from services.learning_progress import snapshot
    progress = snapshot(lambda key: read_json(key, runtime_data_path(*key.split('/')), {}),
                        now=now, acceptance=acceptance)
    failures = []
    if progress.get('archive_status') == 'STORAGE_BUDGET_REACHED':
        failures.append('Historikkarkivet er fullt; nye læringsrammer blir avvist')
    elif progress.get('archive_bytes') is not None and progress.get('archive_remaining_bytes',0) < 16*1024**2:
        failures.append('Læringsarkivet har under 16 MiB ledig; kapasitetstiltak kreves')
    for name, stream in progress.get('replay_streams', {}).items():
        try:
            last = datetime.fromisoformat(str(stream.get('last_at') or '').replace('Z', '+00:00'))
            if (now - last).total_seconds() > 72 * 3600:
                failures.append(name + ': ingen nye historikkrammer siste 72 t')
        except (TypeError, ValueError):
            if stream.get('frames'): failures.append(name + ': ugyldig siste datatidspunkt')
    if (progress.get('weekly_report') or {}).get('status') == 'PUSHOVER_FAILED':
        failures.append('Ukentlig læringsrapport er laget, men ikke levert på Pushover')
    if acceptance and not progress['acceptance_fresh']:
        failures.append('Aksept-/kvalitetsrapport mangler gyldig oppdatering siste 48 t')
    if not registered: failures.append("Ingen observasjonsregistrering siste 24 t")
    if not evaluated: failures.append("Ingen utfallsevaluering siste 24 t")
    if not acceptance: failures.append("Ingen aksept-/kvalitetsrapport")
    latest = max(evaluated, key=lambda r: str(r.get("at") or ""), default={})
    production_changed = any(r.get("production_changed") is True for r in window)
    if production_changed: failures.append("Uventet endring i produksjon registrert")
    status = "RØD" if failures else ("GUL" if acceptance.get("strategy_readiness") != "VALIDATED" else "GRØNN")
    return {"date": today.isoformat(), "status": status, "failures": failures,
            "registrations": len(registered), "evaluations": len(evaluated),
            "new_observations": sum(int(r.get('created') or 0) for r in registered),
            "new_measurements": sum(int(r.get('updated') or 0) for r in evaluated),
            "active": latest.get("active"), "matured": latest.get("matured"),
            "strategy_readiness": acceptance.get("strategy_readiness", "UKJENT"),
            "production_changed": production_changed, "learning_progress": progress}


def send_daily_if_due(*, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Fortaleza")).date()
    if today < START:
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
    progress = report.get("learning_progress") or {}
    measured = {row['horizon_days']: row for row in progress.get('measured_shadow_horizons', [])}
    counts = '/'.join(str((measured.get(day) or {}).get('measured_count', 0)) for day in (1, 5, 20, 60))
    current_results = measured.get(20) or measured.get(5) or measured.get(1) or {}
    returns = current_results.get('mean_return_pct')
    excess = current_results.get('mean_excess_return_pct')
    outcome = (f"Alle Shadow-grupper {current_results.get('horizon_days')}d: kurs {returns:+.2f} %, mot benchmark {excess:+.2f} pp. Ikke validert nettoeffekt."
               if returns is not None and excess is not None else 'Shadow-resultat: ingen målte kurshorisonter')
    labels = {'AUTONOMY':'Autonomi', 'SUPER_PORTFOLIO':'Superporteføljen', 'AUTONOMY_UNIVERSE':'Aksjeunivers'}
    streams = '\n'.join(f"{labels[name]}: {row.get('frames', 0)} rammer; sist {str(row.get('last_at') or 'ukjent')[:10]}; "
                        + (f"skygge {row.get('forward_trading_dates', 'ukjent')} datoer" if row.get('independent_strategy_test') else 'kun arkiv')
                        for name, row in progress.get('replay_streams', {}).items() if name in labels)
    failures = report['failures']
    diagnosis = (failures[0] + (f" (+{len(failures)-1} andre avvik)" if len(failures)>1 else '')) if failures else 'Ingen manglende kjøringer'
    text = (f"Shadow og læring {report['date']}: {report['status']}\nAvvik: {diagnosis}\n"
            f"Kjøringer 24t: registrering {report['registrations']}, evaluering {report['evaluations']}\n"
            f"Aktive: {report['active']}; fullført 60d: {report['matured']}\n"
            f"Nye observasjoner: {report.get('new_observations', 'ukjent')}; nye målinger: {report.get('new_measurements', 'ukjent')}\n"
            f"Målt 1/5/20/60 handelsdager: {counts}\n{outcome}\n{streams}\n"
            f"Strategi: {report['strategy_readiness']}; prod endret: {report['production_changed']}\n"
            f"Historisk baseline: {progress.get('historical_signal_count', 'ukjent')} signaler; "
            f"modne strategiposisjoner: {progress.get('current_mature_positions', 'ukjent')}; "
            f"benchmark-målte: {progress.get('benchmark_measured_positions', 'ukjent')}\n"
            f"Kvalitetsrapportens alder: {progress.get('acceptance_age_hours', 'ukjent')} timer")
    try:
        ok, detail = normalize_notification_result(send_pushover_alert(
            text, title=f"Shadow/læring daglig {report['status']}", relevance_event=None))
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
