"""Bounded and diagnosable quality overlay for Technical Quality Challenger.

v19.11.0 keeps the pure technical production benchmark unchanged while making
quality evidence explicit: MISSING is not the same as BELOW_THRESHOLD, all
0-1/0-100 conversions are traceable and insufficient evidence cannot be
mistaken for a quality approval.
"""
from __future__ import annotations

from typing import Any, Mapping
import hashlib
import json

from domain.market_snapshot import CandidateSnapshot
from services.quality_evidence_normalizer import (
    STATUS_AVAILABLE,
    STATUS_BELOW_THRESHOLD,
    STATUS_INVALID,
    STATUS_MISSING,
    classify_threshold,
    coverage_summary,
    normalize_score,
    source_consensus_score,
)
from services.technical_signal_service import (
    TechnicalSignalService,
    get_technical_signal_service,
    normalize_technical_parameter_overrides,
)

TECHNICAL_QUALITY_SERVICE_VERSION = "1.1"
TECHNICAL_QUALITY_POLICY_VERSION = "quality-policy-1.1"

TECHNICAL_QUALITY_DEFAULTS = {
    "minimum_data_quality": 55.0,
    "minimum_liquidity": 35.0,
    "minimum_source_consensus": 40.0,
    "minimum_evidence_components": 2,
    "minimum_critical_evidence_components": 2,
    "maximum_positive_adjustment": 1.0,
    "maximum_negative_adjustment": 1.5,
    "critical_event_blocks_entry": True,
    "insufficient_evidence_blocks_buy": True,
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
        "minimum_critical_evidence_components": (1.0, 3.0),
        "maximum_positive_adjustment": (0.0, 2.0),
        "maximum_negative_adjustment": (0.0, 3.0),
    }
    for key, (low, high) in numeric.items():
        if key in raw:
            number = _number(raw.get(key), policy[key])
            value_normalized = _clamp(float(number if number is not None else policy[key]), low, high)
            policy[key] = int(value_normalized) if key.startswith("minimum_") and key.endswith("components") else value_normalized
    for key in ("critical_event_blocks_entry", "insufficient_evidence_blocks_buy"):
        if key in raw:
            policy[key] = bool(raw.get(key))
    return policy


def policy_checksum(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value or {}), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _component(candidate: CandidateSnapshot, row: Mapping[str, Any], name: str, value: Any, *, source: str) -> dict[str, Any]:
    stored = candidate.quality_evidence.get(name) if isinstance(candidate.quality_evidence, Mapping) else None
    if isinstance(stored, Mapping):
        return dict(stored)
    if name == "source_consensus":
        return source_consensus_score(value, source=source)
    return normalize_score(value, source=source)


