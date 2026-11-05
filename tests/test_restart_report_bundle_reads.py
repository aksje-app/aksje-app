"""Regression: reporting must not deserialize the large NOK restart bundle per family."""
from services import simulation_restart as restart


def test_restart_report_reads_bundle_only_once(monkeypatch):
    period = "test-period"
    bundle = {
        "status": "PREPARED_NOT_ACTIVE", "start_at": "2026-10-25T01:21:18Z",
        "archive": {}, "capital_kind": "TEST",
        "historical_results_label": "historical", "new_results_label": "new",
        "accounts": {family: {"family": family} for family in restart.CAPITALS},
    }

    class Storage:
        def __init__(self):
            self.reads = 0
        def read_json(self, key, default=None):
            assert key == restart._key(period)
            self.reads += 1
            return bundle

    storage = Storage()
    monkeypatch.setattr(restart, "verify_bundle", lambda value: None)

    def report_family(family, doc, *, at=None):
        assert doc is bundle["accounts"][family]
        return {"family": family}

    monkeypatch.setattr(restart.accounting, "_report_verified", report_family)
    result = restart.report(period, storage=storage)
    assert storage.reads == 1
    assert set(result["accounts"]) == set(restart.CAPITALS)


def test_single_account_report_still_verifies_whole_bundle_and_only_builds_requested_account(monkeypatch):
    from services import restart_reporting
    from unittest.mock import Mock
    bundle = {'period_id': 'p', 'status': 'PREPARED_NOT_ACTIVE', 'start_at': '2026-10-25T01:21:18Z',
              'archive': {}, 'capital_kind': 'TEST', 'historical_results_label': 'historical',
              'new_results_label': 'new', 'accounts': {family: {'family': family} for family in restart.CAPITALS}}
    verification = Mock()
    monkeypatch.setattr(restart, 'verify_bundle', verification)
    built = []
    def report(family, doc, *, at=None):
        assert doc is bundle['accounts'][family]
        built.append(family)
        return {'status': 'ACTIVE', 'new_period': {'cash_nok': 1}}
    monkeypatch.setattr(restart.accounting, '_report_verified', report)
    monkeypatch.setattr(restart_reporting, '_nav_history', lambda period: [])
    result = restart_reporting.snapshot('p', 'paper', verified_bundle=bundle)
    verification.assert_called_once_with(bundle)
    assert built == ['paper']
    assert result['family'] == 'paper'
