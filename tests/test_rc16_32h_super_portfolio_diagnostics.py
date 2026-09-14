import io
import json
import zipfile
from datetime import datetime, timezone

import super_portfolio as sp


def test_decision_trace_explains_position_missing_from_new_target():
    state = {
        "source_run_id": "OLD-RUN",
        "positions": {
            "VEI.OL": {"ticker": "VEI.OL", "target_weight_pct": 13.49, "rank": 1, "portfolio_score_adjusted": 79.6},
        },
    }
    pipeline = {
        "run_id": "NEW-RUN",
        "candidates": [
            {"ticker": "AAPL", "market": "USA", "price": 200, "investment_score": 90, "risk_score": 20, "data_quality": 90},
        ],
    }
    trace = sp.build_decision_trace(state=state, pipeline=pipeline, ranked=[{
        "ticker": "AAPL", "rank": 1, "portfolio_score_adjusted": 90.0, "risk_score": 20.0, "price": 200.0,
    }], target={"AAPL": 100.0}, advisory=[{
        "action": "SELL", "ticker": "VEI.OL", "from_pct": 13.49, "to_pct": 0.0,
    }])

    vei = trace["by_ticker"]["VEI.OL"]
    assert vei["current_position"] is True
    assert vei["in_current_pipeline"] is False
    assert vei["target_selected"] is False
    assert vei["action"] == "SELL"
    assert vei["exclusion_reason"] == "NOT_IN_CURRENT_PIPELINE"
    assert vei["position_source_run_id"] == "OLD-RUN"
    assert vei["decision_run_id"] == "NEW-RUN"
    assert vei["snapshot_mismatch"] is True
    assert "INCONSISTENT_DECISION" in vei["alerts"]


def test_diagnostic_zip_contains_readable_trace_and_raw_json():
    state = {
        "source_run_id": "NEW-RUN",
        "decision_trace": {
            "decision_run_id": "NEW-RUN",
            "created_at": "2026-09-14T02:36:02+00:00",
            "by_ticker": {
                "VEI.OL": {"ticker": "VEI.OL", "action": "SELL", "exclusion_reason": "NOT_IN_CURRENT_PIPELINE", "alerts": ["INCONSISTENT_DECISION"]}
            },
        },
    }
    payload = sp.build_diagnostic_zip(state, ticker="VEI.OL")
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names = set(archive.namelist())
        assert "README.txt" in names
        assert "decision_trace.json" in names
        assert "selected_ticker.json" in names
        text = archive.read("README.txt").decode("utf-8")
        assert "VEI.OL" in text
        assert "INCONSISTENT_DECISION" in text
        selected = json.loads(archive.read("selected_ticker.json"))
        assert selected["ticker"] == "VEI.OL"


def test_market_pipeline_emits_real_progress_events(monkeypatch):
    events = []

    def fake_load(cfg, return_discovery=False):
        return ([{"ticker": f"T{i}", "market": cfg.market_scope} for i in range(3)], "fake")

    def fake_coarse(rows, market, limit, **kwargs):
        return [dict(row, coarse_score=100-i) for i, row in enumerate(rows[:limit])]

    def fake_prepare(rows, cfg, progress_callback=None, force_refresh=False):
        return [dict(row, last_price=100.0, data_quality=90.0, risk_score=20.0) for row in rows]

    class Assessment:
        def __init__(self, row, market):
            self.ticker = row["ticker"]
            self.market = market
            self.sector = "Test"
            self.investment_score = 80.0
            self.risk_score = 20.0
            self.data_quality = 90.0
            self.raw = {"last_price": 100.0}

    import investment_pipeline as ip
    monkeypatch.setattr(ip, "_load_candidate_rows_from_app", fake_load)
    monkeypatch.setattr(ip, "_prepare_candidate_rows", fake_prepare)
    monkeypatch.setattr(ip, "score_candidate", lambda row, cfg: Assessment(row, cfg.market_scope))
    monkeypatch.setattr(sp, "_coarse_rank_market_rows", fake_coarse)
    monkeypatch.setattr(sp, "write_json", lambda *args, **kwargs: None)

    cfg = sp.SuperPortfolioConfig(market_scopes=("Norge", "USA"), market_universe_limit_per_market=10, market_coarse_shortlist_per_market=3, market_deep_analysis_per_market=2, market_candidates_per_market=1)
    sp.build_super_portfolio_market_pipeline(cfg, now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc), force_refresh=True, progress_callback=events.append)

    stages = [event["stage"] for event in events]
    assert stages[0] == "START"
    assert "UNIVERSE_LOADED" in stages
    assert "COARSE_COMPLETE" in stages
    assert "DEEP_COMPLETE" in stages
    assert stages[-1] == "COMPLETE"
    assert all(0 <= int(event["percent"]) <= 100 for event in events)


def test_ui_forces_refresh_and_exposes_diagnostic_zip():
    source = open("pages/super_portfolio.py", encoding="utf-8").read()
    assert "force_refresh=True" in source
    assert "get_or_build_super_portfolio_market_pipeline" in source
    assert "build_diagnostic_zip" in source
    assert "🔎 Diagnostiser valgt aksje" in source
    assert "📦 Last ned diagnose-ZIP" in source


def test_version_contract_is_rc16_32h():
    import app_version
    assert app_version.APP_VERSION == "v19.22.0-rc16.32h"
    assert app_version.PREVIOUS_APP_VERSION == "v19.22.0-rc16.32g"
    assert sp.VERSION == "v19.22.0-rc16.32h"
