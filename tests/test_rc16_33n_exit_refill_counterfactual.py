from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import controlled_parameter_learning as cpl
import signal_engine
import super_portfolio as sp


def _candidate(ticker: str, score: float, price: float = 100.0) -> dict:
    return {
        "ticker": ticker,
        "investment_score": score,
        "risk_score": 25,
        "data_quality_score": 95,
        "price": price,
        "market": "USA",
        "sector": "Technology",
        "raw": {
            "last_price": price,
            "volatility_pct": 20,
            "return_5d": 1.0,
            "return_20d": 3.0,
            "return_60d": 6.0,
        },
    }


def _position(ticker: str, *, entry: float, peak: float, last: float, weight: float, score: float) -> dict:
    return {
        "ticker": ticker,
        "market": "USA",
        "sector": "Technology",
        "target_weight_pct": weight,
        "entry_price": entry,
        "last_price": last,
        "peak_price": peak,
        "risk_score": 25,
        "quality_score": 95,
        "portfolio_score": score,
        "portfolio_score_adjusted": score,
        "max_portfolio_correlation": 0.2,
        "correlation_source": "MULTI_HORIZON_RETURN_PROFILE",
    }


def test_super_risk_exit_refills_only_with_allowed_entry(monkeypatch) -> None:
    now = datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(
        target_positions=3,
        max_position_pct=40,
        candidate_persistence_runs=1,
        replacement_rank_buffer=0,
        replacement_score_margin=0,
        production_market_scopes=("USA",),
    )
    state = sp.default_state(cfg)
    state["config"] = asdict(cfg)
    state["positions"] = {
        "EXIT": _position("EXIT", entry=100, peak=104, last=101, weight=40, score=99),
        "KEEP": _position("KEEP", entry=100, peak=101, last=100, weight=40, score=90),
    }
    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "market_activation_level", lambda value: "PRODUCTION")
    monkeypatch.setattr(
        sp,
        "build_rebalance_gate",
        lambda **kwargs: {
            "allowed": True,
            "confidence": {"score": 90, "label": "HIGH"},
            "reason_codes": [],
            "decision_run_id": "R1",
        },
    )

    result = sp.evaluate(
        pipeline={
            "run_id": "R1",
            "created_at": now.isoformat(timespec="seconds"),
            "candidates": [
                _candidate("EXIT", 99, 101),
                _candidate("KEEP", 90, 100),
                _candidate("NEW", 85, 105),
            ],
        },
        persist=False,
        now=now,
        rebalance_policy="ANALYZE_ONLY",
    )

    changes = result["changes"]
    assert any(row["action"] == "SELL" and row["ticker"] == "EXIT" for row in changes)
    refill = [row for row in changes if row.get("reason_code") == "RISK_EXIT_REFILL"]
    assert [row["ticker"] for row in refill] == ["NEW"]
    assert "NEW" in result["state"]["positions"]
    assert "EXIT" not in result["state"]["positions"]
    assert result["state"]["vacancy_diagnostics"]["refill_buys"] == ["NEW"]


def test_super_refill_fails_closed_when_rebalance_gate_is_blocked(monkeypatch) -> None:
    now = datetime(2026, 9, 28, 14, 30, tzinfo=timezone.utc)
    cfg = sp.SuperPortfolioConfig(
        target_positions=3,
        max_position_pct=40,
        candidate_persistence_runs=1,
        replacement_rank_buffer=0,
        replacement_score_margin=0,
        production_market_scopes=("USA",),
    )
    state = sp.default_state(cfg)
    state["config"] = asdict(cfg)
    state["positions"] = {
        "EXIT": _position("EXIT", entry=100, peak=104, last=101, weight=40, score=99),
        "KEEP": _position("KEEP", entry=100, peak=101, last=100, weight=40, score=90),
    }
    monkeypatch.setattr(sp, "load_state", lambda: state)
    monkeypatch.setattr(sp, "market_activation_level", lambda value: "PRODUCTION")
    monkeypatch.setattr(
        sp,
        "build_rebalance_gate",
        lambda **kwargs: {
            "allowed": False,
            "confidence": {"score": 40, "label": "VERY LOW"},
            "reason_codes": ["LOW_DECISION_CONFIDENCE"],
            "decision_run_id": "R2",
        },
    )

    result = sp.evaluate(
        pipeline={
            "run_id": "R2",
            "created_at": now.isoformat(timespec="seconds"),
            "candidates": [
                _candidate("EXIT", 99, 101),
                _candidate("KEEP", 90, 100),
                _candidate("NEW", 85, 105),
            ],
        },
        persist=False,
        now=now,
        rebalance_policy="ANALYZE_ONLY",
    )
    assert not any(row.get("reason_code") == "RISK_EXIT_REFILL" for row in result["changes"])
    assert "NEW" not in result["state"]["positions"]
    assert result["state"]["pending_risk_refill_slots"] == 1
    assert result["state"]["vacancy_diagnostics"]["status"] == "WAITING_FOR_QUALIFIED_CANDIDATE"


