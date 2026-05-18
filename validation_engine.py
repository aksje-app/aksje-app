"""
validation_engine.py

Layer 3 after Core Risk Engine and Portfolio Intelligence Engine.

This module merges backtesting, stress replay and regime replay into one
compact validation layer. It is deterministic and dependency-light so it can
run in tests, Streamlit, API routes or batch jobs without network access.

The goal is not to pretend we have perfect historical market data. Instead it
validates whether the ranking/optimizer logic is stable, explainable and robust
across supplied historical snapshots or synthetic regime/stress replays.
"""

from __future__ import annotations
from utils import _safe_float, _now_iso  # v18.6.3 centralized helpers

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import math

from app_version import get_app_version
from core_risk_engine import STRESS_SCENARIOS, build_core_risk_profile, run_stress_tests
from portfolio_intelligence_engine import (
    REGIME_PRESETS,
    PortfolioConstraints,
    build_portfolio_intelligence_profile,
)


VALIDATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ValidationConfig:
    regimes: Tuple[str, ...] = ("balanced", "risk_off", "rate_shock", "credit_stress", "risk_on")
    max_rank_drift: int = 3
    max_turnover_pct: float = 35.0
    min_pass_rate_pct: float = 60.0
    replay_stress_scenarios: Tuple[str, ...] = tuple(STRESS_SCENARIOS.keys())

    def as_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["regimes"] = list(self.regimes)
        out["replay_stress_scenarios"] = list(self.replay_stress_scenarios)
        return out






def _config(value: Optional[Mapping[str, Any] | ValidationConfig]) -> ValidationConfig:
    if isinstance(value, ValidationConfig):
        return value
    data = dict(value or {})
    regimes = tuple(data.get("regimes") or ("balanced", "risk_off", "rate_shock", "credit_stress", "risk_on"))
    scenarios = tuple(data.get("replay_stress_scenarios") or tuple(STRESS_SCENARIOS.keys()))
    return ValidationConfig(
        regimes=regimes,
        max_rank_drift=int(_safe_float(data.get("max_rank_drift"), 3.0)),
        max_turnover_pct=_safe_float(data.get("max_turnover_pct"), 35.0),
        min_pass_rate_pct=_safe_float(data.get("min_pass_rate_pct"), 60.0),
        replay_stress_scenarios=scenarios,
    )


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or row.get("name") or "").upper().replace(" ", "")


def _ranking(profile: Mapping[str, Any]) -> List[str]:
    return [str(x.get("symbol") or "").upper() for x in profile.get("ranked_candidates") or [] if x.get("symbol")]


def _target_weights(profile: Mapping[str, Any]) -> Dict[str, float]:
    return {
        str(x.get("symbol") or "").upper(): _safe_float(x.get("target_weight_pct"), 0.0)
        for x in ((profile.get("optimizer") or {}).get("target_weights") or [])
        if x.get("symbol")
    }


def _rank_map(symbols: Sequence[str]) -> Dict[str, int]:
    return {s: i + 1 for i, s in enumerate(symbols)}


def _rank_drift(prev: Sequence[str], current: Sequence[str]) -> Dict[str, Any]:
    p = _rank_map(prev)
    c = _rank_map(current)
    common = sorted(set(p).intersection(c))
    changes = []
    for sym in common:
        drift = c[sym] - p[sym]
        if drift:
            changes.append({"symbol": sym, "previous_rank": p[sym], "current_rank": c[sym], "rank_drift": drift})
    changes.sort(key=lambda x: abs(int(x["rank_drift"])), reverse=True)
    avg = sum(abs(int(x["rank_drift"])) for x in changes) / len(common) if common else 0.0
    top5_overlap = len(set(prev[:5]).intersection(current[:5]))
    return {
        "common_count": len(common),
        "average_abs_rank_drift": round(avg, 2),
        "top5_overlap_count": top5_overlap,
        "largest_changes": changes[:10],
    }


def _turnover(prev_weights: Mapping[str, float], current_weights: Mapping[str, float]) -> float:
    symbols = set(prev_weights).union(current_weights)
    return round(sum(abs(_safe_float(current_weights.get(s), 0.0) - _safe_float(prev_weights.get(s), 0.0)) for s in symbols) / 2.0, 2)


