from __future__ import annotations

from datetime import datetime, timedelta, timezone

import learning_observation_engine as engine


def _series(start: datetime, base: float, growth: float, count: int = 70):
    rows = [{"date": "2025-12-31", "close": base}]
    day = start.date()
    index = 0
    while index < count:
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "close": base + growth * index})
            index += 1
        day += timedelta(days=1)
    return rows


def test_report_control_snapshot_is_read_only_and_auditable(monkeypatch):
    monkeypatch.setattr(engine, "load_observations", lambda: [])
    monkeypatch.setattr(engine, "load_engine_state", lambda: {"daily": {"status": "COMPLETED"}})
    monkeypatch.setattr(engine, "read_json", lambda key, path, default: default)
    result = engine.report_control_snapshot({"created": 7}, now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert result["engine_status"] == "AKTIV"
    assert result["pending_registration"] == 7
    assert result["production_parameters_changed"] is False
    assert result["trade_authorized"] is False
    assert len(result["control_sha256"]) == 64


def test_historical_baseline_compares_stock_with_market_without_mutation():
    run = {
        "run_id": "MI-BASE-1", "created_at": "2026-01-02T08:00:00+00:00",
        "candidates": [{"ticker": "AAA", "market": "USA", "sector": "Tech", "investment_score": 78,
                        "autonomy_outcome_code": "KJØPSKANDIDAT", "raw": {"current_price": 100.0}}],
        "report_summary": {"production_buy_threshold": 73},
    }
    stock = _series(datetime(2026, 1, 3, tzinfo=timezone.utc), 100, 1)
    benchmark = _series(datetime(2026, 1, 3, tzinfo=timezone.utc), 200, .2)
    result = engine.build_historical_baseline([run], series_loader=lambda symbols, start: {"AAA": stock, "^GSPC": benchmark})
    assert result["signal_count"] == 1
    assert result["verified_count"] == 1
    twenty = next(row for row in result["analysis"]["horizons"] if row["horizon_days"] == 20)
    assert twenty["excess_return"]["count"] == 1
    assert result["production_parameters_changed"] is False
    assert result["trade_authorized"] is False
    assert len(result["baseline_sha256"]) == 64


def test_report_contract_requires_result_learning_control():
    source = open("report_contracts.py", encoding="utf-8").read()
    pdf_source = open("market_intelligence.py", encoding="utf-8").read()
    assert '"result_learning_control"' in source
    assert "Resultat- og læringskontroll" in pdf_source
    assert "Ferdige 1/5/20/60" in pdf_source


def test_reentry_status_explains_ranking_without_trade():
    from trading_engine import paper_reentry_status
    portfolio = {"trades": [{"type": "SELL", "ticker": "FRO.OL", "time": "2026-09-02T09:02:00",
                              "price": 411.5, "reason": "SELL signal"}]}
    result = paper_reentry_status("FRO.OL", 416.2, portfolio=portfolio,
                                  rules={"sell_signal_cooldown_days": 5}, now=datetime(2026, 9, 3, 9, 0))
    assert result["status"] == "GJENKJØPSKARANTENE"
    assert result["blocked"] is True
    assert result["trade_attempted"] is False
    assert result["last_sell_at"].startswith("2026-09-02")
