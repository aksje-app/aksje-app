"""
factor_timeseries_intelligence.py

v18.5.67 Factor Time-Series Intelligence

Adds the temporal layer missing from a static fund/portfolio risk stack:
- dynamic factor series
- regime transition detection
- rolling exposures
- latent beta drift
- temporal stress propagation
- online/adaptive factor memory

The module is deterministic and dependency-light. It accepts either explicit
factor return/exposure observations or simple asset return rows. No network
calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import math

from app_version import get_app_version
from core_risk_engine import CANONICAL_FACTORS, infer_factor_exposures

FACTOR_TS_SCHEMA_VERSION = 1

DEFAULT_REGIME_CENTERS: Dict[str, Dict[str, float]] = {
    "risk_on": {"equity_beta": 75.0, "tech_ai": 55.0, "duration": 25.0, "credit_spread": 25.0, "usd_fx": 45.0, "liquidity": 20.0, "concentration": 35.0},
    "risk_off": {"equity_beta": 25.0, "tech_ai": 18.0, "duration": 45.0, "credit_spread": 55.0, "usd_fx": 55.0, "liquidity": 60.0, "concentration": 45.0},
    "rate_shock": {"equity_beta": 35.0, "tech_ai": 28.0, "duration": 78.0, "credit_spread": 42.0, "usd_fx": 50.0, "liquidity": 42.0, "concentration": 35.0},
    "credit_stress": {"equity_beta": 30.0, "tech_ai": 24.0, "duration": 35.0, "credit_spread": 80.0, "usd_fx": 48.0, "liquidity": 70.0, "concentration": 42.0},
    "balanced": {"equity_beta": 50.0, "tech_ai": 35.0, "duration": 35.0, "credit_spread": 35.0, "usd_fx": 45.0, "liquidity": 35.0, "concentration": 32.0},
}


@dataclass(frozen=True)
class FactorMemoryConfig:
    half_life_observations: float = 8.0
    drift_alert_threshold: float = 12.0
    transition_alert_threshold: float = 0.35
    rolling_window: int = 5
    stress_horizon_steps: int = 4

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(str(value).replace("%", "").replace(",", ".").strip())
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _factor_vector(row: Mapping[str, Any]) -> Dict[str, float]:
    """Return a 0-100 factor vector from explicit fields, metadata or static inference."""
    meta = dict(row.get("metadata") or {})
    src = row.get("factor_exposures") or meta.get("factor_exposures") or row.get("factors") or {}
    vector: Dict[str, float] = {}
    if isinstance(src, Mapping):
        for f in CANONICAL_FACTORS:
            if f in src:
                vector[f] = _clamp(_safe_float(src.get(f), 0.0))
    if len(vector) < len(CANONICAL_FACTORS):
        inferred = infer_factor_exposures(row)
        for f in CANONICAL_FACTORS:
            vector.setdefault(f, float(inferred.get(f, 0.0)))
    return {f: round(_clamp(vector.get(f, 0.0)), 4) for f in CANONICAL_FACTORS}


def _date_key(row: Mapping[str, Any], idx: int) -> str:
    return str(row.get("date") or row.get("as_of") or row.get("timestamp") or f"t{idx:04d}")


def build_factor_timeseries(observations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Normalize observations into chronological factor vectors."""
    points: List[Dict[str, Any]] = []
    for idx, row in enumerate(observations or []):
        if not isinstance(row, Mapping):
            continue
        vector = _factor_vector(row)
        weight = _safe_float(row.get("weight_pct") or row.get("weight") or 100.0, 100.0)
        points.append({
            "date": _date_key(row, idx),
            "symbol": str(row.get("symbol") or row.get("ticker") or row.get("name") or "PORTFOLIO").upper(),
            "weight_pct": round(weight, 4),
            "factor_vector": vector,
            "source_quality": _clamp(_safe_float(row.get("source_quality") or row.get("confidence"), 70.0)),
        })
    points.sort(key=lambda x: str(x["date"]))
    return {
        "schema_version": FACTOR_TS_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "app_version": get_app_version(),
        "observation_count": len(points),
        "factors": list(CANONICAL_FACTORS),
        "points": points,
    }


