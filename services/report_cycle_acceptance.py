"""Small, observational proof of a new scheduled report on archived journals.

Acceptance proves lifecycle/resource completion only. It never changes source
coverage, financial readiness, trading permissions, or an existing report.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math
from zoneinfo import ZoneInfo

KEY = 'scheduler/report_cycle_acceptance.json'
SCHEMA = 1
CAP_MB = 2048.0
JOBS = {'MI-REQUIRED-MORNING': 8, 'MI-REQUIRED-AFTERNOON': 14, 'MI-REQUIRED-EVENING': 22}


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _time(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def evaluate(*, run, archive_status, context, completed_at, memory, delivery_receipt):
    """Evaluate explicit evidence; never infer delivery or success from existence."""
    run, archive, context, memory, delivery = map(_mapping, (run, archive_status, context, memory, delivery_receipt))
    blockers = []
    def require(condition, reason):
        if not condition:
            blockers.append(reason)

    run_id = str(run.get('run_id') or '')
    job_id = str(run.get('job_id') or '')
    planned = _time(run.get('scheduled_for'))
    started = _time(context.get('started_at'))
    execution = _time(run.get('execution_started_at'))
    created = _time(run.get('created_at'))
    completed = _time(completed_at)
    migrated = _time(archive.get('migration_completed_at'))
    sent = _time(delivery.get('sent_at'))
    require(archive.get('status') == 'VERIFIED' and bool(archive.get('period_id')) and bool(archive.get('semantic_sha256_before')) and archive.get('semantic_sha256_before') == archive.get('semantic_sha256_after'), 'archive_not_verified')
    require(context.get('authoritative_unattended') is True and bool(context.get('deployed_commit')), 'not_deployed_authoritative_scheduler')
    require(bool(run_id) and job_id in JOBS and run.get('trigger') == 'SCHEDULED', 'not_required_scheduled_report')
    require(planned is not None and job_id in JOBS and (planned.astimezone(ZoneInfo('Europe/Oslo')).hour, planned.astimezone(ZoneInfo('Europe/Oslo')).minute) == (JOBS[job_id], 0), 'not_fixed_slot')
    require(not any(run.get(key) for key in ('test_run', 'dry_run', 'suppress_notifications', 'source_draft_run_id')) and not _mapping(run.get('revalidation')).get('is_revalidation') and not _mapping(run.get('report_revision')).get('supersedes_run_id'), 'test_revision_or_promoted_report')
    require(all((planned, started, execution, created, completed, migrated)) and migrated <= planned <= started <= execution <= created <= completed, 'not_new_execution_after_archive')
    required = _mapping(run.get('autonomy_required_evaluation'))
    assessment = _mapping(run.get('portfolio_assessment_contract'))
    require(required.get('completed') is True and required.get('status') == 'COMPLETED' and _mapping(run.get('autonomous_chain')).get('status') in {'OK', 'COMPLETED'} and assessment.get('all_assessed') is True and assessment.get('reconciled_after_autonomy') is True, 'financial_evaluation_incomplete')
    require(_mapping(run.get('final_release_gate')).get('ok') is True and _mapping(run.get('report_status')).get('state') not in {'FAILED', 'FAILED_VALIDATION', 'CANCELLED'}, 'report_not_complete')
    pdf = _mapping(run.get('pdf_delivery'))
    require(all(pdf.get(key) is True for key in ('generated', 'validated', 'published', 'finalized_after_execution_receipt')), 'final_pdf_not_valid')
    require(delivery.get('run_id') == run_id and delivery.get('job_id') == job_id and delivery.get('scheduled_for') == run.get('scheduled_for') and delivery.get('sent') is True and delivery.get('attempted') is True and delivery.get('status') == 'SENT' and delivery.get('triggered_by') == 'SCHEDULED' and not delivery.get('test_run') and bool(delivery.get('notification_id')) and bool(delivery.get('report_url')) and sent is not None and execution is not None and completed is not None and execution <= sent <= completed and _mapping(run.get('notification')).get('sent') is True, 'delivery_not_confirmed')
    measured = {}
    for key in ('process_peak_rss_mb', 'cgroup_memory_peak_mb', 'process_rss_mb', 'cgroup_memory_current_mb'):
        value = memory.get(key)
        valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 < value <= CAP_MB
        require(valid, 'memory_unverified:' + key)
        if valid:
            measured[key] = value
    if blockers:
        return {'schema': SCHEMA, 'status': 'WAITING_FOR_HEAVY_REPORT', 'blockers': blockers, 'financial_state_changed': False}
    return {
        'schema': SCHEMA, 'status': 'HEAVY_REPORT_ACCEPTED', 'run_id': run_id,
        'job_id': job_id, 'scheduled_for': run['scheduled_for'], 'execution_started_at': run['execution_started_at'],
        'completed_at': completed_at, 'deployed_commit': context['deployed_commit'],
        'archive_period_id': archive['period_id'], 'archive_migration_completed_at': archive['migration_completed_at'],
        'archive_semantic_sha256': archive['semantic_sha256_after'],
        'report_state': str(_mapping(run.get('report_status')).get('state') or ''),
        'delivery_notification_id': str(delivery['notification_id']), 'delivery_sent_at': delivery['sent_at'],
        'memory': measured, 'memory_cap_mb': CAP_MB,
        'memory_scope': 'process_and_cgroup_lifetime_peaks_observed_at_report_completion',
        'checks': {'required_financial_evaluation_completed': True, 'autonomy_completed': True,
                   'portfolio_assessment_completed': True, 'final_release_gate_passed': True,
                   'final_pdf_validated': True, 'actual_delivery_receipt_confirmed': True,
                   'process_and_cgroup_observed_within_cap': True},
        'financial_state_changed': False, 'acceptance_scope': 'RESOURCE_AND_LIFECYCLE_ONLY',
    }


def _write_receipt(receipt):
    from durable_runtime import write_json
    from storage_architecture import runtime_data_path
    write_json(KEY, runtime_data_path('scheduler', 'report_cycle_acceptance.json'), receipt)


def record_completed_report(**evidence):
    receipt = evaluate(**evidence)
    if receipt['status'] == 'HEAVY_REPORT_ACCEPTED':
        _write_receipt(receipt)
    return receipt


def status(*, archive_status):
    """Read one small receipt; never load a report or journal to claim closure."""
    from durable_runtime import read_json
    from storage_architecture import runtime_data_path
    receipt = read_json(KEY, runtime_data_path('scheduler', 'report_cycle_acceptance.json'), {})
    archive = _mapping(archive_status)
    if isinstance(receipt, Mapping) and receipt.get('schema') == SCHEMA and receipt.get('status') == 'HEAVY_REPORT_ACCEPTED' and archive.get('status') == 'VERIFIED' and receipt.get('archive_period_id') == archive.get('period_id') and receipt.get('archive_semantic_sha256') == archive.get('semantic_sha256_after'):
        return dict(receipt)
    return {'schema': SCHEMA, 'status': 'WAITING_FOR_HEAVY_REPORT', 'financial_state_changed': False}
