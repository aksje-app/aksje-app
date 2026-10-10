from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import super_portfolio as sp

ROOT = Path(__file__).resolve().parents[1]


def _candidate(ticker: str, score: float = 90.0, risk: float = 25.0) -> dict:
    return {
        "ticker": ticker,
        "portfolio_score": score,
        "portfolio_score_adjusted": score,
        "risk_score": risk,
        "market": "USA",
        "sector": "Technology",
    }


def _position(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "market": "USA",
        "sector": "Technology",
        "target_weight_pct": weight,
        "entry_price": 100.0,
        "last_price": 101.0,
        "peak_price": 102.0,
        "risk_score": 25.0,
        "portfolio_score": 90.0,
        "portfolio_score_adjusted": 90.0,
    }


def test_single_candidate_cannot_absorb_all_cash() -> None:
    cfg = sp.SuperPortfolioConfig(target_positions=10, max_position_pct=15.0)
    weights = sp.target_weights([_candidate("AAA")], cfg)
    assert weights == {"AAA": 15.0}
    assert sum(weights.values()) == 15.0


def test_two_candidates_leave_cash_instead_of_becoming_50_50() -> None:
    cfg = sp.SuperPortfolioConfig(target_positions=10, max_position_pct=15.0)
    weights = sp.target_weights([_candidate("AAA", 95), _candidate("BBB", 85)], cfg)
    assert weights["AAA"] <= 15.0
    assert weights["BBB"] <= 15.0
    assert sum(weights.values()) <= 30.0


def test_enough_candidates_can_fill_portfolio_without_breaking_cap() -> None:
    cfg = sp.SuperPortfolioConfig(target_positions=10, max_position_pct=15.0)
    rows = [_candidate(f"T{i}", 100 - i) for i in range(10)]
    weights = sp.target_weights(rows, cfg)
    assert max(weights.values()) <= 15.0
    assert abs(sum(weights.values()) - 100.0) < 0.1


def test_existing_oversized_positions_are_reduced_even_off_rebalance(monkeypatch) -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(
        target_positions=10,
        max_position_pct=15.0,
        production_market_scopes=("USA",),
    )
    state = sp.default_state(cfg)
    state["config"] = asdict(cfg)
    state["positions"] = {
        "AAA": _position("AAA", 50.0),
        "BBB": _position("BBB", 33.33),
    }
    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "market_activation_level", lambda value: "PRODUCTION")

    result = sp.evaluate(
        pipeline={"run_id": "CAP-TEST", "created_at": now.isoformat(), "candidates": []},
        persist=False,
        now=now,
        rebalance_policy="SCHEDULED",
    )

    positions = result["state"]["positions"]
    assert positions["AAA"]["target_weight_pct"] == 15.0
    assert positions["BBB"]["target_weight_pct"] == 15.0
    reductions = {
        row["ticker"]: row
        for row in result["changes"]
        if row.get("reason_code") == "HARD_POSITION_CAP"
    }
    assert reductions["AAA"]["from_pct"] == 50.0
    assert reductions["AAA"]["to_pct"] == 15.0
    assert reductions["BBB"]["from_pct"] == 33.33
    assert reductions["BBB"]["to_pct"] == 15.0
    assert result["state"]["vacancy_diagnostics"]["cash_pct"] == 70.0


def test_notifications_are_plain_language_first() -> None:
    learning = (ROOT / "controlled_parameter_learning.py").read_text(encoding="utf-8")
    autonomy = (ROOT / "autonomous_portfolio.py").read_text(encoding="utf-8")
    portfolio = (ROOT / "super_portfolio.py").read_text(encoding="utf-8")

    assert "RESULTAT: Paper-porteføljen" in learning
    assert "RISIKO: Drawdown" in learning
    assert "NESTE STEG:" in learning
    assert "HANDLING:" in learning
    assert "KONTROLL:" in autonomy
    assert "HVA SKJEDDE:" in autonomy
    assert "KONTANTER:" in autonomy
    assert "stop_alert_text(alerts)" in portfolio
    assert "SUPERPORTEFØLJE – STOPPKONTROLL" in (ROOT / "portfolio_evidence.py").read_text()
    assert "stoppsituasjonen er forbedret – ingen handling" in (ROOT / "portfolio_evidence.py").read_text()
