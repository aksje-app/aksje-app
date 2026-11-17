from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

import runtime_breadcrumbs as breadcrumbs
import runtime_memory
from services import oom_breadcrumb_budget as history, storage_service
from test_revision_trade_postgres import pg


@pytest.fixture(autouse=True)
def deterministic_memory(monkeypatch):
    monkeypatch.setattr(runtime_memory, "memory_snapshot", lambda: {"process_rss_mb": 42})
    monkeypatch.setattr(history, "process_budget", history.HistoryBudget())


def test_enabled_breadcrumb_keeps_latest_stdout_and_legacy_history(tmp_path, monkeypatch, capsys):
    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    storage.append_jsonl(breadcrumbs.EVENTS_KEY, {"stage": "legacy"})
    original = (tmp_path / breadcrumbs.EVENTS_KEY).read_bytes()

    marker = breadcrumbs.mark_breadcrumb("before-work", detail={"ticker": "ÅSE"})

    assert (tmp_path / breadcrumbs.EVENTS_KEY).read_bytes() == original
    assert storage.read_json(breadcrumbs.LATEST_KEY)["stage"] == "before-work"
    assert "OOM_BREADCRUMB stage=before-work" in capsys.readouterr().out
    assert marker["persisted"] is True
    history = breadcrumbs.read_breadcrumb_history()
    assert [entry["stage"] for entry in history] == ["before-work"]
    assert history[0]["detail"] == {"ticker": "ÅSE"}


def test_flag_defaults_to_legacy_append(tmp_path, monkeypatch):
    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED", raising=False)

    breadcrumbs.mark_breadcrumb("legacy-write")

    assert [entry["stage"] for entry in breadcrumbs.read_breadcrumb_history()] == ["legacy-write"]
    assert {path.name for path in (tmp_path / "runtime").iterdir()} == {
        "oom_breadcrumb_latest.json", "oom_breadcrumb_events.jsonl",
    }


def test_explicit_history_sources_remain_readable_after_flag_rollback(tmp_path, monkeypatch):
    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED", raising=False)
    breadcrumbs.mark_breadcrumb("legacy")

    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    breadcrumbs.mark_breadcrumb("rolling")
    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history(source="legacy")] == ["legacy"]

    monkeypatch.delenv("STORAGE_SHARED_REFERENCES_ENABLED")
    breadcrumbs.mark_breadcrumb("after-rollback")

    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history()] == ["legacy", "after-rollback"]
    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history(source="rolling")] == ["rolling"]


def test_rolling_slots_filter_expired_events_and_keep_byte_and_count_bounds(tmp_path, monkeypatch):
    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "true")
    monkeypatch.setattr(history, "_SLOT_COUNT", 3)
    monkeypatch.setattr(history, "_SLOT_BYTES", 512)
    now = datetime.now(timezone.utc)

    def marker_at(age):
        return (now - timedelta(days=age)).isoformat(timespec="milliseconds")

    monkeypatch.setattr(breadcrumbs, "_now", lambda: marker_at(15))
    breadcrumbs.mark_breadcrumb("expired")
    monkeypatch.setattr(breadcrumbs, "_now", lambda: marker_at(13))
    breadcrumbs.mark_breadcrumb("in-window")
    monkeypatch.setattr(breadcrumbs, "_now", lambda: marker_at(0))
    breadcrumbs.mark_breadcrumb("third", detail={"multibyte": "🙂" * 250})

    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history()] == ["in-window", "third"]
    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history(1)] == ["third"]
    assert breadcrumbs.read_breadcrumb_history(0) == []
    assert storage.read_json(breadcrumbs.LATEST_KEY)["history_omitted"] == 1
    assert breadcrumbs.read_breadcrumb_history(1)[0].get("detail") is None

    breadcrumbs.mark_breadcrumb("fourth")
    breadcrumbs.mark_breadcrumb("fifth")
    slots = list((tmp_path / "runtime/oom_breadcrumb_history_v1").glob("slot-*.json"))
    assert len(slots) == 3
    assert all(path.stat().st_size <= 512 for path in slots)
    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history()] == ["third", "fourth", "fifth"]


def test_process_budget_reports_omissions_without_losing_latest(tmp_path, monkeypatch, capsys):
    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    monkeypatch.setattr(history, "_BUDGET_BYTES", 600)

    for index in range(8):
        breadcrumbs.mark_breadcrumb(f"step-{index}", detail={"ticker": "X" * 300})

    slots = list((tmp_path / "runtime/oom_breadcrumb_history_v1").glob("slot-*.json"))
    assert 0 < sum(path.stat().st_size for path in slots) <= 600
    assert [entry["stage"] for entry in breadcrumbs.read_breadcrumb_history()] == ["step-0"]
    marker = storage.read_json(breadcrumbs.LATEST_KEY)
    assert marker["stage"] == "step-7"
    assert marker["history_omitted"] == 7
    assert "persisted=True history_omitted=7" in capsys.readouterr().out


