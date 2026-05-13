from factor_timeseries_intelligence import (
    build_factor_timeseries,
    rolling_factor_exposures,
    detect_regime_transitions,
    latent_beta_drift,
    temporal_stress_propagation,
    update_adaptive_factor_memory,
    build_factor_timeseries_intelligence,
)


def _obs():
    return [
        {"date": "2026-01-01", "symbol": "PORT", "factor_exposures": {"equity_beta": 72, "tech_ai": 50, "duration": 20, "credit_spread": 20, "usd_fx": 40, "liquidity": 18, "concentration": 25}},
        {"date": "2026-02-01", "symbol": "PORT", "factor_exposures": {"equity_beta": 70, "tech_ai": 48, "duration": 24, "credit_spread": 24, "usd_fx": 42, "liquidity": 22, "concentration": 28}},
        {"date": "2026-03-01", "symbol": "PORT", "factor_exposures": {"equity_beta": 35, "tech_ai": 25, "duration": 70, "credit_spread": 45, "usd_fx": 50, "liquidity": 45, "concentration": 35}},
        {"date": "2026-04-01", "symbol": "PORT", "factor_exposures": {"equity_beta": 28, "tech_ai": 20, "duration": 35, "credit_spread": 82, "usd_fx": 55, "liquidity": 72, "concentration": 44}},
    ]


def test_build_factor_timeseries_normalizes_points():
    result = build_factor_timeseries(_obs())
    assert result["schema_version"] == 1
    assert result["observation_count"] == 4
    assert "equity_beta" in result["points"][0]["factor_vector"]


def test_rolling_exposures_preserve_length():
    rolling = rolling_factor_exposures(_obs(), window=2)
    assert len(rolling) == 4
    assert rolling[-1]["window"] == 2
    assert rolling[-1]["rolling_exposure"]["credit_spread"] > 50


def test_regime_transitions_detect_change():
    transitions = detect_regime_transitions(_obs(), window=1)
    assert len(transitions) >= 1
    assert any(t["to_regime"] in {"rate_shock", "credit_stress", "risk_off"} for t in transitions)


def test_latent_beta_drift_flags_large_factor_moves():
    drift = latent_beta_drift(_obs(), baseline_window=1, current_window=1)
    assert drift["drift_score"] > 10
    assert "credit_spread" in drift["alerts"] or "equity_beta" in drift["alerts"]


def test_temporal_stress_propagation_has_path():
    stress = temporal_stress_propagation(_obs(), horizon_steps=3)
    assert len(stress["path"]) == 3
    assert stress["cumulative_impact_pct"] < 0


def test_online_memory_updates_and_keeps_regime():
    memory = None
    for row in _obs():
        memory = update_adaptive_factor_memory(memory, row)
    assert memory["observation_count"] == 4
    assert memory["current_regime"] in {"risk_on", "risk_off", "rate_shock", "credit_stress", "balanced"}
    assert "equity_beta" in memory["factor_memory"]


def test_full_factor_timeseries_intelligence_end_to_end():
    result = build_factor_timeseries_intelligence(_obs(), {"rolling_window": 2, "stress_horizon_steps": 2})
    assert result["summary"]["observation_count"] == 4
    assert result["adaptive_memory"]["observation_count"] == 4
    assert result["temporal_stress"]["path"][-1]["step"] == 2
