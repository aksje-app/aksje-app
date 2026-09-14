from super_portfolio import (
    SuperPortfolioConfig,
    apply_concentration_penalties,
    ranking_velocity,
    portfolio_health,
    stop_pressure,
    ai_would_do_today,
)


def _r(ticker, score, sector="Industrials", correlations=None):
    return {
        "ticker": ticker,
        "portfolio_score": score,
        "risk_score": 30.0,
        "sector": sector,
        "raw_candidate": {"portfolio_correlations": correlations or {}},
    }


def test_sector_and_correlation_penalties_are_soft_and_ranked():
    cfg = SuperPortfolioConfig(concentration_soft_pct=30.0)
    rows = [
        _r("SHIP1", 92, "Shipping"),
        _r("SHIP2", 91, "Shipping", {"SHIP1": 0.92}),
        _r("HEALTH", 89, "Healthcare", {"SHIP1": 0.10}),
    ]
    out = apply_concentration_penalties(rows, cfg)
    by = {row["ticker"]: row for row in out}
    assert by["SHIP1"]["sector_penalty"] == 0
    assert by["SHIP2"]["sector_penalty"] > 0
    assert by["SHIP2"]["correlation_penalty"] > by["HEALTH"]["correlation_penalty"]
    assert by["SHIP2"]["portfolio_score_adjusted"] < by["SHIP2"]["portfolio_score"]
    assert sorted(out, key=lambda x: -x["portfolio_score_adjusted"]) == out


def test_ranking_velocity_uses_previous_snapshots_and_arrow():
    history = [
        {"ranking": [{"ticker": "AAA", "rank": 24}, {"ticker": "BBB", "rank": 3}]},
        {"ranking": [{"ticker": "AAA", "rank": 17}, {"ticker": "BBB", "rank": 4}]},
    ]
    out = ranking_velocity("AAA", current_rank=8, history=history)
    assert out["rank_change"] == 16
    assert out["rank_velocity"] > 0
    assert out["rank_arrow"] in {"↑↑", "↑↑↑"}
    falling = ranking_velocity("BBB", current_rank=12, history=history)
    assert falling["rank_change"] < 0
    assert "↓" in falling["rank_arrow"]


def test_portfolio_health_rewards_quality_and_diversification():
    diverse = [
        {"portfolio_score_adjusted": 90, "risk_score": 25, "sector": "Tech", "stop_status": "SAFE"},
        {"portfolio_score_adjusted": 88, "risk_score": 30, "sector": "Health", "stop_status": "SAFE"},
        {"portfolio_score_adjusted": 86, "risk_score": 35, "sector": "Industrial", "stop_status": "WATCH"},
    ]
    concentrated = [dict(p, sector="Shipping") for p in diverse]
    good = portfolio_health(diverse)
    bad = portfolio_health(concentrated)
    assert 0 <= good["score"] <= 100
    assert good["score"] > bad["score"]
    assert good["icon"] in {"🟢", "🟡", "🟠", "🔴"}


def test_stop_pressure_detects_move_toward_stop():
    cfg = SuperPortfolioConfig(hard_stop_drawdown_pct=15)
    pos = {"ticker": "AAA", "distance_to_hard_stop_pct": 3.0, "drawdown_from_peak_pct": -12.0}
    history = [
        {"positions": [{"ticker": "AAA", "distance_to_hard_stop_pct": 8.0}]},
        {"positions": [{"ticker": "AAA", "distance_to_hard_stop_pct": 5.5}]},
    ]
    out = stop_pressure(pos, history, cfg)
    assert out["pressure"] in {"HIGH", "CRITICAL"}
    assert "↓" in out["direction_arrow"]
    assert out["distance_change_pct"] < 0


def test_ai_would_do_today_is_advisory_and_does_not_mutate_positions():
    positions = {
        "AAA": {"ticker": "AAA", "target_weight_pct": 12.0},
        "OLD": {"ticker": "OLD", "target_weight_pct": 8.0},
    }
    weights = {"AAA": 10.0, "NEW": 10.0}
    original = {k: dict(v) for k, v in positions.items()}
    actions = ai_would_do_today(positions, weights, min_rebalance_pp=1.0)
    assert positions == original
    lookup = {(a["action"], a["ticker"]) for a in actions}
    assert ("REDUCE", "AAA") in lookup
    assert ("SELL", "OLD") in lookup
    assert ("BUY", "NEW") in lookup
    assert all(a["advisory_only"] is True for a in actions)


def test_evaluate_exposes_health_velocity_pressure_and_advisory_actions(monkeypatch):
    import super_portfolio as sp

    state = sp.default_state(sp.SuperPortfolioConfig(target_positions=2, challenger_count=1))
    state["positions"] = {
        "OLD": {"ticker": "OLD", "target_weight_pct": 50.0, "entry_price": 100, "last_price": 100, "peak_price": 100}
    }
    state["history"] = [
        {
            "positions": [{"ticker": "AAA", "distance_to_hard_stop_pct": 10.0}],
            "ranking": [{"ticker": "AAA", "rank": 6}, {"ticker": "BBB", "rank": 2}],
        }
    ]
    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "save_state", lambda value: value)
    monkeypatch.setattr(sp, "append_event", lambda *args, **kwargs: None)
    pipeline = {
        "run_id": "RUN-32B",
        "candidates": [
            {"ticker":"AAA","investment_score":95,"risk_score":25,"data_quality_score":95,"price":110,"sector":"Tech","market":"USA"},
            {"ticker":"BBB","investment_score":90,"risk_score":35,"data_quality_score":90,"price":100,"sector":"Health","market":"USA"},
            {"ticker":"CCC","investment_score":85,"risk_score":40,"data_quality_score":90,"price":100,"sector":"Shipping","market":"Norge"},
        ],
    }
    result = sp.evaluate(pipeline=pipeline, persist=False)
    assert result["portfolio_health"]["score"] > 0
    assert result["ai_would_do_today"]
    assert result["state"]["portfolio_health"]["score"] == result["portfolio_health"]["score"]
    assert result["state"]["ai_would_do_today"] == result["ai_would_do_today"]
    assert result["snapshot"]["ranking"][0]["rank"] == 1
    aaa = result["state"]["positions"]["AAA"]
    assert "portfolio_score_adjusted" in aaa
    assert "rank_velocity" in aaa and "rank_arrow" in aaa
    assert "stop_pressure" in aaa and "stop_direction_arrow" in aaa
