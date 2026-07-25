from __future__ import annotations

import json
from pathlib import Path

import operational_telemetry as ot


def _local_storage(monkeypatch, tmp_path: Path):
    kv = {}
    streams = {}

    def read_json(key, path, default):
        return json.loads(json.dumps(kv.get(key, default)))

    def write_json(key, path, value):
        kv[key] = json.loads(json.dumps(value, default=str))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, default=str), encoding="utf-8")

    def append_event(key, path, row):
        streams.setdefault(key, []).append(json.loads(json.dumps(row, default=str)))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str) + "\n")

    def read_events(key, path, limit=500):
        return list(streams.get(key, []))[-limit:]

    monkeypatch.setattr(ot, "read_json", read_json)
    monkeypatch.setattr(ot, "write_json", write_json)
    monkeypatch.setattr(ot, "append_event", append_event)
    monkeypatch.setattr(ot, "read_events", read_events)
    monkeypatch.setattr(ot, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(ot, "ERRORS_PATH", tmp_path / "errors.jsonl")
    monkeypatch.setattr(ot, "SOURCE_EVENTS_PATH", tmp_path / "source_health.jsonl")
    monkeypatch.setattr(ot, "TRACE_EVENTS_PATH", tmp_path / "traces.jsonl")
    monkeypatch.setattr(ot, "SOURCE_STATE_PATH", tmp_path / "source_state.json")
    monkeypatch.setattr(ot, "TRACE_INDEX_PATH", tmp_path / "trace_index.json")
    monkeypatch.setattr(ot, "TRACE_DIR", tmp_path / "traces")
    return kv, streams


def test_stable_error_codes_are_human_searchable():
    assert ot.stable_error_code("NEWS", "fetch_failed", "EFN") == "NEWS-EFN-0042"
    assert ot.stable_error_code("SCHEDULER", "scheduler_failed", "CYCLE") == "SCHEDULER-CYCLE-0001"


def test_run_trace_covers_start_stages_binding_and_completion(monkeypatch, tmp_path):
    _local_storage(monkeypatch, tmp_path)
    trace = ot.begin_run_trace(kind="REPORT", trigger="MANUAL", job_id="JOB-1")
    trace_id = trace["trace_id"]
    ot.mark_run_stage(trace_id, "MARKET_DATA", status="RUNNING", message="Henter data")
    ot.bind_run_trace(trace_id, run_id="MI-123", report_id="MI-123")
    ot.mark_run_stage(trace_id, "REPORT", status="COMPLETED", metrics={"pages": 4})
    final = ot.complete_run_trace(trace_id, status="COMPLETED")

    assert final["status"] == "COMPLETED"
    assert final["run_id"] == "MI-123"
    assert final["report_id"] == "MI-123"
    assert [row["stage"] for row in final["stages"]] == ["MARKET-DATA", "REPORT"]
    assert ot.list_run_traces(1)[0]["trace_id"] == trace_id


def test_source_health_alerts_after_three_failures(monkeypatch, tmp_path):
    _local_storage(monkeypatch, tmp_path)
    for _ in range(3):
        state = ot.record_source_attempt(
            source_id="efn", market="Sverige", publisher="EFN", url="https://efn.se/rss",
            success=False, response_ms=200, error="timeout",
        )
    assert state["consecutive_failures"] == 3
    assert state["alert"] is True
    assert state["error_code"] == "NEWS-EFN-0042"
    assert state["health_score"] <= 40


def test_source_volume_anomaly_uses_successful_history(monkeypatch, tmp_path):
    _local_storage(monkeypatch, tmp_path)
    for count in (20, 21, 19, 20, 22):
        ot.record_source_attempt(source_id="cnbc", market="USA", publisher="CNBC", success=True, article_count=count)
    state = ot.record_source_attempt(source_id="cnbc", market="USA", publisher="CNBC", success=True, article_count=1)
    assert state["volume_anomaly"] is True
    assert state["alert"] is True
    assert state["volume_baseline"] >= 19


def test_source_success_resets_failure_streak(monkeypatch, tmp_path):
    _local_storage(monkeypatch, tmp_path)
    ot.record_source_attempt(source_id="e24", publisher="E24", success=False, error="down")
    state = ot.record_source_attempt(source_id="e24", publisher="E24", success=True, article_count=12, response_ms=350)
    assert state["consecutive_failures"] == 0
    assert state["last_error"] == ""
    assert state["last_success_at"]


def test_report_wrapper_binds_and_completes_trace(monkeypatch):
    import market_intelligence as mi

    calls = []
    monkeypatch.setattr(ot, "begin_run_trace", lambda **kwargs: {"trace_id": "TRACE-1"})
    monkeypatch.setattr(ot, "mark_run_stage", lambda *args, **kwargs: calls.append(("stage", args, kwargs)) or {})
    monkeypatch.setattr(ot, "bind_run_trace", lambda *args, **kwargs: calls.append(("bind", args, kwargs)) or {})
    monkeypatch.setattr(ot, "complete_run_trace", lambda *args, **kwargs: calls.append(("complete", args, kwargs)) or {})
    monkeypatch.setattr(mi, "_run_job_impl", lambda *args, **kwargs: {"run_id": "MI-1", "errors": [], "warnings": [], "candidates": [1], "proposals": []})

    class Job:
        job_id = "JOB-1"
        name = "Testjobb"
        markets = ["Norge"]

    result = mi.run_job(Job())
    assert result["operations_trace_id"] == "TRACE-1"
    assert any(row[0] == "bind" and row[2].get("run_id") == "MI-1" for row in calls)
    assert any(row[0] == "complete" and row[2].get("status") == "COMPLETED" for row in calls)


def test_rss_fallback_and_stale_cache_are_traceable(monkeypatch):
    import news_source_registry as registry

    events = []
    attempts = []

    def fake_fetch(url):
        if "primary" in url:
            raise RuntimeError("primary down")
        return "<rss><channel><item><title>Equinor result</title><link>https://example.test/a</link></item></channel></rss>", "STALE_FALLBACK", 120.0

    monkeypatch.setattr(registry, "_fetch_feed_text", fake_fetch)
    monkeypatch.setattr(registry, "record_event", lambda *args, **kwargs: events.append((args, kwargs)) or {})
    monkeypatch.setattr(registry, "record_source_attempt", lambda **kwargs: attempts.append(kwargs) or {"health_score": 77, "alert": False})
    rows, meta = registry.fetch_rss_source({
        "id": "test_source", "publisher": "Test Source", "label": "Test Source RSS",
        "url": "https://primary.test/rss", "fallback_urls": ["https://fallback.test/rss"],
        "market": "Norge", "source_role": "PRIMARY_NEWS",
    }, ["equinor"])

    assert len(rows) == 1
    assert meta["fallback_used"] is True
    assert meta["cache_status"] == "STALE_FALLBACK"
    assert events and events[0][1]["error_code"] == "NEWS-TEST-SOURCE-0042"
    assert attempts[-1]["fallback_used"] is True


def test_telemetry_storage_failure_never_breaks_business_flow(monkeypatch):
    monkeypatch.setattr(ot, "append_event", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    monkeypatch.setattr(ot, "write_json", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    monkeypatch.setattr(ot, "read_json", lambda *args, **kwargs: {})
    event = ot.record_event("TEST", component="SYSTEM", message="still running")
    assert event["event"] == "TEST"
    state = ot.record_source_attempt(source_id="e24", publisher="E24", success=True, article_count=4)
    assert state["source_id"] == "e24"
