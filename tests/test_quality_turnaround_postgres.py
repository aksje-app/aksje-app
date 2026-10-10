"""Real DB checks for concurrent shadow observations and frozen evidence."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import pytest

URL = os.getenv("TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL runs in release CI")


@pytest.fixture
def postgres(monkeypatch):
    import psycopg2
    from services.storage_service import StorageService
    from quality_turnaround_shadow import KEY
    service = StorageService(database_url=URL, mode="postgres", allow_local_fallback=False)
    service.init_db()
    with psycopg2.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "entry_exit_test"
            cur.execute("DELETE FROM app_kv_store WHERE name=%s", (KEY,))
    monkeypatch.setattr("services.storage_service.get_storage_service", lambda: service)
    yield service
    service.delete_json(KEY)


def observation(now, price=10):
    return {"state": "COMPLETED", "run_key": "quality_valuation/runs/20261010T120000123456",
            "generated_at": now.isoformat(), "groups": {"test": [
                {"ticker": "NRC.OL", "price": price, "currency": "NOK", "observed_at": now.isoformat(),
                 "quality_evidence_ready": False, "turnaround": {"financial_improvement": True, "observed_at": now.isoformat()}}
            ]}}


def test_concurrent_sessions_record_one_cohort(postgres):
    from quality_turnaround_shadow import record, KEY
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: record(observation(now)), range(8)))
    assert all(len(receipt["cohorts"]) == 1 for receipt in receipts)
    assert len(postgres.read_json(KEY)["cohorts"]) == 1


def test_closed_evidence_survives_reloads_and_repeated_observation(postgres):
    from quality_turnaround_shadow import record, KEY
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    record(observation(now))
    later = observation(now + timedelta(days=31), price=9)
    closed = record(later)["cohorts"][0]
    assert closed["closed_at"] and closed["false_positive_count"] == 1
    assert closed["baseline"]["net_value"] == 100  # empty baseline is cash
    record(later)
    assert postgres.read_json(KEY)["cohorts"][0] == closed