def test_report_budget_resets_for_consecutive_and_nested_runs(tmp_path, monkeypatch):
    import market_intelligence as reporting
    import operational_telemetry

    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    monkeypatch.setattr(history, "_BUDGET_BYTES", 600)
    monkeypatch.setattr(operational_telemetry, "complete_run_trace", lambda *args, **kwargs: None)

    def mark(stage):
        return breadcrumbs.mark_breadcrumb(stage, detail={"ticker": "X" * 300})

    def run(trigger):
        return reporting._run_job_traced(None, trigger, None, False, None, False, None, "test")

    def run_impl(_job, *, trigger, **_kwargs):
        first = mark(f"{trigger}-first")
        if trigger == "outer":
            run("inner")
        second = mark(f"{trigger}-second")
        return {"omissions": [first["history_omitted"], second["history_omitted"]]}

    monkeypatch.setattr(reporting, "_run_job_impl", run_impl)
    mark("process-first")

    assert run("outer")["omissions"] == [0, 1]
    assert run("next-report")["omissions"] == [0, 1]
    assert mark("process-second")["history_omitted"] == 1
    assert [row["stage"] for row in breadcrumbs.read_breadcrumb_history()] == [
        "process-first", "outer-first", "inner-first", "next-report-first",
    ]


def test_failed_history_budget_does_not_interrupt_latest_or_stdout(tmp_path, monkeypatch, capsys):
    storage = storage_service.StorageService(tmp_path, mode="local")
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: storage)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")

    def unavailable(_payload):
        raise RuntimeError("history budget unavailable")

    monkeypatch.setattr(history.process_budget, "reserve", unavailable)
    marker = breadcrumbs.mark_breadcrumb("still-recoverable")

    assert storage.read_json(breadcrumbs.LATEST_KEY, {}).get("stage") == "still-recoverable"
    assert marker["persisted"] is True
    assert "OOM_BREADCRUMB stage=still-recoverable" in capsys.readouterr().out


def test_postgres_concurrent_slot_updates_are_serialized(pg, monkeypatch):
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: pg)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    monkeypatch.setattr(history, "_SLOT_COUNT", 9)
    monkeypatch.setattr(history, "_SLOT_BYTES", 512)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(breadcrumbs, "_now", lambda: (now - timedelta(days=15)).isoformat(timespec="milliseconds"))
    pg.append_jsonl(breadcrumbs.EVENTS_KEY, {"stage": "legacy"})
    breadcrumbs.mark_breadcrumb("expired")
    monkeypatch.setattr(breadcrumbs, "_now", lambda: now.isoformat(timespec="milliseconds"))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(breadcrumbs.mark_breadcrumb, [f"concurrent-{i}" for i in range(8)]))
    assert {row["stage"] for row in breadcrumbs.read_breadcrumb_history()} == {f"concurrent-{i}" for i in range(8)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(breadcrumbs.mark_breadcrumb, [f"wrapped-{i}" for i in range(8)]))
    rows = breadcrumbs.read_breadcrumb_history()
    assert len(rows) == 9
    assert {row["stage"] for row in rows[1:]} == {f"wrapped-{i}" for i in range(8)}
    assert pg.read_jsonl(breadcrumbs.EVENTS_KEY) == [{"stage": "legacy"}]
    conn = pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), MAX(octet_length(payload)) FROM app_kv_store WHERE name LIKE %s", (history._PREFIX + "slot-%",))
            count, largest = cur.fetchone()
            assert count == 9 and largest <= 512
            cur.execute("SELECT payload FROM app_kv_store WHERE name=%s", (history._COUNTER_KEY,))
            assert cur.fetchone()[0] == "17"
    finally:
        conn.close()


def test_postgres_failed_slot_rolls_back_counter_and_keeps_latest(pg, monkeypatch):
    monkeypatch.setattr(storage_service, "get_storage_service", lambda: pg)
    monkeypatch.setenv("STORAGE_SHARED_REFERENCES_ENABLED", "1")
    breadcrumbs.mark_breadcrumb("first")
    conn = pg._conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE FUNCTION reject_oom_slot() RETURNS trigger LANGUAGE plpgsql AS $$
                   BEGIN
                       IF NEW.name LIKE 'runtime/oom_breadcrumb_history_v1/slot-%'
                           AND NEW.payload LIKE '%reject-this-stage%' THEN
                           RAISE EXCEPTION 'controlled OOM slot rejection';
                       END IF;
                       RETURN NEW;
                   END $$;
                   CREATE TRIGGER reject_oom_slot BEFORE INSERT ON app_kv_store
                   FOR EACH ROW EXECUTE FUNCTION reject_oom_slot();"""
            )
        conn.commit()
    finally:
        conn.close()

    marker = breadcrumbs.mark_breadcrumb("reject-this-stage")

    assert marker["persisted"] is True
    assert marker["history_omitted"] == 0
    assert pg.read_json(breadcrumbs.LATEST_KEY)["stage"] == "reject-this-stage"
    assert pg.read_json(history._COUNTER_KEY) == 1
    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history()] == ["first"]

    breadcrumbs.mark_breadcrumb("after-failure")

    assert pg.read_json(history._COUNTER_KEY) == 2
    assert [event["stage"] for event in breadcrumbs.read_breadcrumb_history()] == ["first", "after-failure"]
