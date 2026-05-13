from validation_engine import (
    build_validation_profile,
    run_regime_replay,
    run_stress_replay,
    run_survivorship_and_data_checks,
    run_walk_forward_validation,
)


ROWS = [
    {"symbol": "SPY", "weight_pct": 35, "asset_type": "ETF", "sector": "Bred", "score": 82},
    {"symbol": "QQQ", "weight_pct": 25, "asset_type": "ETF", "sector": "Teknologi", "score": 86},
    {"symbol": "TLT", "weight_pct": 15, "asset_type": "Rente-/obligasjonsfond", "score": 68},
    {"symbol": "HYG", "weight_pct": 10, "asset_type": "High yield-fond", "score": 63},
    {"symbol": "SGOV", "weight_pct": 15, "asset_type": "Pengemarkedsfond", "score": 58},
]


SNAPSHOTS = [
    {"label": "t0", "rows": ROWS},
    {"label": "t1", "rows": [dict(r, score=(r.get("score", 60) + (2 if r["symbol"] == "SPY" else 0))) for r in ROWS]},
    {"label": "t2", "rows": [dict(r, weight_pct=r["weight_pct"]) for r in ROWS]},
]


def test_walk_forward_validation_reports_transitions():
    out = run_walk_forward_validation(SNAPSHOTS, constraints={"target_position_count": 4})
    assert out["snapshot_count"] == 3
    assert out["transition_count"] == 2
    assert out["pass_rate_pct"] >= 0
    assert out["latest_ranking"]


def test_stress_replay_contains_worst_scenario():
    out = run_stress_replay(ROWS)
    assert out["scenario_count"] >= 3
    assert out["worst_scenario"] is not None
    assert "scenarios" in out


def test_regime_replay_runs_multiple_regimes():
    out = run_regime_replay(ROWS, constraints={"target_position_count": 4, "max_position_pct": 40})
    assert out["regime_count"] >= 3
    assert all("top_candidates" in r for r in out["regimes"])


def test_data_quality_flags_duplicates_and_drops():
    snapshots = [
        {"label": "a", "rows": ROWS + [{"symbol": "SPY", "weight_pct": 1}]},
        {"label": "b", "rows": ROWS[:2]},
    ]
    out = run_survivorship_and_data_checks(snapshots)
    assert out["duplicate_rows"] >= 1
    assert out["drop_events"]
    assert out["status"] == "review"


def test_full_validation_profile_is_structured():
    out = build_validation_profile(ROWS, snapshots=SNAPSHOTS, constraints={"target_position_count": 4, "max_position_pct": 40})
    assert out["model"] == "Validation Engine"
    assert out["walk_forward"]["transition_count"] == 2
    assert out["stress_replay"]["scenario_count"] >= 3
    assert out["regime_replay"]["regime_count"] >= 3
    assert out["data_quality"]["snapshot_count"] == 3