class TechnicalQualityService:
    def __init__(self, technical_service: TechnicalSignalService | None = None):
        self.technical_service = technical_service or get_technical_signal_service()

    def evidence(self, candidate: CandidateSnapshot) -> dict[str, Any]:
        row = dict(candidate.decision_inputs or {})
        analyst = row.get("analyst") if isinstance(row.get("analyst"), Mapping) else {}
        earnings = row.get("earnings") if isinstance(row.get("earnings"), Mapping) else {}
        regime = row.get("market_regime") if isinstance(row.get("market_regime"), Mapping) else {}

        data_quality_raw = candidate.data_quality
        if data_quality_raw is None:
            data_quality_raw = _first(row, "data_quality", "data_quality_score", "quality_score")
        consensus_raw = candidate.source_consensus
        if consensus_raw is None:
            consensus_raw = _first(row, "source_consensus", "source_confidence", "consensus_score")
        liquidity_raw = candidate.liquidity
        if liquidity_raw is None:
            # Deliberately exclude average_volume: raw volume is not a 0-100 score.
            liquidity_raw = _first(row, "liquidity_score", "liquidity")

        analyst_raw = _first(row, "analyst_score", "recommendation_score")
        if analyst_raw is None:
            analyst_raw = _trend_score(analyst.get("trend") or _first(row, "analyst_trend", "recommendation_trend"))
        regime_raw = _first(row, "market_regime_score", "sector_relative_strength", "relative_strength")
        if regime_raw is None:
            regime_raw = _trend_score(regime.get("trend") or _first(row, "market_regime", "sector_trend"))

        components = {
            "data_quality": _component(candidate, row, "data_quality", data_quality_raw, source="candidate_data_quality"),
            "source_consensus": _component(candidate, row, "source_consensus", consensus_raw, source="candidate_source_consensus"),
            "liquidity": _component(candidate, row, "liquidity", liquidity_raw, source="candidate_liquidity_score"),
            "insider_score": _component(candidate, row, "insider_score", _first(row, "insider_score"), source="insider_intelligence"),
            "analyst_score": _component(candidate, row, "analyst_score", analyst_raw, source="analyst_data"),
            "market_regime_score": _component(candidate, row, "market_regime_score", regime_raw, source="market_regime"),
            "news_score": _component(candidate, row, "news_score", _first(row, "news_score", "sentiment_score"), source="news_intelligence"),
        }
        earnings_value = earnings.get("surprise", _first(row, "earnings_surprise", "surprise"))
        stored_earnings = candidate.quality_evidence.get("earnings_surprise") if isinstance(candidate.quality_evidence, Mapping) else None
        components["earnings_surprise"] = dict(stored_earnings) if isinstance(stored_earnings, Mapping) else {
            "status": STATUS_AVAILABLE if _number(earnings_value) is not None else STATUS_MISSING,
            "value": _number(earnings_value),
            "raw_value": earnings_value,
            "source": "earnings_data",
            "normalised_from": "percentage_surprise",
        }
        critical_event = bool(_first(row, "critical_event", "event_risk_critical", "severe_event_risk") or False)
        return {"components": components, "critical_event": critical_event}

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
        components = {name: dict(value or {}) for name, value in evidence["components"].items()}
        diagnostics: list[dict[str, Any]] = []
        adjustments: list[dict[str, Any]] = []
        blocker_codes: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        thresholds = {
            "data_quality": policy["minimum_data_quality"],
            "liquidity": policy["minimum_liquidity"],
            "source_consensus": policy["minimum_source_consensus"],
        }
        labels = {
            "data_quality": "Datakvalitet",
            "liquidity": "Likviditet",
            "source_consensus": "Kildekonsensus",
            "insider_score": "Insiderdata",
            "analyst_score": "Analytikerdata",
            "earnings_surprise": "Resultatdata",
            "market_regime_score": "Markedsregime",
            "news_score": "Nyhetsdata",
        }
        for name, component in components.items():
            diagnosed = classify_threshold(component, thresholds.get(name))
            diagnosed.update({"component": name, "label": labels.get(name, name)})
            diagnostics.append(diagnosed)
            if diagnosed.get("threshold_status") == STATUS_BELOW_THRESHOLD:
                code = f"{name.upper()}_BELOW_THRESHOLD"
                blocker_codes.append(code)
                value = float(diagnosed.get("value") or 0.0)
                threshold = float(diagnosed.get("threshold") or 0.0)
                blockers.append(f"{labels.get(name, name)} {value:.1f} under terskel {threshold:.1f}")
            elif diagnosed.get("status") == STATUS_MISSING:
                warnings.append(f"MANGLER DATA: {labels.get(name, name)}")
            elif diagnosed.get("status") == STATUS_INVALID:
                warnings.append(f"UGYLDIG DATA: {labels.get(name, name)}")

        if evidence["critical_event"] and policy["critical_event_blocks_entry"]:
            blocker_codes.append("CRITICAL_EVENT_RISK")
            blockers.append("Kritisk hendelsesrisiko blokkerer ny inngang")

        coverage = coverage_summary(
            components,
            minimum_components=int(policy["minimum_evidence_components"]),
        )
        required_critical = int(policy["minimum_critical_evidence_components"])
        evidence_sufficient = bool(
            coverage["available_components"] >= int(policy["minimum_evidence_components"])
            and coverage["available_critical_components"] >= required_critical
        )
        coverage["required_critical_components"] = required_critical
        coverage["sufficient_evidence"] = evidence_sufficient
        if not evidence_sufficient:
            warnings.append(
                "MANGLER DATA: utilstrekkelig kvalitetsevidens "
                f"({coverage['available_components']} komponenter, {coverage['available_critical_components']} kritiske)"
            )

        weights = {
            "data_quality": 0.35,
            "source_consensus": 0.20,
            "liquidity": 0.30,
            "insider_score": 0.25,
            "analyst_score": 0.20,
            "market_regime_score": 0.20,
            "news_score": 0.15,
        }
        for name, weight in weights.items():
            component = components.get(name, {})
            if component.get("status") != STATUS_AVAILABLE or component.get("value") is None:
                continue
            value = _clamp(float(component["value"]), 0.0, 100.0)
            delta = ((value - 50.0) / 50.0) * weight
            adjustments.append({"component": name, "value": round(value, 3), "delta": round(delta, 3)})
        earnings = components.get("earnings_surprise", {})
        if earnings.get("status") == STATUS_AVAILABLE and _number(earnings.get("value")) is not None:
            surprise = _clamp(float(earnings["value"]), -20.0, 20.0)
            adjustments.append({"component": "earnings_surprise", "value": round(surprise, 3), "delta": round((surprise / 20.0) * 0.25, 3)})

        raw_delta = sum(float(item["delta"]) for item in adjustments)
        delta = _clamp(raw_delta, -float(policy["maximum_negative_adjustment"]), float(policy["maximum_positive_adjustment"]))
        base_score = float(base.get("score") or 0.0)
        adjusted_score = round(_clamp(base_score + delta, 0.0, 10.0), 2)
        technical_profile = normalize_technical_parameter_overrides(technical_parameters)
        base_decision = str(base.get("decision") or "HOLD / WAIT").upper()
        positive_confirmation = bool(base.get("macd_bullish")) or str(base.get("breakout_type") or "").lower() in {"bullish", "breakout", "up"}

        if blockers:
            decision = "SELL / AVOID"
        elif not evidence_sufficient and policy["insufficient_evidence_blocks_buy"]:
            decision = "HOLD / WAIT"
        elif "SELL" in base_decision or "AVOID" in base_decision:
            decision = "SELL / AVOID"
        elif adjusted_score >= float(technical_profile["buy_score_threshold"]) and positive_confirmation:
            decision = "BUY"
        elif adjusted_score <= float(technical_profile["sell_score_threshold"]):
            decision = "SELL / AVOID"
        else:
            decision = "HOLD / WAIT"

        confidence = int(_clamp((float(base.get("confidence") or 35.0) * 0.70) + min(coverage["available_components"], 8) / 8.0 * 30.0, 35.0, 95.0))
        reasons = list(base.get("reasons") or [])
        for item in adjustments:
            if float(item["delta"]) >= 0.12:
                reasons.append(f"Kvalitetsstøtte: {item['component']} ({item['delta']:+.2f})")
            elif float(item["delta"]) <= -0.12:
                warnings.append(f"Kvalitetstrekk: {item['component']} ({item['delta']:+.2f})")
        warnings.extend(blockers)

        return {
            **dict(base),
            "score": adjusted_score,
            "final_score": adjusted_score,
            "decision_score": adjusted_score,
            "decision": decision,
            "confidence": confidence,
            "reasons": reasons[:16],
            "warnings": warnings[:20],
            "technical_base_score": base_score,
            "quality_adjustment": round(delta, 3),
            "quality_adjustment_raw": round(raw_delta, 3),
            "quality_evidence": {name: component.get("value") for name, component in components.items()},
            "quality_evidence_components": components,
            "quality_diagnostics": diagnostics,
            "quality_components": adjustments,
            "quality_component_count": coverage["available_components"],
            "quality_critical_component_count": coverage["available_critical_components"],
            "quality_evidence_sufficient": evidence_sufficient,
            "quality_missing_components": coverage["missing_components"],
            "quality_invalid_components": coverage["invalid_components"],
            "quality_blockers": blockers,
            "quality_blocker_codes": blocker_codes,
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
