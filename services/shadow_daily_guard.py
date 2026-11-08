"""Continuous daily read-only Shadow / learning watchdog with Pushover receipts."""
from __future__ import annotations
from datetime import datetime, date, timezone, timedelta, time
from zoneinfo import ZoneInfo
from durable_runtime import read_events, read_json, write_json
from storage_architecture import runtime_data_path

START = date(2026, 10, 17)
LEDGER = "controlled_learning/daily_shadow_receipts.json"
LEDGER_PATH = runtime_data_path("controlled_learning", "daily_shadow_receipts.json")


def _activity_floor(now, schedules):
    """Keep the 24h check, extending only over a verified scheduled pause.

    An hour after a scheduled start allows the normal job to complete. Unknown
    schedules fail closed to the existing 24-hour rule. A pause cannot hide a
    missing run on the last expected workday.
    """
    normal = now - timedelta(days=1)
    expected_days = []
    for job in schedules:
        if not isinstance(job, dict) or job.get('enabled') is not True:
            continue
        try:
            tz = ZoneInfo(job.get('timezone_name') or 'Europe/Oslo')
            local = now.astimezone(tz)
            weekdays = set(job.get('weekdays') or [])
            for offset in range(8):
                day = local.date() - timedelta(days=offset)
                if day.weekday() not in weekdays or (day.weekday() >= 5 and not job.get('allow_weekends')):
                    continue
                passed = False
                for slot in job.get('schedules') or []:
                    hour, minute = map(int, str(slot).split(':'))
                    start = datetime.combine(day, time(hour, minute), tzinfo=tz)
                    passed |= start + timedelta(hours=1) <= local
                if passed:
                    expected_days.append(datetime.combine(day, time(), tzinfo=tz).astimezone(timezone.utc))
                    break
        except (ValueError, TypeError, KeyError):
            continue
    return min(normal, max(expected_days)) if expected_days else normal