def rolling_factor_exposures(observations: Sequence[Mapping[str, Any]], window: int = 5) -> List[Dict[str, Any]]:
    ts = build_factor_timeseries(observations)
    pts = ts["points"]
    window = max(1, int(window or 1))
    out: List[Dict[str, Any]] = []
    for i, point in enumerate(pts):
        chunk = pts[max(0, i - window + 1): i + 1]
        avg = {f: round(sum(p["factor_vector"].get(f, 0.0) for p in chunk) / len(chunk), 4) for f in CANONICAL_FACTORS}
        out.append({"date": point["date"], "window": len(chunk), "rolling_exposure": avg})
    return out


def detect_regime(vector: Mapping[str, float]) -> Dict[str, Any]:
    """Classify a factor vector by nearest canonical regime center."""
    distances: Dict[str, float] = {}
    for regime, center in DEFAULT_REGIME_CENTERS.items():
        dist = math.sqrt(sum((float(vector.get(f, 0.0)) - center.get(f, 0.0)) ** 2 for f in CANONICAL_FACTORS) / len(CANONICAL_FACTORS))
        distances[regime] = dist
    best = min(distances, key=distances.get) if distances else "balanced"
    inv = {k: 1.0 / (v + 1.0) for k, v in distances.items()}
    total = sum(inv.values()) or 1.0
    probs = {k: round(v / total, 4) for k, v in inv.items()}
    return {"regime": best, "confidence": probs.get(best, 0.0), "probabilities": probs, "distance": round(distances.get(best, 0.0), 4)}


def detect_regime_transitions(observations: Sequence[Mapping[str, Any]], window: int = 5) -> List[Dict[str, Any]]:
    roll = rolling_factor_exposures(observations, window)
    transitions: List[Dict[str, Any]] = []
    prev: Optional[Dict[str, Any]] = None
    for item in roll:
        detected = detect_regime(item["rolling_exposure"])
        entry = {"date": item["date"], "regime": detected["regime"], "confidence": detected["confidence"], "probabilities": detected["probabilities"]}
        if prev and prev["regime"] != entry["regime"]:
            transitions.append({
                "date": item["date"],
                "from_regime": prev["regime"],
                "to_regime": entry["regime"],
                "confidence_delta": round(entry["confidence"] - float(prev.get("confidence", 0.0)), 4),
            })
        prev = entry
    return transitions


def latent_beta_drift(observations: Sequence[Mapping[str, Any]], baseline_window: int = 3, current_window: int = 3) -> Dict[str, Any]:
    roll = rolling_factor_exposures(observations, window=max(baseline_window, current_window, 1))
    if not roll:
        return {"drift_score": 0.0, "factor_drift": {}, "alerts": []}
    base_chunk = roll[:max(1, min(baseline_window, len(roll)))]
    cur_chunk = roll[-max(1, min(current_window, len(roll))):]
    base = {f: sum(x["rolling_exposure"][f] for x in base_chunk) / len(base_chunk) for f in CANONICAL_FACTORS}
    cur = {f: sum(x["rolling_exposure"][f] for x in cur_chunk) / len(cur_chunk) for f in CANONICAL_FACTORS}
    drift = {f: round(cur[f] - base[f], 4) for f in CANONICAL_FACTORS}
    score = round(sum(abs(v) for v in drift.values()) / len(CANONICAL_FACTORS), 4)
    alerts = [f for f, v in drift.items() if abs(v) >= 12.0]
    return {"drift_score": score, "factor_drift": drift, "baseline": {k: round(v, 4) for k, v in base.items()}, "current": {k: round(v, 4) for k, v in cur.items()}, "alerts": alerts}


