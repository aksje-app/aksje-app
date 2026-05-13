from pathlib import Path

from app_version import get_app_version
from fund_etf_analyzer import (
    build_portfolio_intelligence_foundation_profile,
    build_portfolio_overlap_matrix,
    build_regime_memory_profile,
)


def _row(symbol, fit=70, scenario=65, worst=55, holdings=None, confidence=75):
    return {
        "symbol": symbol,
        "portfolio_fit_score": fit,
        "confidence_score": confidence,
        "scenario_score": scenario,
        "scenario_regime_profile": {
            "best_scenario": {"label": "Rentefall", "score": scenario + 5},
            "worst_scenario": {"label": "Kredittstress", "score": worst},
        },
        "holdings_profile": {"top_holdings": holdings or []},
        "portfolio_fit_profile": {"overlap_pct": 5 if symbol == "A" else 18},
    }


def test_v18561_version():
    assert get_app_version() == "v18.5.71"


def test_overlap_matrix_uses_holdings_pairs():
    rows = [
        _row("A", holdings=[{"symbol": "MSFT"}, {"symbol": "NVDA"}]),
        _row("B", holdings=[{"symbol": "MSFT"}, {"symbol": "AAPL"}]),
        _row("C", holdings=[{"symbol": "TSLA"}]),
    ]
    matrix = build_portfolio_overlap_matrix(rows)
    assert matrix["model"] == "Portfolio Overlap Matrix"
    assert matrix["fund_count"] == 3
    assert matrix["highest_overlaps"][0]["a"] == "A"
    assert matrix["highest_overlaps"][0]["b"] == "B"
    assert matrix["highest_overlaps"][0]["overlap_pct"] > 0


def test_regime_memory_stores_baseline(tmp_path, monkeypatch):
    import fund_etf_analyzer as fea
    monkeypatch.setattr(fea, "REGIME_MEMORY_DIR", tmp_path)
    rows = [_row("A", worst=40), _row("B", worst=60)]
    profile = build_regime_memory_profile(rows, selection_info={"fund_type": "ETF"})
    assert profile["model"] == "Regime Memory"
    assert profile["previous_available"] is False
    assert "baseline" in profile["changes"][0]
    assert list(Path(tmp_path).glob("regime__*.json"))


def test_portfolio_intelligence_foundation_combines_three_components(tmp_path, monkeypatch):
    import fund_etf_analyzer as fea
    monkeypatch.setattr(fea, "PORTFOLIO_INTELLIGENCE_DIR", tmp_path / "portfolio")
    monkeypatch.setattr(fea, "REGIME_MEMORY_DIR", tmp_path / "regime")
    monkeypatch.setattr(fea, "OVERLAP_CACHE_DIR", tmp_path / "overlap")
    rows = [
        _row("A", holdings=[{"symbol": "MSFT"}, {"symbol": "NVDA"}]),
        _row("B", holdings=[{"symbol": "MSFT"}, {"symbol": "AAPL"}]),
    ]
    profile = build_portfolio_intelligence_foundation_profile(rows, selection_info={"fund_type": "ETF"})
    assert profile["module"] == "C"
    assert profile["components"] == ["Portfolio Overlap Cache", "Regime Memory", "Why this portfolio?"]
    assert profile["portfolio_intelligence_cache"]["enabled"] is True
    assert profile["regime_memory"]["model"] == "Regime Memory"
    assert profile["why_this_portfolio"]["model"] == "Why This Portfolio?"
