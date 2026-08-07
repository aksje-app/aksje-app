from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime, timezone

import market_intelligence as mi
import paper_autonomy_bridge as bridge
import paper_scanner_runtime


def test_authoritative_cron_claims_recent_slot_after_process_start(monkeypatch):
    monkeypatch.setattr(
        mi, "SCHEDULER_OBSERVATION_STARTED_AT_UTC_V19220_RC13",
        datetime(2026, 8, 7, 7, 0, 20, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(mi, "load_job_history", lambda limit=1000: [])
    job = mi.JobProfile(
        name="Morgenanalyse", job_id="MIJ-CRON", enabled=True,
        schedules=["09:00"], weekdays=[0, 1, 2, 3, 4],
        timezone_name="Europe/Oslo", last_run_at="",
    )
    now = datetime(2026, 8, 7, 7, 5, tzinfo=timezone.utc)

    web = mi._due_slot_info(job, now)
    cron = mi._due_slot_info(job, now, authoritative_unattended=True)

    assert web["unobserved_after_restart"] is True
    assert web["due"] is False
    assert cron["authoritative_slot_eligible"] is True
    assert cron["unobserved_after_restart"] is False
    assert cron["due"] is True


def test_authoritative_cron_does_not_replay_arbitrarily_old_slot(monkeypatch):
    monkeypatch.setenv("REPORT_CRON_CATCHUP_MINUTES", "30")
    monkeypatch.setattr(
        mi, "SCHEDULER_OBSERVATION_STARTED_AT_UTC_V19220_RC13",
        datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(mi, "load_job_history", lambda limit=1000: [])
    job = mi.JobProfile(
        name="Morgenanalyse", enabled=True, schedules=["09:00"],
        weekdays=[0, 1, 2, 3, 4], timezone_name="Europe/Oslo",
    )
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

    result = mi._due_slot_info(job, now, authoritative_unattended=True)

    assert result["authoritative_slot_eligible"] is False
    assert result["due"] is False


def _memory_bridge(monkeypatch):
    memory = {}
    monkeypatch.setattr(bridge, "write_json", lambda key, path, value: memory.update({key: json.loads(json.dumps(value))}))
    monkeypatch.setattr(bridge, "read_json", lambda key, path, default: json.loads(json.dumps(memory.get(key, default))))
    return memory


def test_paper_bridge_is_checksum_verified_observational_input(monkeypatch):
    _memory_bridge(monkeypatch)
    snapshot = {
        "snapshot_id": "MS-PAPER", "run_id": "PAPER-1", "checksum": "market-check",
        "captured_at": bridge._now(),
        "candidates": [{
            "ticker": "DNB.OL", "candidate_snapshot_id": "CS-DNB",
            "checksum": "candidate-check", "captured_at": bridge._now(),
            "price": 309.1, "technical": {"rsi": 75.1},
        }],
    }
    parallel = {"decisions": [{
        "ticker": "DNB.OL", "strategy_family": "technical",
        "strategy_id": "technical_benchmark", "action": "SELL",
        "score": 76, "confidence": 76, "execution_authorized": False,
    }]}
    bridge.publish_paper_engine_handoff(run_id="PAPER-1", market_snapshot=snapshot, parallel_result=parallel)
    candidates = [{"ticker": "DNB.OL", "investment_score": 81.25, "portfolio_action": "BUY"}]

    summary = bridge.attach_paper_engine_inputs(candidates)

    assert summary["available"] is True
    assert summary["matched_candidates"] == 1
    assert candidates[0]["investment_score"] == 81.25
    assert candidates[0]["portfolio_action"] == "BUY"
    paper_input = candidates[0]["paper_engine_input"]
    assert paper_input["technical"]["rsi"] == 75.1
    assert paper_input["technical_decisions"][0]["action"] == "SELL"
    assert paper_input["execution_authorized"] is False


def test_corrupt_paper_bridge_is_rejected(monkeypatch):
    memory = _memory_bridge(monkeypatch)
    bridge.publish_paper_engine_handoff(
        run_id="PAPER-2",
        market_snapshot={"snapshot_id": "MS-2", "candidates": []},
        parallel_result={},
    )
    memory[bridge.BRIDGE_KEY]["candidate_count"] = 999

    result = bridge.load_paper_engine_handoff()

    assert result["available"] is False
    assert result["reason"] == "MISSING_OR_INVALID_CHECKSUM"


def test_render_blueprint_separates_web_and_authoritative_cron_flags():
    source = open("render.yaml", encoding="utf-8").read()
    web, cron = source.split("  - type: cron", 1)
    assert 'REPORT_SCHEDULER_ENABLED\n        value: "false"' in web
    assert 'REPORT_SCHEDULER_ENABLED\n        value: "true"' in cron
    assert "startCommand: python scheduled_runner.py" in cron


def test_paper_scanner_has_durable_status_and_global_coordination(monkeypatch):
    statuses = []
    monkeypatch.setattr(paper_scanner_runtime, "write_scanner_status", lambda value: statuses.append(dict(value)))
    monkeypatch.setattr(paper_scanner_runtime, "paper_scanner_global_lock", lambda: nullcontext(True))

    result = paper_scanner_runtime.run_coordinated(lambda force=False: 2, force=False)

    assert result == 2
    assert statuses[0]["state"] == "RUNNING"
    assert statuses[-1]["state"] == "COMPLETED"
    assert statuses[-1]["trades_executed"] == 2


def test_paper_scanner_skips_when_another_cron_holds_lock(monkeypatch):
    statuses = []
    monkeypatch.setattr(paper_scanner_runtime, "write_scanner_status", lambda value: statuses.append(dict(value)))
    monkeypatch.setattr(paper_scanner_runtime, "paper_scanner_global_lock", lambda: nullcontext(False))
    run_impl = lambda force=False: (_ for _ in ()).throw(AssertionError("must not run"))

    assert paper_scanner_runtime.run_coordinated(run_impl) == 0
    assert statuses[-1]["state"] == "SKIPPED_LOCKED"
