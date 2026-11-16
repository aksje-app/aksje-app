from copy import deepcopy
import json

import pytest

from services import report_cycle_acceptance as acceptance


def evidence():
    return dict(
        run={
            'run_id': 'MI-NEW', 'job_id': 'MI-REQUIRED-EVENING', 'trigger': 'SCHEDULED',
            'scheduled_for': '2026-11-16T21:00:00+00:00',
            'created_at': '2026-11-16T21:01:00+00:00',
            'execution_started_at': '2026-11-16T21:00:01+00:00',
            'autonomy_required_evaluation': {'completed': True, 'status': 'COMPLETED'},
            'autonomous_chain': {'status': 'OK'},
            'portfolio_assessment_contract': {'all_assessed': True, 'reconciled_after_autonomy': True},
            'final_release_gate': {'ok': True},
            'report_status': {'state': 'SOURCE_LIMITED'},
            'pdf_delivery': {'validated': True, 'generated': True, 'published': True, 'finalized_after_execution_receipt': True},
            'notification': {'sent': True},
        },
        archive_status={'status': 'VERIFIED', 'period_id': 'period-1', 'migration_completed_at': '2026-11-16T14:00:00+00:00', 'semantic_sha256_before': 'abc', 'semantic_sha256_after': 'abc'},
        context={'started_at': '2026-11-16T21:00:00+00:00', 'authoritative_unattended': True, 'deployed_commit': 'a' * 40},
        completed_at='2026-11-16T21:10:00+00:00',
        memory={'process_peak_rss_mb': 1500, 'cgroup_memory_peak_mb': 1800, 'process_rss_mb': 1000, 'cgroup_memory_current_mb': 1600},
        delivery_receipt={'run_id': 'MI-NEW', 'job_id': 'MI-REQUIRED-EVENING', 'sent': True, 'attempted': True, 'status': 'SENT', 'triggered_by': 'SCHEDULED', 'sent_at': '2026-11-16T21:05:00+00:00', 'scheduled_for': '2026-11-16T21:00:00+00:00', 'report_url': 'https://example/report.pdf', 'notification_id': 'REPORT-MI-NEW-PUSHOVER'},
    )


def test_accepts_new_heavy_report_without_changing_source_limits():
    data = evidence()
    original = deepcopy(data)
    result = acceptance.evaluate(**data)
    assert result['status'] == 'HEAVY_REPORT_ACCEPTED'
    assert result['report_state'] == 'SOURCE_LIMITED'
    assert result['financial_state_changed'] is False
    assert data == original
    assert len(json.dumps(result)) < 4096


@pytest.mark.parametrize('field,value', [('trigger', 'REVALIDATION'), ('test_run', True), ('dry_run', True), ('source_draft_run_id', 'OLD'), ('revalidation', {'is_revalidation': True}), ('report_revision', {'supersedes_run_id': 'OLD'}), ('execution_started_at', '2026-11-16T13:00:00+00:00'), ('job_id', 'CUSTOM'), ('scheduled_for', '2026-11-16T20:00:00+00:00')])
def test_old_repaired_test_and_nonmandatory_reports_do_not_count(field, value):
    data = evidence()
    data['run'][field] = value
    assert acceptance.evaluate(**data)['status'] == 'WAITING_FOR_HEAVY_REPORT'


@pytest.mark.parametrize('section,field,value', [
    ('archive_status', 'status', 'PENDING'), ('archive_status', 'semantic_sha256_after', 'different'),
    ('context', 'authoritative_unattended', False), ('context', 'deployed_commit', ''),
    ('memory', 'process_peak_rss_mb', 2048.1), ('memory', 'cgroup_memory_peak_mb', None),
    ('memory', 'cgroup_memory_peak_mb', float('nan')),
    ('delivery_receipt', 'sent', False), ('delivery_receipt', 'run_id', 'OLD'),
    ('delivery_receipt', 'attempted', False), ('delivery_receipt', 'sent_at', '2026-11-16T13:00:00+00:00'),
])
def test_missing_or_failed_proof_never_passes(section, field, value):
    data = evidence()
    data[section][field] = value
    assert acceptance.evaluate(**data)['status'] == 'WAITING_FOR_HEAVY_REPORT'


@pytest.mark.parametrize('field,value', [('autonomy_required_evaluation', {'completed': False}), ('autonomous_chain', {'status': 'ERROR'}), ('portfolio_assessment_contract', {'all_assessed': False}), ('pdf_delivery', {'validated': False}), ('final_release_gate', {'ok': False})])
def test_required_lifecycle_evidence(field, value):
    data = evidence()
    data['run'][field] = value
    assert acceptance.evaluate(**data)['status'] == 'WAITING_FOR_HEAVY_REPORT'