def temporal_stress_propagation(observations: Sequence[Mapping[str, Any]], shock_vector: Optional[Mapping[str, float]] = None, horizon_steps: int = 4) -> Dict[str, Any]:
    roll = rolling_factor_exposures(observations, window=3)
    latest = roll[-1]["rolling_exposure"] if roll else {f: 0.0 for f in CANONICAL_FACTORS}
    shock = dict(shock_vector or {"equity_beta": -18.0, "tech_ai": -24.0, "duration": -10.0, "credit_spread": -16.0, "usd_fx": -4.0, "liquidity": -12.0, "concentration": -8.0})
    path: List[Dict[str, Any]] = []
    cumulative = 0.0
    for step in range(1, max(1, int(horizon_steps or 1)) + 1):
        decay = 1.0 / math.sqrt(step)
        impacts = {f: round((latest.get(f, 0.0) / 100.0) * _safe_float(shock.get(f), 0.0) * decay, 4) for f in CANONICAL_FACTORS}
        total = round(sum(impacts.values()), 4)
        cumulative = round(cumulative + total, 4)
        path.append({"step": step, "decay": round(decay, 4), "factor_impacts": impacts, "total_impact_pct": total, "cumulative_impact_pct": cumulative})
    return {"latest_exposure": latest, "shock_vector": {f: _safe_float(shock.get(f), 0.0) for f in CANONICAL_FACTORS}, "path": path, "worst_step_impact_pct": min((p["total_impact_pct"] for p in path), default=0.0), "cumulative_impact_pct": cumulative}


def update_adaptive_factor_memory(previous_memory: Optional[Mapping[str, Any]], new_observation: Mapping[str, Any], config: Optional[FactorMemoryConfig | Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Online exponential-memory update for live use."""
    cfg = config if isinstance(config, FactorMemoryConfig) else FactorMemoryConfig(**dict(config or {}))
    prev = dict(previous_memory or {})
    old = dict(prev.get("factor_memory") or {})
    obs = _factor_vector(new_observation)
    alpha = 1.0 - math.exp(math.log(0.5) / max(1.0, cfg.half_life_observations))
    updated = {f: round((1 - alpha) * _safe_float(old.get(f), obs[f]) + alpha * obs[f], 4) for f in CANONICAL_FACTORS}
    previous_regime = str(prev.get("current_regime") or "")
    detected = detect_regime(updated)
    drift = {f: round(updated[f] - _safe_float(old.get(f), updated[f]), 4) for f in CANONICAL_FACTORS}
    alerts: List[str] = []
    for f, v in drift.items():
        if abs(v) >= cfg.drift_alert_threshold:
            alerts.append(f"factor_drift:{f}")
    if previous_regime and previous_regime != detected["regime"] and detected["confidence"] >= cfg.transition_alert_threshold:
        alerts.append(f"regime_transition:{previous_regime}->{detected['regime']}")
    return {
        "schema_version": FACTOR_TS_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "app_version": get_app_version(),
        "config": cfg.as_dict(),
        "observation_count": int(prev.get("observation_count") or 0) + 1,
        "alpha": round(alpha, 6),
        "factor_memory": updated,
        "last_observation": obs,
        "factor_drift_since_last": drift,
        "current_regime": detected["regime"],
        "regime_confidence": detected["confidence"],
        "alerts": alerts,
    }


def build_factor_timeseries_intelligence(observations: Sequence[Mapping[str, Any]], config: Optional[FactorMemoryConfig | Mapping[str, Any]] = None) -> Dict[str, Any]:
    cfg = config if isinstance(config, FactorMemoryConfig) else FactorMemoryConfig(**dict(config or {}))
    ts = build_factor_timeseries(observations)
    rolling = rolling_factor_exposures(observations, cfg.rolling_window)
    transitions = detect_regime_transitions(observations, cfg.rolling_window)
    drift = latent_beta_drift(observations)
    stress = temporal_stress_propagation(observations, horizon_steps=cfg.stress_horizon_steps)
    memory: Optional[Dict[str, Any]] = None
    for row in observations or []:
        memory = update_adaptive_factor_memory(memory, row, cfg)
    latest_regime = detect_regime(rolling[-1]["rolling_exposure"]) if rolling else detect_regime({})
    return {
        "schema_version": FACTOR_TS_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "app_version": get_app_version(),
        "config": cfg.as_dict(),
        "factor_timeseries": ts,
        "rolling_exposures": rolling,
        "latest_regime": latest_regime,
        "regime_transitions": transitions,
        "latent_beta_drift": drift,
        "temporal_stress": stress,
        "adaptive_memory": memory or update_adaptive_factor_memory(None, {}, cfg),
        "summary": {
            "observation_count": ts["observation_count"],
            "transition_count": len(transitions),
            "drift_score": drift.get("drift_score", 0.0),
            "current_regime": latest_regime.get("regime"),
            "stress_cumulative_impact_pct": stress.get("cumulative_impact_pct", 0.0),
        },
    }
