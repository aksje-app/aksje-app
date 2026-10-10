"""Bounded, offline experiments. No production writes or trade authority.

Replay invokes the Super Portfolio evaluator, not a second trading policy.
Historical frames must be point-in-time exports. Missing history is never
filled with today's news, classifications, prices or configuration.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import random
from typing import Any, Mapping, Sequence

MAX_FRAMES_BYTES = 8 * 1024 * 1024
MAX_FRAMES = 240
MAX_TRIALS = 200
MAX_FINALISTS = 5
EXPERIMENT_PARAMETERS = {
    "minimum_score", "maximum_risk", "candidate_persistence_runs", "max_position_pct",
    "hard_stop_drawdown_pct", "profit_protect_trigger_pct", "profit_retention_2_3_pct",
    "profit_retention_3_5_pct", "profit_retention_5_8_pct", "profit_retention_8_plus_pct",
    "concentration_soft_pct", "sector_penalty_per_existing", "correlation_soft_limit",
    "correlation_penalty_scale", "risk_exit_cooldown_days", "risk_reentry_confirmation_runs",
    "manual_exit_cooldown_days", "replacement_rank_buffer", "replacement_score_margin",
}
FRAME_KEY = "controlled_learning/experiment_frames.json"
FIELDS = ("ticker", "symbol", "market", "country", "currency", "sector", "industry", "price", "current_price",
          "autonomy_adjusted_investment_score", "last_price", "investment_score", "final_score", "score", "quality_score", "data_quality_score", "risk_score",
          "volatility_pct", "data_freshness", "data_coverage", "event_risk", "price_timestamp", "data_timestamp",
          "return_1d", "return_3d", "return_5d", "return_10d", "return_20d", "return_60d", "return_1m", "return_3m",
          "official_events", "official_market_events", "decision_readiness", "confidence_score", "validation_score", "portfolio_fit_score")

def checksum(value) -> str:
    if hasattr(value, "dataset_identity"):
        value = {"ordered_frame_checksums": value.dataset_identity}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def compact_candidates(rows):
    result = []
    for row in rows[:1000]:
        value = {key: deepcopy(row[key]) for key in FIELDS if key in row}
        raw = row.get("raw") or {}
        value["raw"] = {key: deepcopy(raw[key]) for key in FIELDS if key in raw}
        result.append(value)
    return result

def record_frame(pipeline, *, config, preselection=None, deep_candidates=None, captured_at=None):
    """Small ring of exports, not a claim of a complete historical universe."""
    from durable_runtime import read_json, write_json
    from storage_architecture import runtime_data_path
    path = runtime_data_path("controlled_learning", "experiment_frames.json")
    from market_universe import MARKET_ACTIVATION_LEVELS
    # A scan may take minutes: quotes collected after its start are available
    # only at capture completion, never at the pipeline's earlier start time.
    frame = {"engine": "SUPER_PORTFOLIO", "at": captured_at or datetime.now(timezone.utc).isoformat(),
             "run_id": pipeline.get("run_id"), "config": dict(config),
             "pipeline": {k: deepcopy(pipeline[k]) for k in ("run_id", "created_at", "summary", "confidence", "regime") if k in pipeline},
             "preselection": compact_candidates(preselection or []),
             "capture_scope": "COARSE_SHORTLIST_AND_DEEP_CANDIDATES", "complete_universe": False, "preselection_total": len(preselection or []),
             "deep_total": len(deep_candidates or []),
             "deep_candidates": compact_candidates(deep_candidates or [])}
    frame["pipeline"]["candidates"] = compact_candidates(list(pipeline.get("candidates") or []))
    frame["pipeline"]["market_activation_levels"] = dict(MARKET_ACTIVATION_LEVELS)
    frame["sha256"] = checksum(frame)
    if len(json.dumps(frame, default=str).encode()) > MAX_FRAMES_BYTES // 2:
        return {"status": "FRAME_TOO_LARGE", "production_changed": False}
    stored = read_json(FRAME_KEY, path, [])
    frames = [f for f in stored if f.get("run_id") != frame["run_id"]] if isinstance(stored, list) else []
    frames.append(frame)
    frames = frames[-MAX_FRAMES:]
    while len(json.dumps(frames, default=str).encode()) > MAX_FRAMES_BYTES:
        frames.pop(0)
    if not write_json(FRAME_KEY, path, frames):
        return {"status": "CAPTURE_FAILED", "production_changed": False}
    return {"status": "CAPTURED", "frames": len(frames), "sha256": frame["sha256"], "production_changed": False}

def validate_frames(frames):
    if not frames:
        raise ValueError("No historical frames")
    previous = None
    for f in frames:
        body = {k: v for k, v in f.items() if k != "sha256"}
        if checksum(body) != f.get("sha256"):
            raise ValueError("Frame checksum mismatch")
        at = datetime.fromisoformat(str(f.get("at")).replace("Z", "+00:00"))
        if at.tzinfo is None or (previous and at <= previous):
            raise ValueError("Frames need strictly increasing timezone-aware timestamps")
        if f.get("engine") not in {"SUPER_PORTFOLIO", "AUTONOMY"} or not f.get("config"):
            raise ValueError("Frozen engine/config missing")
        from learning_runtime import validate
        validate(f)
        if f.get("engine") == "SUPER_PORTFOLIO" and not isinstance((f.get("pipeline") or {}).get("market_activation_levels"), dict):
            raise ValueError("Frozen market activation policy missing")
        for row in (f.get("pipeline") or {}).get("candidates") or []:
            stamp = row.get("price_timestamp") or row.get("data_timestamp")
            if stamp:
                observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if observed.tzinfo is None or observed > at:
                    raise ValueError("Future or undated quote in frame")
        previous = at

def chronological_split(frames, *, embargo_days=90):
    """Split by date, not row; embargo accommodates overlapping outcome windows."""
    validate_frames(frames)
    dates = sorted({str(f["at"])[:10] for f in frames})
    if len(dates) < 15:
        raise ValueError("At least 15 distinct dates required before splitting")
    a, b = dates[int(len(dates) * .6)], dates[int(len(dates) * .8)]
    gap = timedelta(days=max(0, int(embargo_days)))
    if hasattr(frames, "select_period"):
        train = frames.select_period(end=a)
        validation = frames.select_period(begin=(datetime.fromisoformat(a) + gap).date().isoformat(), end=b)
        holdout = frames.select_period(begin=(datetime.fromisoformat(b) + gap).date().isoformat())
        if min(map(len, (train, validation, holdout))) < 3:
            raise ValueError("Insufficient periods after embargo; keep collecting/exporting data")
        return train, validation, holdout
    train = [f for f in frames if str(f["at"])[:10] < a]
    validation = [f for f in frames if datetime.fromisoformat(str(f["at"])[:10]) >= datetime.fromisoformat(a) + gap and str(f["at"])[:10] < b]
    holdout = [f for f in frames if datetime.fromisoformat(str(f["at"])[:10]) >= datetime.fromisoformat(b) + gap]
    if min(map(len, (train, validation, holdout))) < 3:
        raise ValueError("Insufficient periods after embargo; keep collecting/exporting data")
    return train, validation, holdout

def combinations(space, *, budget=100, seed=7):
    """Bounded random coverage; no materialization of a gigantic Cartesian grid."""
    keys = sorted(space)
    values = [list(space[k]) for k in keys]
    if not keys or any(not v for v in values):
        raise ValueError("Empty parameter space")
    size = 1
    for v in values:
        size *= len(v)
    budget = min(MAX_TRIALS, max(1, int(budget)), size)
    indices = random.Random(seed).sample(range(size), budget)
    for index in indices:
        row = {}
        for key, options in reversed(list(zip(keys, values))):
            row[key] = options[index % len(options)]
            index //= len(options)
        yield row

def replay_super_portfolio(frames, parameters):
    """Same decisions, gates, risk exits, cash and NAV costs as production.

    Frozen marks approximate fills, not executable historical bid/ask quotes.
    That limitation prevents automatic promotion from these results.
    """
    from dataclasses import asdict
    from super_portfolio import SuperPortfolioConfig, default_state, evaluate
    validate_frames(frames)
    allowed = set(SuperPortfolioConfig.__dataclass_fields__)
    if set(parameters) - EXPERIMENT_PARAMETERS:
        raise ValueError("Unsupported experiment parameter")
    from math import isfinite
    if any(not isfinite(float(v)) or float(v) < 0 for v in parameters.values()):
        raise ValueError("Invalid experiment parameter")
    # Safety contracts remain invariant, even inside the optimizer.
    if float(parameters.get("hard_stop_drawdown_pct", 3)) > 3 or float(parameters.get("max_position_pct", 15)) > 15:
        raise ValueError("Parameter exceeds engine safety cap")
    if float(parameters.get("hard_stop_drawdown_pct", 3)) <= 0 or float(parameters.get("max_position_pct", 15)) <= 0:
        raise ValueError("Parameter disables engine safety cap")
    state = default_state()
    curve, sales, trades, costs, cash = [], [], 0, 0., []
    for frame in frames:
        state["config"] = {**frame["config"], **parameters, "auto_pushover": False}
        cfg = SuperPortfolioConfig(**{k: v for k, v in state["config"].items() if k in allowed})
        if cfg.hard_stop_drawdown_pct > 3 or cfg.max_position_pct > 15:
            raise ValueError("Frozen configuration exceeds engine safety cap")
        if not curve:
            state["initial_cash"] = cfg.start_cash
            state["portfolio_value"] = cfg.start_cash
        at = datetime.fromisoformat(frame["at"].replace("Z", "+00:00"))
        result = evaluate(pipeline=deepcopy(frame["pipeline"]), simulation_state=state,
                          persist=False, now=at, rebalance_policy="AUTO")
        state = result["state"]
        curve.append(float(state["portfolio_value"]))
        changes = result.get("changes") or []
        trades += len(changes)
        sales.extend(float(c["pnl_pct"]) for c in changes if c.get("action") == "SELL" and c.get("pnl_pct") is not None)
        costs += float(state.get("last_portfolio_transaction_cost") or 0)
        cash.append(float((state.get("vacancy_diagnostics") or {}).get("cash_pct", 100)))
    peak, drawdown = state["initial_cash"], 0.
    for value in curve:
        peak = max(peak, value)
        drawdown = max(drawdown, 100 * (peak - value) / peak)
    return {"net_return_pct": 100 * (curve[-1] / state["initial_cash"] - 1),
            "maximum_drawdown_pct": drawdown, "transaction_cost": costs,
            "trade_count": trades, "mean_cash_pct": sum(cash) / len(cash),
            "measured_exit_count": len(sales), "losing_exit_count": sum(x < 0 for x in sales),
            "production_changed": False, "fill_model": "FROZEN_MARKS",
            "promotion_eligible": False}

def run_search(frames, space, *, budget=100, finalists=3, embargo_days=90, evaluator=None):
    """Train search → validation shortlist → untouched holdout comparison.

    Holdout is never used to choose which finalist to report or apply.
    No statistical/causal claim is made from maximizing many trials.
    """
    if len({f["engine"] for f in frames}) != 1:
        raise ValueError("Separate engine datasets required")
    train, validation, holdout = chronological_split(frames, embargo_days=embargo_days)
    from learning_runtime import replay_autonomy
    evaluate = evaluator or (replay_autonomy if frames[0]["engine"] == "AUTONOMY" else replay_super_portfolio)
    manifest = {"dataset_sha256": checksum(frames), "space": space, "budget": min(budget, MAX_TRIALS),
                "historical_end": frames[-1]["at"],
                "embargo_days": embargo_days, "objective": "net_return_minus_maximum_drawdown",
                "production_changed": False, "status": "HISTORICAL_TEST_COMPLETED"}
    reference = {name: evaluate(part, {}) for name, part in (("train", train), ("validation", validation), ("holdout", holdout))}
    trials = []
    for parameters in combinations(space, budget=budget):
        metrics = evaluate(train, parameters)
        trials.append({"parameters": parameters, "train": metrics,
                       "objective": metrics["net_return_pct"] - metrics["maximum_drawdown_pct"]})
    shortlist = sorted(trials, key=lambda r: r["objective"], reverse=True)[:min(10, len(trials))]
    for trial in shortlist:
        trial["validation"] = evaluate(validation, trial["parameters"])
    frozen = sorted(shortlist, key=lambda r: r["validation"]["net_return_pct"] - r["validation"]["maximum_drawdown_pct"], reverse=True)[:max(1, min(finalists, MAX_FINALISTS))]
    for trial in frozen:
        trial["holdout"] = evaluate(holdout, trial["parameters"])
        trial["status"] = "REQUIRES_FORWARD_SHADOW_VALIDATION"
    return {**manifest, "reference": reference, "trials": trials, "finalists": frozen,
            "trial_count": len(trials), "statistical_validation": False,
            "production_approval_available": False,
            "limitations": ["Multiple trials can produce chance winners", "Frozen mark fills, not guaranteed executions",
                            "FX, dividends and intrabar paths need separately verified inputs",
                            "Capture covers shortlist, not every rejected universe member"]}

def create_forward_plan(search, reference_config, *, started_at):
    """Freeze finalists and reference before any forward observations exist."""
    at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(search["historical_end"].replace("Z", "+00:00"))
    if at.tzinfo is None or at <= end or search.get("status") != "HISTORICAL_TEST_COMPLETED":
        raise ValueError("Forward test must start after historical test")
    plan = {"status": "ACTIVE_SHADOW", "started_at": started_at,
            "search_sha256": checksum(search), "reference_config": deepcopy(reference_config),
            "finalists": [deepcopy(r["parameters"]) for r in search["finalists"]],
            "production_changed": False}
    plan["sha256"] = checksum(plan)
    return plan

def evaluate_forward_plan(plan, frames, *, evaluator=None):
    """Independent offline job; paired paths use the same future frames and costs."""
    if checksum({k: v for k, v in plan.items() if k != "sha256"}) != plan.get("sha256"):
        raise ValueError("Forward plan modified after activation")
    validate_frames(frames)
    start = datetime.fromisoformat(plan["started_at"].replace("Z", "+00:00"))
    if any(datetime.fromisoformat(f["at"].replace("Z", "+00:00")) <= start for f in frames):
        raise ValueError("Historical data cannot be called forward data")
    paired = deepcopy(frames)
    for frame in paired:
        frame["config"] = deepcopy(plan["reference_config"])
        frame["sha256"] = checksum({k: v for k, v in frame.items() if k != "sha256"})
    from learning_runtime import replay_autonomy
    evaluate = evaluator or (replay_autonomy if frames[0]["engine"] == "AUTONOMY" else replay_super_portfolio)
    baseline = evaluate(paired, {})
    return {"status": "ACTIVE_SHADOW", "plan_sha256": plan["sha256"],
            "dataset_sha256": checksum(frames), "first_at": frames[0]["at"], "last_at": frames[-1]["at"],
            "observed_dates": len({f["at"][:10] for f in frames}), "reference": baseline,
            "finalists": [{"parameters": p, "metrics": evaluate(paired, p)} for p in plan["finalists"]],
            "validated": False, "production_changed": False, "production_approval_available": False}

def forward_shadow_status(history, finalist_parameters, reference_parameters):
    """Register comparable paired forward results without enabling production."""
    pairs = [r for r in history if r.get("finalist_parameters") == finalist_parameters
             and r.get("reference_parameters") == reference_parameters and r.get("period_id")]
    unique = {r["period_id"]: r for r in pairs}
    return {"status": "ACTIVE_SHADOW" if unique else "PROPOSED_SHADOW",
            "completed_periods": len(unique), "production_changed": False,
            "validated": False, "approval_required": True}
