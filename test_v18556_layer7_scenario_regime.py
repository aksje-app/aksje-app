from fund_etf_analyzer import analyze_fund_record, build_scenario_regime_profile, run_fund_etf_lab


def _prices(start=100.0, step=0.2, n=90):
    return [round(start + i * step, 2) for i in range(n)]


def test_long_duration_bond_is_helped_by_rate_cuts_and_hurt_by_rate_hikes():
    row = {
        "fund_type": "Rente-/obligasjonsfond",
        "duration": 9.5,
        "risk_score": 65,
        "volatility_pct": 8,
        "max_drawdown_pct": -7,
        "holdings_profile": {"holdings_available": False},
        "insider_holdings_profile": {"direction": "Nøytral"},
    }
    prof = build_scenario_regime_profile(row)
    assert prof["model"] == "Scenario & Regime Engine"
    assert prof["scenarios"]["rentefall"]["score"] > prof["scenarios"]["renteokning"]["score"]
    assert prof["worst_scenario"]["label"] in {"Renteøkning", "Kredittstress", "Tech/AI-selloff", "Inflasjon", "Resesjon"}


def test_high_yield_is_penalized_in_credit_stress_but_helped_in_risk_on():
    row = {
        "fund_type": "High yield-fond",
        "risk_score": 55,
        "volatility_pct": 13,
        "max_drawdown_pct": -14,
        "holdings_profile": {"holdings_available": False},
        "insider_holdings_profile": {"direction": "Nøytral"},
    }
    prof = build_scenario_regime_profile(row)
    assert prof["scenarios"]["kredittstress"]["score"] < 40
    assert prof["scenarios"]["risk_on"]["score"] > prof["scenarios"]["kredittstress"]["score"]


def test_analyze_fund_record_attaches_layer7_profile():
    data = {
        "name": "iShares 20+ Year Treasury Bond ETF",
        "fund_type": "Rente-/obligasjonsfond",
        "prices": _prices(100, 0.03),
        "expense_ratio": 0.15,
        "duration": 16.8,
        "holdings": [],
    }
    row = analyze_fund_record("TLT", data, fund_type="Rente-/obligasjonsfond")
    assert "scenario_regime_profile" in row
    assert row["scenario_score"] is not None
    assert "mest" in row["scenario_summary"].lower()


def test_run_lab_ranks_and_exposes_scenario_layer():
    def provider(symbol):
        base = {
            "TLT": {"fund_type": "Rente-/obligasjonsfond", "duration": 16.0, "prices": _prices(100, 0.02), "expense_ratio": 0.15},
            "SHY": {"fund_type": "Rente-/obligasjonsfond", "duration": 1.8, "prices": _prices(100, 0.01), "expense_ratio": 0.15},
        }
        return base[symbol]

    result = run_fund_etf_lab(["TLT", "SHY"], data_provider=provider, fund_type="Rente-/obligasjonsfond", max_funds=1)
    assert result["version"] == "v18.5.73"
    assert len(result["ranked"]) == 2
    assert all("scenario_regime_profile" in r for r in result["ranked"])
    assert all(r.get("scenario_score") is not None for r in result["ranked"])