def _snapshot_rows(snapshot: Any) -> Tuple[str, List[Mapping[str, Any]]]:
    if isinstance(snapshot, Mapping):
        label = str(snapshot.get("date") or snapshot.get("as_of") or snapshot.get("label") or f"snapshot_{id(snapshot)}")
        rows = list(snapshot.get("rows") or snapshot.get("holdings") or snapshot.get("portfolio") or [])
        return label, rows
    return f"snapshot_{id(snapshot)}", list(snapshot or [])


def run_walk_forward_validation(
    snapshots: Sequence[Any],
    *,
    regime: str = "balanced",
    constraints: Optional[Mapping[str, Any] | PortfolioConstraints] = None,
    config: Optional[Mapping[str, Any] | ValidationConfig] = None,
) -> Dict[str, Any]:
    cfg = _config(config)
    profiles: List[Dict[str, Any]] = []
    for snap in snapshots or []:
        label, rows = _snapshot_rows(snap)
        profile = build_portfolio_intelligence_profile(rows, regime=regime, constraints=constraints, selection_info={"validation_snapshot": label})
        profiles.append({"label": label, "profile": profile, "ranking": _ranking(profile), "weights": _target_weights(profile)})

    transitions: List[Dict[str, Any]] = []
    for prev, curr in zip(profiles, profiles[1:]):
        drift = _rank_drift(prev["ranking"], curr["ranking"])
        turnover = _turnover(prev["weights"], curr["weights"])
        passed = drift["average_abs_rank_drift"] <= cfg.max_rank_drift and turnover <= cfg.max_turnover_pct
        transitions.append({
            "from": prev["label"],
            "to": curr["label"],
            "rank_stability": drift,
            "target_turnover_pct": turnover,
            "status": "pass" if passed else "review",
        })

    pass_rate = round(100.0 * sum(1 for t in transitions if t["status"] == "pass") / len(transitions), 2) if transitions else 100.0
    return {
        "model": "Walk-Forward Validation",
        "snapshot_count": len(profiles),
        "transition_count": len(transitions),
        "pass_rate_pct": pass_rate,
        "status": "pass" if pass_rate >= cfg.min_pass_rate_pct else "review",
        "transitions": transitions,
        "latest_ranking": profiles[-1]["ranking"] if profiles else [],
        "summary": "Tester om ranking og target weights holder seg stabile fra snapshot til snapshot.",
    }


def run_stress_replay(rows: Sequence[Mapping[str, Any]], *, config: Optional[Mapping[str, Any] | ValidationConfig] = None) -> Dict[str, Any]:
    cfg = _config(config)
    selected = {k: v for k, v in STRESS_SCENARIOS.items() if k in set(cfg.replay_stress_scenarios)}
    stress = run_stress_tests(rows, scenarios=selected)
    scenarios = list(stress.get("scenarios") or [])
    failures = [s for s in scenarios if _safe_float(s.get("estimated_impact_pct"), 0.0) <= -10.0]
    return {
        "model": "Stress Replay Validation",
        "scenario_count": len(scenarios),
        "worst_scenario": stress.get("worst_scenario"),
        "failure_count": len(failures),
        "status": "review" if failures else "pass",
        "scenarios": scenarios,
        "summary": "Replayer Core Risk stress-scenarier og flagger porteføljer med tosifret estimert drawdown.",
    }


