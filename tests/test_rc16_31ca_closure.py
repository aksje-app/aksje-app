import io
import json
import zipfile
from datetime import datetime, timezone

import learning_observation_engine as loe
import report_replay_export as rre


def test_single_report_package_contains_standard_technical_json_and_diagnostic(monkeypatch):
    run = {
        "version": "v19.22.0-rc16.31ca",
        "run_id": "MI-TEST",
        "report_id": "MI-TEST",
        "background_execution_id": "MBJ-TEST",
        "created_at": "2026-09-09T02:00:00+00:00",
        "markets": ["Norge"],
        "candidates": [],
    }
    monkeypatch.setattr(rre, "_build_canonical_pdf", lambda _run: b"%PDF-standard")
    monkeypatch.setattr(rre, "_build_canonical_technical_pdf", lambda _run: b"%PDF-technical")
    monkeypatch.setattr(rre, "_build_text", lambda _run: "report text")
    monkeypatch.setattr(rre, "_read_diagnostic_bundle", lambda _run, _entry=None: (b"PKdiagnostic", "diagnose.zip"))
    monkeypatch.setattr(rre, "classify_replay_case", lambda _run: ("FULL", []))
    import report_export_audit
    monkeypatch.setattr(report_export_audit, "canonical_public_run", lambda value: dict(value))
    monkeypatch.setattr(report_export_audit, "validate_artifacts", lambda **kwargs: {"ok": True, "errors": []})
    monkeypatch.setattr(report_export_audit, "validate_zip", lambda payload: {"ok": True, "errors": []})

    payload, manifest = rre.build_single_report_package(run)
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        names = set(zf.namelist())
        assert "report/report.pdf" in names
        assert "report/report_technical.pdf" in names
        assert "report/report.json" in names
        assert "diagnostics/diagnose.zip" in names
    assert manifest["artifact_roles"]["technical_pdf"] == "report/report_technical.pdf"
    assert manifest["diagnostic_available"] is True


def test_new_observation_before_next_trading_day_is_not_degraded(monkeypatch):
    obs = [{
        "observation_id": "O1",
        "ticker": "AKRBP.OL",
        "benchmark_ticker": "^OSEAX",
        "entry_market_date": "2026-09-08",
        "entry_price": 100.0,
        "status": "ACTIVE",
        "group": "MODERATE",
        "horizon_measurements": {},
    }]
    monkeypatch.setattr(loe, "load_observations", lambda: obs)
    monkeypatch.setattr(loe, "save_observations", lambda rows: None)
    monkeypatch.setattr(loe, "load_engine_state", lambda: {})
    monkeypatch.setattr(loe, "write_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(loe, "_audit", lambda *args, **kwargs: None)

    def loader(symbols, start_date):
        return {
            "AKRBP.OL": [{"date": "2026-09-08", "close": 100.0}],
            "^OSEAX": [{"date": "2026-09-08", "close": 1500.0}],
        }

    result = loe.evaluate_observations(loader, now=datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc))
    assert result["status"] == "COMPLETED"
    assert result["missing"] == 0
    assert obs[0]["source_health"]["status"] == "AWAITING_NEXT_TRADING_DAY"


def test_weekly_health_does_not_degrade_for_waiting_next_trading_day():
    rows = [{
        "ticker": "AKRBP.OL",
        "status": "ACTIVE",
        "group": "MODERATE",
        "benchmark_ticker": "^OSEAX",
        "source_health": {"status": "AWAITING_NEXT_TRADING_DAY"},
        "horizon_measurements": {},
        "decision_snapshot": {},
    }]
    analysis = loe.build_weekly_analysis(rows)
    assert analysis["health"]["status"] == "OK"
    assert analysis["health"]["missing_or_stale"] == 0


def test_market_intelligence_uses_exchange_helper_for_recommendation_table_source():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath("market_intelligence.py").read_text(encoding="utf-8")
    assert '_exchange_for_ticker(row.get("ticker"), row.get("exchange_name") or row.get("market_segment"))' in source
    assert 'render_report_file_center(\n                st, latest' in source
