from pathlib import Path

from scheduler_event_system import DomainEventBus, DurableEventStore, SchedulerCoordinator


def test_event_is_persisted(tmp_path: Path):
    store = DurableEventStore(tmp_path / "events.jsonl")
    bus = DomainEventBus(store)
    event = bus.publish("trade.test", source="pytest", symbol="TEST")
    rows = store.recent(10)
    assert rows[-1]["event_id"] == event.event_id
    assert rows[-1]["payload"]["symbol"] == "TEST"


def test_scheduler_records_success(tmp_path: Path):
    bus = DomainEventBus(DurableEventStore(tmp_path / "events.jsonl"))
    scheduler = SchedulerCoordinator(bus, tmp_path / "scheduler.json")
    scheduler.register("job", 60)
    assert scheduler.run_job("job", lambda: 42) == 42
    row = scheduler.snapshot()[0]
    assert row["last_status"] == "OK"
    assert row["success_count"] == 1


def test_scheduler_records_failure(tmp_path: Path):
    bus = DomainEventBus(DurableEventStore(tmp_path / "events.jsonl"))
    scheduler = SchedulerCoordinator(bus, tmp_path / "scheduler.json")
    scheduler.register("job", 60)
    try:
        scheduler.run_job("job", lambda: (_ for _ in ()).throw(ValueError("bad")))
    except ValueError:
        pass
    row = scheduler.snapshot()[0]
    assert row["last_status"] == "ERROR"
    assert row["failure_count"] == 1
    assert "ValueError" in row["last_error"]


def test_scheduler_skips_disabled_job(tmp_path: Path):
    bus = DomainEventBus(DurableEventStore(tmp_path / "events.jsonl"))
    scheduler = SchedulerCoordinator(bus, tmp_path / "scheduler.json")
    scheduler.register("job", 60, enabled=False)
    assert scheduler.run_job("job", lambda: 42) is None
    row = scheduler.snapshot()[0]
    assert row["last_status"] == "DISABLED"
    assert row["skipped_count"] == 1
