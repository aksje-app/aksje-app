from test_revision_trade_postgres import pg

import durable_runtime
from services.report_run_retention import prune


def test_retention_preserves_latest_three_and_independent_projections(pg, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_RUN_RETENTION_ENABLED", "true")
    monkeypatch.setattr(durable_runtime, "get_storage_service", lambda: pg)
    reports = [f"MI-{number}" for number in range(6)]
    archive = [{"run_id": run} for run in reversed(reports)]
    pg.write_json("repositories/reports.json", archive)
    pg.write_json("market_intelligence/report_archive.json", archive)
    for report in reports:
        pg.write_json(f"market_intelligence/runs/{report}.json", {"run_id": report})
    for number in range(6):
        key = f"investment_pipeline/runs/IP-{number}.json"
        doc = {"run_id": f"IP-{number}", "proposals": [number]}
        pg.write_json_aliases(key, doc, aliases={
            f"investment_pipeline/proposals/IP-{number}_proposals.json": "proposals",
            "investment_pipeline/latest_run.json": None,
        })
    pg.write_json("market_intelligence/latest_run.json", {"run_id": reports[-1]})
    pg.write_json("controlled_learning/history/test.json", {"keep": True})
    mirror = tmp_path / "old-run.json"
    mirror.write_text('{"run_id":"MI-0"}')

    result = prune(storage=pg)

    assert result["removed"] == {"market_intelligence": 3, "investment_pipeline": 3}
    for family, prefix in (("market_intelligence", "MI"), ("investment_pipeline", "IP")):
        assert sorted(k for k in pg.list_json_names() if k.startswith(f"{family}/runs/")) == [
            f"{family}/runs/{prefix}-{number}.json" for number in range(3, 6)
        ]
        assert pg.read_json(f"{family}/latest_run.json")["run_id"] == f"{prefix}-5"
    assert pg.read_json("market_intelligence/report_archive.json") == archive[:3]
    assert pg.read_json("repositories/reports.json") == archive[:3]
    assert pg.read_json("investment_pipeline/proposals/IP-0_proposals.json") == [0]
    assert pg.read_json("controlled_learning/history/test.json") == {"keep": True}
    assert durable_runtime.read_json("market_intelligence/runs/MI-0.json", mirror, None) is None
    assert pg.read_json("market_intelligence/runs/MI-0.json") is None
    assert prune(storage=pg)["removed"] == {}


def test_retention_keeps_favorites_and_reports_waiting_for_revalidation(pg, monkeypatch):
    monkeypatch.setenv("REPORT_RUN_RETENTION_ENABLED", "true")
    archive = []
    for number in range(6):
        run = f"MI-{number}"
        pg.write_json(f"market_intelligence/runs/{run}.json", {"run_id": run})
        archive.insert(0, {"run_id": run, "favorite": number == 0, "revalidation_required": number == 1})
    pg.write_json("repositories/reports.json", archive)

    assert prune(storage=pg)["removed"] == {"market_intelligence": 1}
    assert pg.read_json("market_intelligence/runs/MI-0.json")
    assert pg.read_json("market_intelligence/runs/MI-1.json")
    assert pg.read_json("market_intelligence/runs/MI-2.json") is None