def test_only_successful_new_proof_is_persisted(monkeypatch):
    writes = []
    monkeypatch.setattr(acceptance, '_write_receipt', lambda receipt: writes.append(receipt))
    data = evidence()
    data['run']['test_run'] = True
    acceptance.record_completed_report(**data)
    assert not writes
    data['run']['test_run'] = False
    acceptance.record_completed_report(**data)
    assert len(writes) == 1
    assert writes[0]['run_id'] == 'MI-NEW'


def test_slot_before_archive_is_not_future_acceptance():
    data = evidence()
    data['archive_status']['migration_completed_at'] = '2026-11-16T21:00:00.500000+00:00'
    data['context']['started_at'] = '2026-11-16T21:00:00.500000+00:00'
    assert acceptance.evaluate(**data)['status'] == 'WAITING_FOR_HEAVY_REPORT'


def test_small_status_invalidates_different_archive_period(monkeypatch):
    import durable_runtime
    data = evidence()
    receipt = acceptance.evaluate(**data)
    monkeypatch.setattr(durable_runtime, 'read_json', lambda *args: receipt)
    assert acceptance.status(archive_status=data['archive_status'])['status'] == 'HEAVY_REPORT_ACCEPTED'
    data['archive_status']['period_id'] = 'period-2'
    assert acceptance.status(archive_status=data['archive_status'])['status'] == 'WAITING_FOR_HEAVY_REPORT'


def test_completion_hook_reads_real_delivery_and_does_not_notify(monkeypatch):
    import sys
    from types import SimpleNamespace
    import market_intelligence as mi
    import runtime_memory
    data = evidence()
    writes = []
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'a' * 40)
    monkeypatch.setattr(mi, '_now_iso', lambda: data['completed_at'])
    monkeypatch.setattr(mi, '_read', lambda *args: {'MI-NEW': data['delivery_receipt']})
    monkeypatch.setattr(runtime_memory, 'memory_snapshot', lambda: data['memory'])
    monkeypatch.setitem(sys.modules, 'services.restart_payload_archive', SimpleNamespace(status=lambda: data['archive_status']))
    monkeypatch.setattr(acceptance, '_write_receipt', lambda receipt: writes.append(receipt))
    mi._record_scheduled_report_cycle_acceptance(data['run'], data['context']['started_at'])
    assert len(writes) == 1
    assert writes[0]['status'] == 'HEAVY_REPORT_ACCEPTED'


def test_acceptance_storage_failure_does_not_fail_completed_report(monkeypatch):
    import sys
    from types import SimpleNamespace
    import market_intelligence as mi
    monkeypatch.setitem(sys.modules, 'services.restart_payload_archive', SimpleNamespace(status=lambda: (_ for _ in ()).throw(RuntimeError('storage offline'))))
    monkeypatch.setattr(mi, '_read', lambda *args: {})
    breadcrumbs = []
    monkeypatch.setattr(mi, 'mark_breadcrumb', lambda *args, **kwargs: breadcrumbs.append(args))
    mi._record_scheduled_report_cycle_acceptance({}, '2026-11-16T21:00:00+00:00')
    assert breadcrumbs[0][0] == 'report:cycle_acceptance:unavailable'


@pytest.mark.parametrize('authoritative', [False, True])
def test_due_job_acceptance_hook_runs_only_in_authoritative_scheduler(monkeypatch, authoritative):
    import market_intelligence as mi
    job = mi.JobProfile(job_id='MI-REQUIRED-EVENING', name='Obligatorisk kveldsrapport', markets=['Norge'])
    monkeypatch.setattr(mi, 'load_jobs', lambda: [job])
    monkeypatch.setattr(mi, '_due_slot_info', lambda *args, **kwargs: {'due': True, 'previous_planned_utc': '2026-11-16T21:00:00+00:00'})
    monkeypatch.setattr(mi, 'upsert_job', lambda *args: None)
    monkeypatch.setattr(mi, '_append_job_history', lambda *args: None)
    monkeypatch.setattr(mi, '_audit', lambda *args: None)
    monkeypatch.setattr(mi, 'run_job', lambda *args, **kwargs: {'run_id': 'MI-NEW'})
    calls = []
    monkeypatch.setattr(mi, '_record_scheduled_report_cycle_acceptance', lambda *args: calls.append(args))
    result = mi.run_due_jobs(authoritative_unattended=authoritative)
    assert result == [{'run_id': 'MI-NEW'}]
    assert len(calls) == int(authoritative)
