from datetime import datetime
from contextlib import contextmanager
from zoneinfo import ZoneInfo


OSLO = ZoneInfo("Europe/Oslo")


def test_release_version_is_scheduled_quality_reports():
    from app_version import APP_VERSION, APP_VERSION_NAME

    assert APP_VERSION == "v19.22.0-rc16.32x"
    assert "Mobile Market Quality View" in APP_VERSION_NAME


def test_quality_schedule_runs_before_each_required_report_only_on_weekdays():
    from quality_valuation_schedule import scheduled_slot

    assert scheduled_slot(datetime(2026, 9, 25, 7, 30, tzinfo=OSLO)).endswith("T08:00@Europe/Oslo")
    assert scheduled_slot(datetime(2026, 9, 25, 13, 30, tzinfo=OSLO)).endswith("T14:00@Europe/Oslo")
    assert scheduled_slot(datetime(2026, 9, 25, 21, 30, tzinfo=OSLO)).endswith("T22:00@Europe/Oslo")
    assert scheduled_slot(datetime(2026, 9, 25, 7, 50, tzinfo=OSLO)) == ""
    assert scheduled_slot(datetime(2026, 9, 26, 7, 30, tzinfo=OSLO)) == ""


def test_scheduled_selection_prioritizes_holdings_then_ranked_candidates(monkeypatch):
    import quality_valuation_schedule as schedule

    monkeypatch.setattr("quality_valuation._safe_ticker", lambda value: str(value or "").upper())
    latest = {
        "portfolio_intelligence": {"positions": [{"ticker": "OWN.OL"}]},
        "candidates": [
            {"ticker": "LOW.OL", "investment_score": 60},
            {"ticker": "HIGH.OL", "investment_score": 88},
        ],
    }
    assert schedule.select_symbols(latest, limit=3) == ["OWN.OL", "HIGH.OL", "LOW.OL"]


def test_partial_quality_snapshot_is_visible_in_fixed_reports(monkeypatch):
    import quality_valuation_store as store

    monkeypatch.setattr(store, "load_latest", lambda: {
        "state": "PARTIAL", "run_mode": "SCHEDULED_SHADOW",
        "generated_at": "2026-09-25T19:30:00+00:00", "selected": 15, "completed": 14,
        "failures": [{"ticker": "MISS.OL", "error": "RuntimeError"}],
        "report_url": "https://example.test/?public_report_token=abc",
        "groups": {
            "Attraktivt priset kandidat": [{
                "ticker": "GOOD.OL", "name": "Good", "roce_pct": 18.2,
                "reported_pe": 9.1, "normalized_pe": 11.4,
                "entry_range_scenario": [90, 100], "financial_date": "2025-12-31",
                "industry": "Industrials", "country": "Norway", "warnings": [],
            }],
            "Kvalitetsselskap": [], "Dyr kvalitet / følges": [],
        },
    })
    summary = store.recent_report_summary(max_age_hours=24 * 365)
    assert summary["shadow_observation"] is True
    assert summary["run_mode"] == "SCHEDULED_SHADOW"
    assert summary["status"] == "PARTIAL"
    assert summary["failure_count"] == 1
    assert summary["top"][0]["roce_pct"] == 18.2
    assert summary["top"][0]["normalized_pe"] == 11.4


def test_missing_quality_snapshot_still_has_visible_fixed_report_status(monkeypatch):
    import quality_valuation_store as store

    monkeypatch.setattr(store, "load_latest", lambda: {})
    summary = store.recent_report_summary()
    assert summary["shadow_observation"] is True
    assert summary["status"] == "MANGLER"
    assert summary["top"] == []
    assert "Ingen fersk" in summary["reason"]


def test_scheduled_screen_is_idempotent_for_completed_slot(monkeypatch):
    import quality_valuation_schedule as schedule
    import quality_valuation_store

    monkeypatch.setattr(schedule, "scheduled_slot", lambda now=None: "2026-09-25T22:00@Europe/Oslo")
    monkeypatch.setattr(quality_valuation_store, "load_latest", lambda: {
        "scheduled_slot": "2026-09-25T22:00@Europe/Oslo",
        "run_key": "quality_valuation/runs/one", "report_url": "https://example.test/report",
    })
    result = schedule.run_due_scheduled_screen()
    assert result == {
        "state": "ALREADY_COMPLETED", "scheduled_slot": "2026-09-25T22:00@Europe/Oslo",
        "run_key": "quality_valuation/runs/one", "report_url": "https://example.test/report",
    }


