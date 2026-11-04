"""Read-only report must not re-fetch an already verified signed restart bundle."""
from unittest.mock import patch
import pytest
from services import simulation_restart as restart


def test_report_rejects_verified_bundle_from_another_period():
    with pytest.raises(ValueError, match="period mismatch"):
        restart.report("period-one", verified_bundle={"period_id": "period-two"})


def test_report_reuses_verified_bundle_without_storage_read():
    bundle = {"period_id": "period-one", "status": "PREPARED_NEW_PERIOD",
              "start_at": "2026-10-25T00:00:00+00:00", "archive": {},
              "capital_kind": "NOK", "historical_results_label": "old",
              "new_results_label": "new", "accounts": {family: {} for family in restart.CAPITALS}}
    class NoReadStorage:
        def read_json(self, *args, **kwargs):
            raise AssertionError("duplicate full bundle read")
    with patch.object(restart, "verify_bundle") as verify:
        with patch.object(restart.accounting, "report", return_value={"status": "ACTIVE"}):
            report = restart.report("period-one", storage=NoReadStorage(), verified_bundle=bundle)
    verify.assert_called_once_with(bundle)
    assert set(report["accounts"]) == set(restart.CAPITALS)