def run_regime_replay(
    rows: Sequence[Mapping[str, Any]],
    *,
    constraints: Optional[Mapping[str, Any] | PortfolioConstraints] = None,
    config: Optional[Mapping[str, Any] | ValidationConfig] = None,
) -> Dict[str, Any]:
    cfg = _config(config)
    baseline = build_portfolio_intelligence_profile(rows, regime="balanced", constraints=constraints, selection_info={"validation": "regime_replay_baseline"})
    base_ranking = _ranking(baseline)
    base_weights = _target_weights(baseline)
    regimes: List[Dict[str, Any]] = []
    for regime in cfg.regimes:
        if regime not in REGIME_PRESETS:
            continue
        profile = build_portfolio_intelligence_profile(rows, regime=regime, constraints=constraints, selection_info={"validation": "regime_replay", "regime": regime})
        drift = _rank_drift(base_ranking, _ranking(profile))
        turnover = _turnover(base_weights, _target_weights(profile))
        optimizer = profile.get("optimizer") or {}
        status = "pass" if drift["average_abs_rank_drift"] <= cfg.max_rank_drift and optimizer.get("constraint_status") == "ok" else "review"
        regimes.append({
            "regime": regime,
            "label": (profile.get("regime_config") or {}).get("label") or regime,
            "average_abs_rank_drift_vs_balanced": drift["average_abs_rank_drift"],
            "turnover_vs_balanced_pct": turnover,
            "constraint_status": optimizer.get("constraint_status"),
            "top_candidates": _ranking(profile)[:5],
            "status": status,
        })
    pass_rate = round(100.0 * sum(1 for r in regimes if r["status"] == "pass") / len(regimes), 2) if regimes else 100.0
    return {
        "model": "Regime Replay Validation",
        "regime_count": len(regimes),
        "pass_rate_pct": pass_rate,
        "status": "pass" if pass_rate >= cfg.min_pass_rate_pct else "review",
        "regimes": regimes,
        "summary": "Tester om optimizer/ranking er robust når adaptive regimevekter endres.",
    }


def run_survivorship_and_data_checks(snapshots: Sequence[Any]) -> Dict[str, Any]:
    symbol_sets: List[Tuple[str, set[str]]] = []
    missing_symbol_rows = 0
    duplicate_rows = 0
    for snap in snapshots or []:
        label, rows = _snapshot_rows(snap)
        symbols: List[str] = []
        for row in rows:
            sym = _symbol(row)
            if not sym:
                missing_symbol_rows += 1
            else:
                symbols.append(sym)
        duplicate_rows += max(0, len(symbols) - len(set(symbols)))
        symbol_sets.append((label, set(symbols)))
    dropped = []
    for (prev_label, prev_symbols), (curr_label, curr_symbols) in zip(symbol_sets, symbol_sets[1:]):
        lost = sorted(prev_symbols - curr_symbols)
        if lost:
            dropped.append({"from": prev_label, "to": curr_label, "dropped_symbols": lost[:20], "dropped_count": len(lost)})
    status = "review" if missing_symbol_rows or duplicate_rows or any(x["dropped_count"] >= 3 for x in dropped) else "pass"
    return {
        "model": "Survivorship/Data Quality Checks",
        "snapshot_count": len(symbol_sets),
        "missing_symbol_rows": missing_symbol_rows,
        "duplicate_rows": duplicate_rows,
        "drop_events": dropped,
        "status": status,
        "summary": "Fanger enkle datakvalitets- og survivorship-problemer før backtestresultater tolkes for hardt.",
    }


def build_validation_profile(
    rows: Sequence[Mapping[str, Any]],
    *,
    snapshots: Optional[Sequence[Any]] = None,
    regime: str = "balanced",
    constraints: Optional[Mapping[str, Any] | PortfolioConstraints] = None,
    config: Optional[Mapping[str, Any] | ValidationConfig] = None,
) -> Dict[str, Any]:
    cfg = _config(config)
    effective_snapshots = list(snapshots or [{"label": "current", "rows": list(rows or [])}])
    core = build_core_risk_profile(rows)
    walk = run_walk_forward_validation(effective_snapshots, regime=regime, constraints=constraints, config=cfg)
    stress = run_stress_replay(rows, config=cfg)
    regimes = run_regime_replay(rows, constraints=constraints, config=cfg)
    data_quality = run_survivorship_and_data_checks(effective_snapshots)

    sections = [walk, stress, regimes, data_quality]
    review_sections = [s.get("model") for s in sections if s.get("status") != "pass"]
    status = "pass" if not review_sections else "review"
    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "model": "Validation Engine",
        "status": status,
        "config": cfg.as_dict(),
        "core_risk_engine": core,
        "core_risk_score": core.get("core_risk_score"),
        "walk_forward": walk,
        "stress_replay": stress,
        "regime_replay": regimes,
        "data_quality": data_quality,
        "review_sections": review_sections,
        "summary": "Samler walk-forward, stress replay, regime replay, ranking stability, turnover og datakvalitet i ett valideringslag.",
    }


__all__ = [
    "VALIDATION_SCHEMA_VERSION",
    "ValidationConfig",
    "run_walk_forward_validation",
    "run_stress_replay",
    "run_regime_replay",
    "run_survivorship_and_data_checks",
    "build_validation_profile",
]