def test_due_scheduled_screen_persists_partial_result_and_pdf(monkeypatch):
    import quality_valuation as engine
    import quality_valuation_alerts
    import quality_valuation_control
    import quality_valuation_data
    import quality_valuation_schedule as schedule
    import quality_valuation_store
    import quality_valuation_ui

    @contextmanager
    def acquired_screen():
        yield True

    result = {
        "state": "PARTIAL", "generated_at": "2026-09-25T19:30:00+00:00",
        "selected": 2, "completed": 1, "elapsed_seconds": 1.0,
        "failures": [{"ticker": "MISS.OL", "error": "provider"}],
        "groups": {"Attraktivt priset kandidat": [{"ticker": "GOOD.OL", "market_drivers": []}]},
    }
    persisted: list[dict] = []
    monkeypatch.setattr(schedule, "scheduled_slot", lambda now=None: "2026-09-25T22:00@Europe/Oslo")
    monkeypatch.setattr(schedule, "_latest_market_run", lambda: {"run_id": "source-1"})
    monkeypatch.setattr(schedule, "select_symbols", lambda latest: ["GOOD.OL", "MISS.OL"])
    monkeypatch.setattr(schedule, "_publish_pdf", lambda value: value.update({"report_url": "https://example.test/qv.pdf"}) or value["report_url"])
    monkeypatch.setattr(quality_valuation_store, "load_latest", lambda: {})
    monkeypatch.setattr(quality_valuation_store, "persist_screen", lambda value: persisted.append(dict(value)) or "quality_valuation/runs/one")
    monkeypatch.setattr(quality_valuation_control, "single_manual_screen", acquired_screen)
    monkeypatch.setattr(quality_valuation_ui, "required_report_busy", lambda: False)
    monkeypatch.setattr(quality_valuation_data, "memory_budget_ok", lambda: True)
    monkeypatch.setattr(engine, "run_screen", lambda *args, **kwargs: dict(result))
    monkeypatch.setattr(quality_valuation_alerts, "transition_messages", lambda previous, current: [])

    summary = schedule.run_due_scheduled_screen()
    assert summary["state"] == "PARTIAL"
    assert summary["completed"] == 1
    assert summary["failures"] == 1
    assert summary["report_url"] == "https://example.test/qv.pdf"
    assert persisted[0]["run_mode"] == "SCHEDULED_SHADOW"
    assert persisted[0]["source_report_id"] == "source-1"


def test_scheduler_executes_quality_before_required_reports():
    source = open("scheduled_runner.py", encoding="utf-8").read()
    assert source.index('state["database_preflight"] = _database_preflight()') < source.index("run_due_scheduled_screen")
    assert source.index('release_process_memory("scheduled_runner:before_quality_valuation")') < source.index("run_due_scheduled_screen")
    assert source.index("run_due_scheduled_screen") < source.index("run_scheduler_cycle")
    assert '"quality_valuation"' in source


def test_fixed_pdf_contract_contains_ranked_quality_metrics():
    source = open("market_intelligence.py", encoding="utf-8").read()
    assert "Kvalitet, ROCE og prising" in source
    assert '"ROCE", "P/E", "Norm. P/E", "Inngangsscenario"' in source
    assert "qv.get('status')" in source
    assert "Datastatus:" in source


def test_fixed_pdf_renders_quality_ranking_and_metrics():
    from io import BytesIO

    from pypdf import PdfReader
    import market_intelligence as market

    run = {
        "run_id": "MI-QV-TEST", "created_at": "2026-09-25T20:00:00+00:00",
        "job_name": "Obligatorisk kveldsrapport", "markets": ["Norge"],
        "summary": {}, "candidates": [], "portfolio_decisions": {},
        "quality_valuation_observation": {
            "shadow_observation": True, "run_mode": "SCHEDULED_SHADOW",
            "generated_at": "2026-09-25T19:30:00+00:00", "status": "PARTIAL",
            "selected": 15, "completed": 14,
            "top": [{
                "ticker": "GOOD.OL", "name": "Good Industri", "group": "Attraktivt priset kandidat",
                "roce_pct": 18.2, "reported_pe": 9.1, "normalized_pe": 11.4,
                "entry_range_scenario": [90, 100],
            }],
        },
    }
    pdf = market.build_pdf(run)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "Kvalitet, ROCE og prising" in text
    assert "GOOD.OL" in text
    assert "Attraktivt priset kandidat" in text
    assert "18,2 %" in text
    assert "11,4" in text
