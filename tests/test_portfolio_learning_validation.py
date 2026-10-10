from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from io import BytesIO
import pytest
from pypdf import PdfReader
import super_portfolio as sp
import learning_observation_engine as learning
from portfolio_evidence import rank_text, stop_alert_text, retention_explanation
from learning_experiments import checksum, combinations, chronological_split, run_search, replay_super_portfolio, compact_candidates, create_forward_plan, evaluate_forward_plan, record_frame, validate_frames

def test_entry_rank_and_score_are_immutable_and_legacy_stays_unknown():
    row = {"ticker": "HAFNI.OL", "rank": 8, "price": 100, "portfolio_score_adjusted": 70}
    pos = sp._position_from_row(row, 10, {}, "2026-01-01T12:00:00+00:00", sp.SuperPortfolioConfig(), [])
    row.update(rank=21, portfolio_score_adjusted=56, price=103)
    updated = sp._position_from_row(row, 10, pos, "2026-01-02T12:00:00+00:00", sp.SuperPortfolioConfig(), [])
    assert updated["entry_rank"] == 8 and updated["entry_portfolio_score"] == 70
    assert updated["best_rank_since_entry"] == 8
    assert rank_text(updated) == "#8 → #21 · svekket 13 plasser"
    legacy = sp._position_from_row(row, 10, {"entry_price": 90}, "2026-01-02T12:00:00+00:00", sp.SuperPortfolioConfig(), [])
    assert legacy["entry_rank"] is None and "ukjent" in rank_text(legacy)

def test_shipping_exposure_survives_broad_sector_and_legacy_position():
    radar = sp.stress_radar([{"ticker": "HAFNI.OL", "sector": "Industrials", "target_weight_pct": 12}])
    shipping = next(r for r in radar if r["key"] == "shipping_-30")
    assert shipping["exposure_pct"] == 12 and shipping["estimated_portfolio_impact_pct"] == -3.6
    assert next(r for r in radar if r["key"] == "energy_-20")["exposure_pct"] == 0

def test_multi_stock_notification_uses_current_price_denominator():
    rows = [{"ticker": "OET.OL", "entry_price": 860, "peak_price": 901, "current_price": 901,
             "stop_price": 882.55, "pnl_pct": 4.77, "protected_gain_pct": 2.62, "to": "PROFIT PROTECT"},
            {"ticker": "CMBTO.OL", "current_price": 198.6, "stop_price": 195.63}]
    message = stop_alert_text(rows)
    assert "\n\nCMBTO.OL:" in message and "2.05%" in message
    assert "pp margin" not in message and "Sikret gevinstgulv" not in message
    assert "ikke garantert salgskurs" in message

def test_learning_reports_absolute_excess_and_no_validation_claim():
    rows = [{"group": group, "decision_snapshot": {"program_version": "old"},
             "horizon_measurements": {"20": {"return_pct": -.4, "excess_return_pct": excess}}}
            for group, excess in (("MODERATE", 1.5), ("MATCHED_CONTROL", .7)) for _ in range(30)]
    result = learning.build_weekly_analysis(rows)
    assert result["selection_quality"]["status"] == "FORELØPIG POSITIV FORSKJELL"
    assert not result["selection_quality"]["independent_validation"]
    assert result["cohort"] == "old" and result["matured_count"] == 0
    strict = next(r for r in result["groups"] if r["group"] == "STRICT")
    assert strict["assessment_status"] == "KAN IKKE VURDERES"
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(learning.build_weekly_pdf(result))).pages)
    assert "Fullført 60 børsdager" in text and "ikke nødvendigvis positiv" in text

def frames(days=600):
    cfg = asdict(sp.SuperPortfolioConfig())
    result = []
    for day in range(days):
        at = (datetime(2025, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=day)).isoformat()
        f = {"engine": "SUPER_PORTFOLIO", "at": at, "config": cfg,
             "pipeline": {"run_id": str(day), "created_at": at, "candidates": [], "market_activation_levels": {"USA": "PRODUCTION", "Norge": "PRODUCTION"}}}
        f["sha256"] = checksum(f)
        result.append(f)
    return result

def test_split_is_chronological_and_purges_overlapping_periods():
    train, validation, holdout = chronological_split(frames())
    assert (datetime.fromisoformat(validation[0]["at"]) - datetime.fromisoformat(train[-1]["at"])).days >= 60
    assert (datetime.fromisoformat(holdout[0]["at"]) - datetime.fromisoformat(validation[-1]["at"])).days >= 60
    bad = frames(20)
    bad[0]["pipeline"]["candidates"] = [{"price_timestamp": bad[1]["at"]}]
    bad[0]["sha256"] = checksum({k:v for k,v in bad[0].items() if k != "sha256"})
    with pytest.raises(ValueError, match="Future"):
        chronological_split(bad, embargo_days=0)

def test_parameter_budget_is_bounded_without_enumerating_grid():
    rows = list(combinations({f"p{i}": range(10) for i in range(9)}, budget=999))
    assert len(rows) == 200 and len({checksum(r) for r in rows}) == 200

