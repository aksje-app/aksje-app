from datetime import datetime, timezone
import os
import super_portfolio as sp


def test_super_portfolio_market_scope_is_independent_of_production_norway_only(monkeypatch):
    monkeypatch.setenv("PRODUCTION_NORWAY_ONLY", "true")
    cfg = sp.SuperPortfolioConfig()
    assert tuple(cfg.market_scopes) == ("Norge", "Sverige", "Danmark", "Finland", "USA")


def test_build_market_pipeline_collects_candidates_from_all_configured_markets(monkeypatch):
    calls = []

    def fake_load(cfg, return_discovery=False):
        calls.append(cfg.market_scope)
        row = {"ticker": f"{cfg.market_scope[:2].upper()}1", "market": cfg.market_scope, "sector": "Test"}
        return ([row], f"source:{cfg.market_scope}")

    def fake_prepare(rows, cfg, progress_callback=None, force_refresh=False):
        market = cfg.market_scope
        return [{**rows[0], "last_price": 100.0, "data_quality": 90.0, "risk_score": 20.0, "return_1d": 1.0}]

    class Assessment:
        def __init__(self, market):
            self.ticker = f"{market[:2].upper()}1"
            self.market = market
            self.sector = "Test"
            self.investment_score = 80.0
            self.risk_score = 20.0
            self.data_quality = 90.0
            self.rank = 1
            self.raw = {"last_price": 100.0, "return_1d": 1.0}

    def fake_score(row, cfg):
        return Assessment(cfg.market_scope)

    import investment_pipeline as ip
    monkeypatch.setattr(ip, "_load_candidate_rows_from_app", fake_load)
    monkeypatch.setattr(ip, "_prepare_candidate_rows", fake_prepare)
    monkeypatch.setattr(ip, "score_candidate", fake_score)
    monkeypatch.setattr(sp, "write_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(sp, "read_json", lambda *args, **kwargs: {})

    cfg = sp.SuperPortfolioConfig(market_scan_limit_per_market=3, market_candidates_per_market=2)
    payload = sp.build_super_portfolio_market_pipeline(cfg, now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc), force_refresh=True)

    assert calls == ["Norge", "Sverige", "Danmark", "Finland", "USA"]
    assert {row["market"] for row in payload["candidates"]} == {"Norge", "Sverige", "Danmark", "Finland", "USA"}
    assert payload["market_scope"] == "Norden + USA"


def test_scheduled_cycle_uses_independent_super_portfolio_market_pipeline(monkeypatch):
    state = sp.default_state()
    state["last_scheduled_source_run_id"] = "OLD"
    pipeline = {"run_id": "SPM-NEW", "market_scope": "Norden + USA", "candidates": []}
    used = []

    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "get_or_build_super_portfolio_market_pipeline", lambda **kwargs: pipeline)
    monkeypatch.setattr(sp, "evaluate", lambda **kwargs: used.append(kwargs.get("pipeline")) or {"state": {**state, "positions": {}}, "changes": [], "stop_alerts": [], "rebalance_due": False})
    monkeypatch.setattr(sp, "refresh_index_benchmark", lambda state=None: {})
    monkeypatch.setattr(sp, "resource_health", lambda: {"status": "OK"})
    monkeypatch.setattr(sp, "save_state", lambda value: state.update(value) or value)
    monkeypatch.setattr(sp, "append_event", lambda *a, **k: None)

    result = sp.run_scheduled_shadow_cycle()
    assert result["state"] == "COMPLETED"
    assert used and used[0]["market_scope"] == "Norden + USA"


def test_master_checklist_tracks_multimarket_independence():
    rows = {row["key"]: row for row in sp.master_checklist()}
    assert rows["independent_multimarket_universe"]["status"] == "DONE"
    assert rows["production_norway_isolation"]["status"] == "DONE"
