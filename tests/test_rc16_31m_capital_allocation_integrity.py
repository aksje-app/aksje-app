from __future__ import annotations

def _replay_candidates():
    """Self-contained golden rows; release archives must not depend on a sibling dump."""
    return [{
        "ticker": "HWM", "market": "USA", "autonomy_adjusted_investment_score": 75.83,
        "technical_signal_action": "HOLD",
        "analysis_ranking": {"matches": ["Growth"]},
        "evidence_coverage": {
            "news": {"status": "AVAILABLE"},
            "insider": {"status": "SOURCE_ERROR"},
        },
        "evidence_passport": {"areas": {
            "news": {"status": "AVAILABLE", "ranking_contribution": 0.0},
            "insider": {"status": "SOURCE_ERROR", "ranking_contribution": 3.0},
        }},
    }, {
        "ticker": "SSAB-A.ST", "market": "Sverige", "investment_score": 76.8,
        "technical_signal_action": "WAIT", "evidence_valid_for_decision": True,
    }]


def _replay_portfolio():
    return {
        "initial_cash": 100000.0, "cash": 90000.0,
        "positions": {
            "SSAB-A.ST": {
                "ticker": "SSAB-A.ST", "quantity": 100.0,
                "average_price": 100.0, "last_price": 100.0,
                "entry_score": 76.8, "market": "Sverige",
            },
        },
    }


def test_golden_replay_neutralises_unverified_positive_credit():
    from decision_inputs import candidate_entry_score, candidate_score_audit
    rows = {row["ticker"]: row for row in _replay_candidates()}
    hwm = rows["HWM"]
    audit = candidate_score_audit(hwm)
    assert audit["raw_adjusted_score"] == 75.83
    assert audit["unverified_positive_credit_removed"] > 0
    assert candidate_entry_score(hwm) < 73.0


def test_strategy_relevant_policy_does_not_make_insider_failure_mandatory():
    from evidence_relevance import evidence_decision_assessment
    rows = {row["ticker"]: row for row in _replay_candidates()}
    result = evidence_decision_assessment(rows["HWM"])
    assert result["valid_for_decision"] is True
    assert result["missing_required_areas"] == []
    assert "insider" in result["neutralised_optional_areas"]


def test_balanced_shortlist_guarantees_ten_per_available_market():
    from market_intelligence import _balanced_global_shortlist
    rows = [
        {"ticker": f"US{i}", "market": "USA", "investment_score": 100-i} for i in range(50)
    ] + [
        {"ticker": f"NO{i}", "market": "Norge", "investment_score": 50-i} for i in range(15)
    ] + [
        {"ticker": f"SE{i}", "market": "Sverige", "investment_score": 40-i} for i in range(15)
    ]
    selected = _balanced_global_shortlist(rows, 60, ["Norge", "Sverige", "USA"])
    assert len(selected) == 60
    for market in ("Norge", "Sverige", "USA"):
        assert sum(row["market"] == market for row in selected) >= 10


def test_balanced_shortlist_retains_each_available_sector():
    from market_intelligence import _balanced_global_shortlist
    rows = [{"ticker": f"US{i}", "market": "USA", "sector": "Technology", "investment_score": 100-i} for i in range(70)]
    rows += [{"ticker": "NOENERGY", "market": "Norge", "sector": "Energy", "investment_score": 20}]
    rows += [{"ticker": "SEHEALTH", "market": "Sverige", "sector": "Healthcare", "investment_score": 19}]
    selected = _balanced_global_shortlist(rows, 60, ["Norge", "Sverige", "USA"])
    assert {"Technology", "Energy", "Healthcare"} <= {row["sector"] for row in selected}


def test_replay_existing_positions_are_explicitly_labelled():
    from report_portfolio_intelligence import build_portfolio_report
    portfolio = _replay_portfolio()
    report = build_portfolio_report(portfolio, _replay_candidates())
    assert report["open_positions"] == len(portfolio["positions"])
    assert all(row["portfolio_label"] == "ALLEREDE I PORTEFØLJEN" for row in report["positions"])
    assert all(row["addition_policy"] == "TILLEGGSKJØP DEAKTIVERT" for row in report["positions"])
    assert any(row["ticker"] == "SSAB-A.ST" for row in report["positions"])


def test_golden_replay_system_watch_detects_uniform_technical_hold():
    from report_portfolio_intelligence import build_system_anomaly_watch
    alerts = build_system_anomaly_watch(_replay_candidates())
    assert any(row["code"] == "TECHNICAL_SIGNAL_UNIFORM" for row in alerts)


def test_sec_ticker_registry_is_reused_across_tickers():
    import sec_form4_source as sec
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"0": {"ticker": "AAA", "cik_str": 1, "title": "A"}, "1": {"ticker": "BBB", "cik_str": 2, "title": "B"}}
    class Session:
        def __init__(self): self.calls = 0
        def get(self, *args, **kwargs): self.calls += 1; return Response()
    session = Session()
    sec._TICKER_CACHE = {}; sec._TICKER_CACHE_FETCHED_AT = 0.0
    assert sec._ticker_cik("AAA", session)[0] == "0000000001"
    assert sec._ticker_cik("BBB", session)[0] == "0000000002"
    assert session.calls == 1


def test_version_is_rc16_31m():
    from app_version import APP_VERSION
    assert APP_VERSION == "v19.22.0-rc16.31s"