def test_holdout_never_selects_the_winner():
    calls = []
    data = frames()
    holdout_start = chronological_split(data)[2][0]["at"]
    def evaluate(part, params):
        calls.append((part[0]["at"], deepcopy(params)))
        score = params.get("minimum_score", 0)
        return {"net_return_pct": -score if part[0]["at"] == holdout_start else score, "maximum_drawdown_pct": 0}
    result = run_search(frames(), {"minimum_score": [60, 70, 80]}, evaluator=evaluate, finalists=1)
    assert result["finalists"][0]["parameters"]["minimum_score"] == 80
    assert result["finalists"][0]["holdout"]["net_return_pct"] == -80
    assert result["trial_count"] == 3 and not result["production_approval_available"]

def test_replay_never_reads_or_writes_production(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Production I/O in replay")
    for name in ("load_state", "save_state", "append_event", "get_or_build_super_portfolio_market_pipeline"):
        monkeypatch.setattr(sp, name, forbidden)
    result = replay_super_portfolio(frames(3), {})
    assert result["trade_count"] == 0 and not result["production_changed"]
    with pytest.raises(ValueError, match="safety cap"):
        replay_super_portfolio(frames(3), {"hard_stop_drawdown_pct": 8})

def test_pending_ordinary_sale_has_human_explanation():
    state = {"decision_trace": {"by_ticker": {"AKVA.OL": {"action": "SELL", "action_execution_status": "ADVISORY_ONLY"}}}}
    assert "venter på ordinær omvekting" in retention_explanation("AKVA.OL", state)


def test_replay_executes_buy_and_risk_sale_with_costs_without_production_io(monkeypatch):
    from tests.test_program_audit_candidate_fallback import candidate
    monkeypatch.setattr(sp, "market_activation_level", lambda _: "PRODUCTION")
    def forbidden(*args, **kwargs):
        raise AssertionError("Production I/O in trade replay")
    for name in ("load_state", "save_state", "append_event", "get_or_build_super_portfolio_market_pipeline"):
        monkeypatch.setattr(sp, name, forbidden)
    data = frames(6)
    for i, frame in enumerate(data):
        row = candidate("AAA")
        row["price"] = 105 if i < 3 else 95
        row["raw"]["last_price"] = row["price"]
        frame["config"].update(target_positions=1, production_market_scopes=["USA"])
        frame["pipeline"]["candidates"] = compact_candidates([row])
        frame["sha256"] = checksum({k: v for k, v in frame.items() if k != "sha256"})
    original = deepcopy(data)
    result = replay_super_portfolio(data, {})
    assert data == original
    assert result["trade_count"] == 2 and result["losing_exit_count"] == 1
    assert result["transaction_cost"] > 0 and result["net_return_pct"] < 0


def test_forward_plan_is_frozen_and_cannot_relabel_historical_data():
    search = {"status": "HISTORICAL_TEST_COMPLETED", "historical_end": "2024-12-30T12:00:00+00:00",
              "finalists": [{"parameters": {"minimum_score": 65}}]}
    plan = create_forward_plan(search, asdict(sp.SuperPortfolioConfig()), started_at="2024-12-31T12:00:00+00:00")
    result = evaluate_forward_plan(plan, frames(3), evaluator=lambda f, p: {"net_return_pct": 0})
    assert result["observed_dates"] == 3 and not result["production_approval_available"]
    changed = deepcopy(plan)
    changed["finalists"][0]["minimum_score"] = 50
    with pytest.raises(ValueError, match="modified"):
        evaluate_forward_plan(changed, frames(3))
    future_plan = deepcopy(plan)
    future_plan["started_at"] = frames(3)[-1]["at"]
    future_plan["sha256"] = checksum({k: v for k, v in future_plan.items() if k != "sha256"})
    with pytest.raises(ValueError, match="Historical"):
        evaluate_forward_plan(future_plan, frames(3))


def test_capture_uses_completion_time_not_scan_start_and_keeps_rejected_evidence(monkeypatch):
    import durable_runtime
    stored = []
    monkeypatch.setattr(durable_runtime, "read_json", lambda *a: [])
    def write(key, path, value):
        stored.extend(value)
        return True
    monkeypatch.setattr(durable_runtime, "write_json", write)
    quote = {"ticker": "AAA", "price": 100, "price_timestamp": "2026-10-10T12:04:00+00:00"}
    pipeline = {"run_id": "RUN", "created_at": "2026-10-10T12:00:00+00:00", "candidates": [quote]}
    rejected = {**quote, "ticker": "REJECTED", "official_market_events": [{"id": "KNOWN_EVENT"}]}
    result = record_frame(pipeline, config=asdict(sp.SuperPortfolioConfig()),
                          preselection=[rejected], deep_candidates=[rejected, quote],
                          captured_at="2026-10-10T12:05:00+00:00")
    assert result["status"] == "CAPTURED"
    validate_frames(stored)
    assert stored[0]["at"] > quote["price_timestamp"] > pipeline["created_at"]
    assert stored[0]["preselection"][0]["official_market_events"][0]["id"] == "KNOWN_EVENT"
    assert len(stored[0]["deep_candidates"]) == 2