def _snapshot(signal: str = "BUY", confidence: int = 90, score: float = 9.0) -> dict:
    return {
        "schema": "paper_counterfactual_v1",
        "candidate_snapshot": {"ticker": "X", "entry_only": 1},
        "technical_context": {"rsi": 55},
        "original_decision": {"decision": signal, "confidence": confidence},
        "signal": signal,
        "confidence": confidence,
        "score": score,
        "portfolio_state": {"position_count": 1},
    }


def test_paper_counterfactual_marks_legacy_unavailable_and_replays_without_future_data(monkeypatch) -> None:
    seen = []

    def fake_decision(candidate, technical):
        seen.append((dict(candidate), dict(technical)))
        ticker = str(candidate.get("ticker") or "")
        if ticker == "KEEPWIN":
            return {"decision": "BUY", "confidence": 90, "decision_score": 9.0}
        return {"decision": "HOLD / WAIT", "confidence": 40, "decision_score": 4.0}

    monkeypatch.setattr(signal_engine, "build_trading_decision", fake_decision)
    monkeypatch.setattr(cpl, "load_paper_rules", lambda: {
        "min_buy_confidence": 70, "min_buy_score": 7.0, "max_open_positions": 5,
    })
    monkeypatch.setattr(cpl, "load_paper_portfolio", lambda: {
        "trades": [
            {"type": "BUY", "ticker": "LEGACY", "trade_id": "b0"},
            {"type": "SELL", "ticker": "LEGACY", "trade_id": "s0", "pnl_pct": 9.35, "pnl_amount": 599.5},
            {"type": "BUY", "ticker": "MISSWIN", "trade_id": "b1", "decision_snapshot": {
                **_snapshot(), "candidate_snapshot": {"ticker": "MISSWIN", "entry_only": 11}}},
            {"type": "SELL", "ticker": "MISSWIN", "trade_id": "s1", "pnl_pct": 5.0, "pnl_amount": 500.0},
            {"type": "BUY", "ticker": "AVOIDLOSS", "trade_id": "b2", "decision_snapshot": {
                **_snapshot(), "candidate_snapshot": {"ticker": "AVOIDLOSS", "entry_only": 22}}},
            {"type": "SELL", "ticker": "AVOIDLOSS", "trade_id": "s2", "pnl_pct": -4.0, "pnl_amount": -400.0},
            {"type": "BUY", "ticker": "KEEPWIN", "trade_id": "b3", "decision_snapshot": {
                **_snapshot(), "candidate_snapshot": {"ticker": "KEEPWIN", "entry_only": 33}}},
            {"type": "SELL", "ticker": "KEEPWIN", "trade_id": "s3", "pnl_pct": 3.0, "pnl_amount": 300.0},
        ]
    })

    result = cpl.paper_counterfactual_replay()
    rows = {row["ticker"]: row for row in result["rows"]}
    assert rows["LEGACY"]["classification"] == "UNTESTABLE_LEGACY"
    assert rows["MISSWIN"]["classification"] == "MISSED_WINNER"
    assert rows["AVOIDLOSS"]["classification"] == "AVOIDED_LOSER"
    assert rows["KEEPWIN"]["classification"] == "RETAINED_WINNER"
    assert result["missed_winners"] == 1
    assert result["avoided_losers"] == 1
    assert result["retained_winners"] == 1
    assert all("pnl_pct" not in candidate and "sell" not in candidate for candidate, _ in seen)
    assert {candidate["entry_only"] for candidate, _ in seen} == {11, 22, 33}


def test_release_wiring_and_diagnostics_are_visible() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    super_src = (root / "super_portfolio.py").read_text(encoding="utf-8")
    page_src = (root / "pages" / "super_portfolio.py").read_text(encoding="utf-8")
    learning = (root / "controlled_parameter_learning.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    assert "vacancy_diagnostics.json" in super_src
    assert "current_positions.json" in super_src
    assert "SUPER_PORTFOLIO_DECISION" in super_src
    assert "Ledige plasser / kontantandel" in page_src
    assert "Counterfactual / Replay" in learning
    assert "🔎 Super Portfolio diagnose" in app
    assert "📚 Rapporter" in app
