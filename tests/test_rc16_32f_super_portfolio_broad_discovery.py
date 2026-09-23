from datetime import datetime, timezone
import super_portfolio as sp


def test_super_portfolio_broad_discovery_scans_full_available_universe_before_shortlist(monkeypatch):
    seen = {"load_cfg": [], "coarse_rows": [], "prepare_rows": []}

    def fake_load(cfg, return_discovery=False):
        seen["load_cfg"].append((cfg.market_scope, cfg.scan_limit, cfg.full_universe_scan))
        rows = [
            {"ticker": f"{cfg.market_scope[:2].upper()}{i}", "market": cfg.market_scope, "sector": "Test"}
            for i in range(120)
        ]
        return (rows, f"source:{cfg.market_scope}")

    def fake_coarse(rows, market, limit, **kwargs):
        seen["coarse_rows"].append((market, len(rows), limit))
        return [dict(row, coarse_score=100.0 - idx) for idx, row in enumerate(rows[-limit:])]

    def fake_prepare(rows, cfg, progress_callback=None, force_refresh=False):
        seen["prepare_rows"].append((cfg.market_scope, len(rows)))
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

    def fake_score(row, cfg):
        return Assessment(row, cfg.market_scope)

    import investment_pipeline as ip
    import stocks
    monkeypatch.setattr(stocks, "get_us_broad_tickers", lambda limit: [])
    monkeypatch.setattr(ip, "_load_candidate_rows_from_app", fake_load)
    monkeypatch.setattr(ip, "_prepare_candidate_rows", fake_prepare)
    monkeypatch.setattr(ip, "score_candidate", fake_score)
    monkeypatch.setattr(sp, "_coarse_rank_market_rows", fake_coarse)
    monkeypatch.setattr(sp, "_bounded_insider_checks", lambda candidates, config: {})
    monkeypatch.setattr(sp, "write_json", lambda *args, **kwargs: None)

    cfg = sp.SuperPortfolioConfig(
        market_universe_limit_per_market=500,
        market_coarse_shortlist_per_market=80,
        market_deep_analysis_per_market=40,
        market_candidates_per_market=12,
    )
    payload = sp.build_super_portfolio_market_pipeline(
        cfg, now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc), force_refresh=True
    )

    assert all(scan_limit == 500 and full_scan for _, scan_limit, full_scan in seen["load_cfg"])
    assert all(loaded == 120 and shortlist_limit == 80 for _, loaded, shortlist_limit in seen["coarse_rows"])
    assert all(deep_count == 40 for _, deep_count in seen["prepare_rows"])
    assert all(item["universe_loaded"] == 120 for item in payload["summary"]["markets"])
    assert all(item["coarse_shortlisted"] == 80 for item in payload["summary"]["markets"])
    assert all(item["deep_analyzed"] == 40 for item in payload["summary"]["markets"])


def test_coarse_stage_does_not_default_to_first_rows_when_scores_favor_later_symbols(monkeypatch):
    rows = [
        {"ticker": f"T{i}", "market": "USA", "coarse_hint": float(i)}
        for i in range(100)
    ]

    monkeypatch.setattr(sp, "_coarse_market_snapshot", lambda tickers, market: {
        ticker: {"return_20d": float(int(ticker[1:])), "return_60d": 0.0, "avg_dollar_volume": 1_000_000.0, "volatility_pct": 20.0}
        for ticker in tickers
    })

    ranked = sp._coarse_rank_market_rows(rows, "USA", 10)
    tickers = [row["ticker"] for row in ranked]

    assert tickers[0] == "T99"
    assert "T0" not in tickers
    assert set(tickers) == {f"T{i}" for i in range(90, 100)}


def test_master_checklist_tracks_broad_universe_funnel():
    rows = {row["key"]: row for row in sp.master_checklist()}
    assert rows["broad_universe_first_pass"]["status"] == "DONE"
    assert rows["coarse_to_deep_funnel"]["status"] == "DONE"