def evaluate(now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Fortaleza")).date()
    audit = read_events("controlled_learning/outcome_audit.jsonl",
                        runtime_data_path("controlled_learning", "outcome_audit.jsonl"), limit=400)
    timed = []
    for row in audit:
        try:
            at = datetime.fromisoformat(str(row.get("at") or "").replace("Z", "+00:00"))
            if at.tzinfo is not None and at <= now:
                timed.append((at, row))
        except (TypeError, ValueError):
            continue
    window = [r for at, r in timed if at >= now - timedelta(days=1)]
    registered = [r for r in window if r.get("event") == "OBSERVATIONS_REGISTERED"]
    evaluated = [r for r in window if r.get("event") == "OUTCOMES_EVALUATED"]
    # Read the canonical job document directly; do not invoke load_jobs(),
    # repair configuration or change the operator's weekend choices here.
    registry = read_json('autonomi_core/configuration_registry.json',
                         runtime_data_path('autonomi_core', 'configuration_registry.json'), {})
    node = registry
    for key in ('values', 'runtime', 'scheduler'):
        node = node.get(key) if isinstance(node, dict) else None
    jobs = node.get('jobs', []) if isinstance(node, dict) else []
    jobs = [r for r in jobs if isinstance(r, dict) and str(r.get('job_id') or '').startswith('MI-REQUIRED-')] if isinstance(jobs, list) else []
    registration_floor = _activity_floor(now, jobs)
    evaluation_floor = _activity_floor(now, [dict(enabled=True, weekdays=list(range(5)),
        schedules=['06:30'], allow_weekends=False, timezone_name='Europe/Oslo')])
    expected_registered = [r for at, r in timed if at >= registration_floor and r.get('event') == 'OBSERVATIONS_REGISTERED']
    expected_evaluated = [r for at, r in timed if at >= evaluation_floor and r.get('event') == 'OUTCOMES_EVALUATED']
    acceptance = read_json("controlled_learning/acceptance_latest.json",
                           runtime_data_path("controlled_learning", "acceptance_latest.json"), {})
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    from services.learning_progress import snapshot
    progress = snapshot(lambda key: read_json(key, runtime_data_path(*key.split('/')), {}),
                        now=now, acceptance=acceptance)
    failures = []
    closed_collector = progress.get('closed_position_collector') or {}
    closed_results = progress.get('closed_position_results') or {}
    if closed_collector.get('status') == 'FAILED':
        failures.append('Resultatmåling for lukkede læringshandler har feilet')
    if closed_results.get('unmeasured',0) and not closed_results.get('pending_after_batch',0):
        failures.append('Lukkede læringshandler mangler verifiserbare indekskurser')
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
    if not expected_registered: failures.append("Ingen observasjonsregistrering siden siste planlagte kjøredag" if registration_floor < now-timedelta(days=1) else "Ingen observasjonsregistrering siste 24 t")
    if not expected_evaluated: failures.append("Ingen utfallsevaluering siden siste planlagte kjøredag" if evaluation_floor < now-timedelta(days=1) else "Ingen utfallsevaluering siste 24 t")
    if not acceptance: failures.append("Ingen aksept-/kvalitetsrapport")
    latest = max(expected_evaluated, key=lambda r: str(r.get("at") or ""), default={})
    production_changed = any(r.get("production_changed") is True for r in window)
    if production_changed: failures.append("Uventet endring i produksjon registrert")
    status = "RØD" if failures else ("GUL" if acceptance.get("strategy_readiness") != "VALIDATED" else "GRØNN")
    return {"date": today.isoformat(), "status": status, "failures": failures,
            "registrations": len(registered), "evaluations": len(evaluated),
            "new_observations": sum(int(r.get('created') or 0) for r in registered),
            "new_measurements": sum(int(r.get('updated') or 0) for r in evaluated),
            "active": latest.get("active"), "matured": latest.get("matured"),
            "scheduled_pause": registration_floor < now-timedelta(days=1) or evaluation_floor < now-timedelta(days=1),
            "registration_window_start": registration_floor.isoformat(),
            "evaluation_window_start": evaluation_floor.isoformat(),
            "last_registration_at": max((str(r.get('at') or '') for r in expected_registered), default=None),
            "last_evaluation_at": latest.get('at'),
            "strategy_readiness": acceptance.get("strategy_readiness", "UKJENT"),
            "production_changed": production_changed, "learning_progress": progress}


def send_daily_if_due(*, now=None, repair_id=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Fortaleza")).date()
    if today < START:
        return {"status": "OUTSIDE_MONITORING_WINDOW"}
    if now.astimezone(ZoneInfo("America/Fortaleza")).hour < 8:
        return {"status": "NOT_DUE_YET", "date": today.isoformat()}
    ledger = read_json(LEDGER, LEDGER_PATH, {})
    ledger = dict(ledger) if isinstance(ledger, dict) else {}
    # Explicit operator recovery can deliver corrected evidence once without
    # deleting/replacing the daily message the user already received.
    if repair_id is not None:
        if not isinstance(repair_id,str) or not repair_id.isalnum() or len(repair_id)>64:
            raise ValueError('A bounded alphanumeric repair ID is required')
    receipt_key = today.isoformat() + (':repair:'+repair_id if repair_id else '')
    prior = ledger.get(receipt_key, {})
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
    closed = progress.get('closed_position_results') or {}
    closed_excess = closed.get('mean_excess_return_pct')
    if closed_excess is not None:
        outcome += (f"\nLukkede: {closed.get('measured',0)}/{closed.get('closed_positions',0)} målt; mot indeks {closed_excess:+.2f} pp før kostnader; "
                    f"{closed.get('retrospective_comparators',0)} ettervalgte referanser.")
    validation_text = (f"Valideringsklare posisjoner: {progress.get('current_mature_positions','ukjent')}; "
                       f"benchmark-klare: {progress.get('benchmark_measured_positions','ukjent')}"
                       if closed_excess is not None else
                       f"Historisk baseline: {progress.get('historical_signal_count','ukjent')} signaler; "
                       f"modne strategiposisjoner: {progress.get('current_mature_positions','ukjent')}; "
                       f"benchmark-klare: {progress.get('benchmark_measured_positions','ukjent')}")
    labels = {'AUTONOMY':'Autonomi', 'SUPER_PORTFOLIO':'Superporteføljen', 'AUTONOMY_UNIVERSE':'Aksjeunivers'}
    streams = '\n'.join(f"{labels[name]}: {row.get('frames', 0)} rammer; sist {str(row.get('last_at') or 'ukjent')[:10]}; "
                        + (f"skygge {row.get('forward_trading_dates', 'ukjent')} datoer" if row.get('independent_strategy_test') else 'kun arkiv')
                        for name, row in progress.get('replay_streams', {}).items() if name in labels)
    failures = report['failures']
    diagnosis = (failures[0] + (f" (+{len(failures)-1} andre avvik)" if len(failures)>1 else '')) if failures else ('Planlagt pause; siste kjøredag kontrollert' if report.get('scheduled_pause') else 'Ingen manglende kjøringer')
    text = (f"Shadow og læring {report['date']}: {report['status']}\nAvvik: {diagnosis}\n"
            f"Kjøringer 24t: registrering {report['registrations']}, evaluering {report['evaluations']}\n"
            f"Aktive: {report['active']}; fullført 60d: {report['matured']}\n"
            f"Nye observasjoner: {report.get('new_observations', 'ukjent')}; nye målinger: {report.get('new_measurements', 'ukjent')}\n"
            f"Målt 1/5/20/60 handelsdager: {counts}\n{outcome}\n{streams}\n"
            f"Strategi: {report['strategy_readiness']}; prod endret: {report['production_changed']}\n"
            f"{validation_text}\n"
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
    if repair_id:
        report['repair_id'] = repair_id
    ledger[receipt_key] = report
    write_json(LEDGER, LEDGER_PATH, ledger)
    return report
