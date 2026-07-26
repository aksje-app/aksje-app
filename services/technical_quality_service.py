"""Bounded quality overlay for the v19.10.0 Technical Quality Challenger.

The pure technical production benchmark remains unchanged. This service reads
additional evidence already present in the same CandidateSnapshot and produces
an isolated, read-only challenger result.
"""
from __future__ import annotations

from typing import Any, Mapping
import hashlib
import json

from domain.market_snapshot import CandidateSnapshot
from services.technical_signal_service import (
    TECHNICAL_DECISION_DEFAULTS,
    TechnicalSignalService,
    get_technical_signal_service,
    normalize_technical_parameter_overrides,
)

TECHNICAL_QUALITY_SERVICE_VERSION = "1.0"
TECHNICAL_QUALITY_POLICY_VERSION = "quality-policy-1.0"

TECHNICAL_QUALITY_DEFAULTS = {
    "minimum_data_quality": 55.0,
    "minimum_liquidity": 35.0,
    "minimum_source_consensus": 40.0,
    "minimum_evidence_components": 2,
    "maximum_positive_adjustment": 1.0,
    "maximum_negative_adjustment": 1.5,
    "critical_event_blocks_entry": True,
}


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            return value
    return None


def _trend_score(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if any(token in text for token in ("positive", "bull", "up", "opp", "strong")):
        return 75.0
    if any(token in text for token in ("negative", "bear", "down", "ned", "weak")):
        return 25.0
    return 50.0


def normalize_quality_policy(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    policy = dict(TECHNICAL_QUALITY_DEFAULTS)
    numeric = {
        "minimum_data_quality": (0.0, 100.0),
        "minimum_liquidity": (0.0, 100.0),
        "minimum_source_consensus": (0.0, 100.0),
        "minimum_evidence_components": (1.0, 8.0),
        "maximum_positive_adjustment": (0.0, 2.0),
        "maximum_negative_adjustment": (0.0, 3.0),
    }
    for key, (low, high) in numeric.items():
        if key in raw:
            value = _clamp(float(_number(raw.get(key), policy[key]) or policy[key]), low, high)
            policy[key] = int(value) if key == "minimum_evidence_components" else value
    if "critical_event_blocks_entry" in raw:
        policy["critical_event_blocks_entry"] = bool(raw.get("critical_event_blocks_entry"))
    return policy


def policy_checksum(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value or {}), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TechnicalQualityService:
    def __init__(self, technical_service: TechnicalSignalService | None = None):
        self.technical_service = technical_service or get_technical_signal_service()

    def evidence(self, candidate: CandidateSnapshot) -> dict[str, Any]:
        row = dict(candidate.decision_inputs or {})
        analyst = row.get("analyst") if isinstance(row.get("analyst"), Mapping) else {}
        earnings = row.get("earnings") if isinstance(row.get("earnings"), Mapping) else {}
        regime = row.get("market_regime") if isinstance(row.get("market_regime"), Mapping) else {}
        data_quality = candidate.data_quality
        if data_quality is None:
            data_quality = _number(_first(row, "data_quality", "data_quality_score", "quality_score"))
        source_consensus = candidate.source_consensus
        if source_consensus is None:
            source_consensus = _number(_first(row, "source_consensus", "source_confidence", "consensus_score"))
        liquidity = candidate.liquidity
        if liquidity is None:
            liquidity = _number(_first(row, "liquidity_score", "liquidity"))
        insider = _number(_first(row, "insider_score"))
        analyst_score = _number(_first(row, "analyst_score", "recommendation_score"))
        if analyst_score is None:
            analyst_score = _trend_score(analyst.get("trend") or _first(row, "analyst_trend", "recommendation_trend"))
        earnings_surprise = _number(earnings.get("surprise", _first(row, "earnings_surprise", "surprise")))
        regime_score = _number(_first(row, "market_regime_score", "sector_relative_strength", "relative_strength"))
        if regime_score is None:
            regime_score = _trend_score(regime.get("trend") or _first(row, "market_regime", "sector_trend"))
        news_score = _number(_first(row, "news_score", "sentiment_score"))
        critical_event = bool(_first(row, "critical_event", "event_risk_critical", "severe_event_risk") or False)
        return {
            "data_quality": data_quality,
            "source_consensus": source_consensus,
            "liquidity": liquidity,
            "insider_score": insider,
            "analyst_score": analyst_score,
            "earnings_surprise": earnings_surprise,
            "market_regime_score": regime_score,
            "news_score": news_score,
            "critical_event": critical_event,
        }

    def evaluate(
        self,
        candidate: CandidateSnapshot,
        *,
        run_id: str = "",
        source: str = "technical_quality_challenger",
        technical_parameters: Mapping[str, Any] | None = None,
        quality_policy: Mapping[str, Any] | None = None,
        model_version: str = "quality-1.0.0",
        parameter_version: str = "technical-quality-1.0",
    ) -> dict[str, Any]:
        base = self.technical_service.evaluate(
            candidate,
            run_id=run_id,
            source=source,
            parameter_overrides=technical_parameters,
            model_version=model_version,
            parameter_version=parameter_version,
        )
        policy = normalize_quality_policy(quality_policy)
        evidence = self.evidence(candidate)
        adjustments: list[dict[str, Any]] = []
        blockers: list[str] = []
        warnings: list[str] = []

        def add_component(name: str, value: float | None, weight: float) -> None:
            if value is None:
                return
            normalized = _clamp(value, 0.0, 100.0)
            delta = ((normalized - 50.0) / 50.0) * weight
            adjustments.append({"component": name, "value": round(value, 3), "delta": round(delta, 3)})

        add_component("data_quality", evidence["data_quality"], 0.35)
        add_component("source_consensus", evidence["source_consensus"], 0.20)
        add_component("liquidity", evidence["liquidity"], 0.30)
        add_component("insider", evidence["insider_score"], 0.25)
        add_component("analyst", evidence["analyst_score"], 0.20)
        if evidence["earnings_surprise"] is not None:
            surprise = _clamp(float(evidence["earnings_surprise"]), -20.0, 20.0)
            adjustments.append({"component": "earnings_surprise", "value": round(surprise, 3), "delta": round((surprise / 20.0) * 0.25, 3)})
        add_component("market_regime", evidence["market_regime_score"], 0.20)
        add_component("news_context", evidence["news_score"], 0.15)

        if evidence["data_quality"] is not None and evidence["data_quality"] < policy["minimum_data_quality"]:
            blockers.append(f"Data quality {evidence['data_quality']:.1f} below quality threshold")
        if evidence["liquidity"] is not None and evidence["liquidity"] < policy["minimum_liquidity"]:
            blockers.append(f"Liquidity {evidence['liquidity']:.1f} below quality threshold")
        if evidence["source_consensus"] is not None and evidence["source_consensus"] < policy["minimum_source_consensus"]:
            blockers.append(f"Source consensus {evidence['source_consensus']:.1f} below quality threshold")
        if evidence["critical_event"] and policy["critical_event_blocks_entry"]:
            blockers.append("Critical event risk blocks new entry")

        coverage = len(adjustments)
        if coverage < int(policy["minimum_evidence_components"]):
            warnings.append(f"Limited quality evidence: {coverage} components")

        raw_delta = sum(float(item["delta"]) for item in adjustments)
        delta = _clamp(raw_delta, -float(policy["maximum_negative_adjustment"]), float(policy["maximum_positive_adjustment"]))
        base_score = float(base.get("score") or 0.0)
        adjusted_score = round(_clamp(base_score + delta, 0.0, 10.0), 2)
        technical_profile = normalize_technical_parameter_overrides(technical_parameters)
        base_decision = str(base.get("decision") or "HOLD / WAIT").upper()
        positive_confirmation = bool(base.get("macd_bullish")) or str(base.get("breakout_type") or "").lower() in {"bullish", "breakout", "up"}

        if blockers:
            decision = "SELL / AVOID"
        elif "SELL" in base_decision or "AVOID" in base_decision:
            decision = "SELL / AVOID"
        elif adjusted_score >= float(technical_profile["buy_score_threshold"]) and positive_confirmation:
            decision = "BUY"
        elif adjusted_score <= float(technical_profile["sell_score_threshold"]):
            decision = "SELL / AVOID"
        else:
            decision = "HOLD / WAIT"

        confidence = int(_clamp((float(base.get("confidence") or 35.0) * 0.70) + min(coverage, 8) / 8.0 * 30.0, 35.0, 95.0))
        reasons = list(base.get("reasons") or [])
        for item in adjustments:
            if float(item["delta"]) >= 0.12:
                reasons.append(f"Quality support: {item['component']} ({item['delta']:+.2f})")
            elif float(item["delta"]) <= -0.12:
                warnings.append(f"Quality drag: {item['component']} ({item['delta']:+.2f})")
        warnings.extend(blockers)

        return {
            **dict(base),
            "score": adjusted_score,
            "final_score": adjusted_score,
            "decision_score": adjusted_score,
            "decision": decision,
            "confidence": confidence,
            "reasons": reasons[:12],
            "warnings": warnings[:12],
            "technical_base_score": base_score,
            "quality_adjustment": round(delta, 3),
            "quality_adjustment_raw": round(raw_delta, 3),
            "quality_evidence": evidence,
            "quality_components": adjustments,
            "quality_component_count": coverage,
            "quality_blockers": blockers,
            "quality_policy": policy,
            "quality_policy_version": TECHNICAL_QUALITY_POLICY_VERSION,
            "quality_policy_checksum": policy_checksum(policy),
            "technical_quality_service_version": TECHNICAL_QUALITY_SERVICE_VERSION,
            "read_only": True,
            "execution_authorized": False,
        }


_default: TechnicalQualityService | None = None


def get_technical_quality_service() -> TechnicalQualityService:
    global _default
    if _default is None:
        _default = TechnicalQualityService()
    return _default
