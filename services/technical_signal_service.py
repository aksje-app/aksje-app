"""Pure technical signal service extracted from the legacy signal engine.

The scoring rules are intentionally identical to v19.5.0. v19.6.0 only moves
ownership, adds canonical snapshot input and returns traceable model metadata.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import hashlib
import json

from domain.market_snapshot import CandidateSnapshot
from services.market_snapshot_service import MarketSnapshotService, get_market_snapshot_service
from utils import _clamp, _safe_float

TECHNICAL_SIGNAL_SCHEMA_VERSION = "1.0"
TECHNICAL_SIGNAL_MODEL_VERSION = "legacy-1.0.0"
TECHNICAL_SIGNAL_PARAMETER_VERSION = "paper-trading-rules-current"

TECHNICAL_DECISION_DEFAULTS = {
    "buy_score_threshold": 7.2,
    "sell_score_threshold": 4.2,
    "maximum_buy_rsi": 70.0,
    "extreme_sell_rsi": 80.0,
    "block_high_risk": True,
    "require_positive_confirmation": True,
}


def normalize_technical_parameter_overrides(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a bounded decision profile without changing legacy defaults."""
    raw = dict(value or {})
    out = dict(TECHNICAL_DECISION_DEFAULTS)
    numeric_bounds = {
        "buy_score_threshold": (0.0, 10.0),
        "sell_score_threshold": (0.0, 10.0),
        "maximum_buy_rsi": (0.0, 100.0),
        "extreme_sell_rsi": (0.0, 100.0),
    }
    for key, (low, high) in numeric_bounds.items():
        if key in raw:
            out[key] = float(_clamp(_safe_float(raw.get(key), out[key]), low, high))
    for key in ("block_high_risk", "require_positive_confirmation"):
        if key in raw:
            out[key] = bool(raw.get(key))
    if out["sell_score_threshold"] > out["buy_score_threshold"]:
        out["sell_score_threshold"] = out["buy_score_threshold"]
    return out


def technical_parameter_checksum(parameters: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(parameters or {}), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get(item: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, Mapping) else default


def _risk_label(risk_score: float) -> str:
    if risk_score >= 70:
        return "Høy"
    if risk_score >= 40:
        return "Middels"
    return "Lav"


class TechnicalSignalService:
    def __init__(self, snapshot_service: MarketSnapshotService | None = None):
        self.snapshot_service = snapshot_service or get_market_snapshot_service()

    def _coerce_snapshot(
        self,
        item: Mapping[str, Any] | CandidateSnapshot,
        technical_context: Mapping[str, Any] | None,
        *,
        run_id: str = "",
        source: str = "",
        market_snapshot_id: str = "",
    ) -> CandidateSnapshot:
        if isinstance(item, CandidateSnapshot):
            return item
        if isinstance(item, Mapping) and item.get("candidate_snapshot_id") and item.get("decision_inputs") is not None:
            return CandidateSnapshot.from_mapping(item)
        return self.snapshot_service.build_candidate_snapshot(
            dict(item or {}),
            technical_context,
            run_id=run_id,
            source=source or "technical_signal_service",
            market_snapshot_id=market_snapshot_id,
        )

    def evaluate(
        self,
        item: Mapping[str, Any] | CandidateSnapshot,
        technical_context: Mapping[str, Any] | None = None,
        insider: Mapping[str, Any] | None = None,
        analyst: Mapping[str, Any] | None = None,
        earnings: Mapping[str, Any] | None = None,
        *,
        run_id: str = "",
        source: str = "",
        market_snapshot_id: str = "",
        parameter_overrides: Mapping[str, Any] | None = None,
        model_version: str = "",
        parameter_version: str = "",
    ) -> dict[str, Any]:
        snapshot = self._coerce_snapshot(
            item, technical_context, run_id=run_id, source=source, market_snapshot_id=market_snapshot_id
        )
        decision_input = dict(snapshot.decision_inputs or {})
        technical = dict(snapshot.technical or {})
        return self._evaluate_legacy_rules(
            decision_input, technical, insider, analyst, earnings, snapshot,
            parameters=normalize_technical_parameter_overrides(parameter_overrides),
            model_version=model_version or TECHNICAL_SIGNAL_MODEL_VERSION,
            parameter_version=parameter_version or TECHNICAL_SIGNAL_PARAMETER_VERSION,
        )

    def evaluate_many(
        self,
        candidates: Sequence[Mapping[str, Any] | CandidateSnapshot],
        *,
        run_id: str = "",
        source: str = "technical_signal_batch",
        market_snapshot_id: str = "",
        parameter_overrides: Mapping[str, Any] | None = None,
        model_version: str = "",
        parameter_version: str = "",
    ) -> list[dict[str, Any]]:
        return [
            self.evaluate(
                candidate, run_id=run_id, source=source, market_snapshot_id=market_snapshot_id,
                parameter_overrides=parameter_overrides, model_version=model_version, parameter_version=parameter_version,
            )
            for candidate in candidates or []
        ]

    def _evaluate_legacy_rules(
        self,
        item: Mapping[str, Any],
        technical_context: Mapping[str, Any],
        insider: Mapping[str, Any] | None,
        analyst: Mapping[str, Any] | None,
        earnings: Mapping[str, Any] | None,
        snapshot: CandidateSnapshot,
        *,
        parameters: Mapping[str, Any],
        model_version: str,
        parameter_version: str,
    ) -> dict[str, Any]:
        reasons: list[str] = []
        warnings: list[str] = []

        base_score = _safe_float(_get(item, "score", 5.0), 5.0)
        score = base_score
        risk_score = 25

        rsi = _safe_float(technical_context.get("rsi", _get(item, "rsi", 50)), 50)
        macd_bullish = bool(technical_context.get("macd_bullish", _get(item, "macd_bullish", False)))
        breakout_type = str(technical_context.get("breakout_type", _get(item, "breakout_type", "neutral"))).lower()
        trend = str(technical_context.get("trend", _get(item, "trend", "neutral"))).lower()
        channel_pos = _safe_float(technical_context.get("channel_pos", _get(item, "channel_pos", 50)), 50)

        head_shoulders = bool(technical_context.get("head_shoulders_found", False))
        inverse_hs = bool(technical_context.get("inverse_head_shoulders_found", False))

        if rsi >= 80:
            score -= 1.2; risk_score += 25; warnings.append("RSI er ekstremt overkjøpt")
        elif rsi >= 70:
            score -= 0.7; risk_score += 15; warnings.append("RSI er overkjøpt")
        elif rsi <= 30:
            score += 0.5; reasons.append("RSI er lav / mulig oversolgt")
        elif 45 <= rsi <= 65:
            score += 0.35; reasons.append("RSI er i sunn sone")

        if trend in ["up", "opp", "bullish", "positive"]:
            score += 0.6; reasons.append("Trend peker opp")
        elif trend in ["down", "ned", "bearish", "negative"]:
            score -= 0.8; risk_score += 20; warnings.append("Trend peker ned")

        if macd_bullish:
            score += 0.45; reasons.append("MACD støtter oppside")
        else:
            score -= 0.15; warnings.append("MACD gir ikke tydelig støtte")

        if breakout_type in ["bullish", "breakout", "up"]:
            score += 0.7; reasons.append("Bullish breakout / brudd opp")
        elif breakout_type in ["bearish", "breakdown", "down"]:
            score -= 1.0; risk_score += 25; warnings.append("Bearish brudd / svak teknisk struktur")

        if channel_pos >= 85:
            score -= 0.5; risk_score += 15; warnings.append("Kursen ligger høyt i trendkanalen")
        elif channel_pos <= 25:
            score += 0.25; reasons.append("Kursen ligger lavt/moderat i trendkanalen")
        else:
            reasons.append("Kursen ligger ikke ekstremt i kanalen")

        if inverse_hs:
            score += 0.4; reasons.append("Bullish mønster støtter oppside")
        if head_shoulders:
            score -= 0.8; risk_score += 25; warnings.append("Bearish mønster øker risiko")

        if isinstance(analyst, Mapping):
            analyst_trend = str(analyst.get("trend", "")).lower()
            if "positive" in analyst_trend or "up" in analyst_trend:
                score += 0.25; reasons.append("Analytikertrend støtter aksjen")
            elif "negative" in analyst_trend or "down" in analyst_trend:
                score -= 0.25; warnings.append("Analytikertrend er svak")

        if isinstance(earnings, Mapping):
            surprise = _safe_float(earnings.get("surprise", 0), 0)
            if surprise > 0:
                score += 0.2; reasons.append("Resultater overrasket positivt")
            elif surprise < 0:
                score -= 0.2; warnings.append("Resultater overrasket negativt")

        if not isinstance(insider, Mapping):
            item_insider = _get(item, "insider_score", None)
            if item_insider is not None:
                insider = {"score": item_insider}

        if isinstance(insider, Mapping):
            insider_score = _safe_float(insider.get("score"), None)
            if insider_score is not None:
                if insider_score > 1 and insider_score <= 100:
                    insider_score = insider_score / 100.0
                elif insider_score > 1:
                    insider_score = insider_score / 10.0
                insider_score = _clamp(insider_score, 0, 1)
                insider_delta = (insider_score - 0.5) * 0.9
                score += insider_delta
                if insider_score >= 0.65:
                    reasons.append("Insiderhandler støtter signalet")
                elif insider_score <= 0.35:
                    risk_score += 8; warnings.append("Insiderhandler trekker signalet ned")

        score = round(_clamp(score, 0, 10), 2)
        bonus = round(score - base_score, 2)
        risk_score = int(_clamp(risk_score, 0, 100))
        risk = _risk_label(risk_score)
        confidence = int(_clamp(round(score * 10), 35, 95))

        buy_score_threshold = float(parameters["buy_score_threshold"])
        sell_score_threshold = float(parameters["sell_score_threshold"])
        maximum_buy_rsi = float(parameters["maximum_buy_rsi"])
        extreme_sell_rsi = float(parameters["extreme_sell_rsi"])
        high_risk_block = bool(parameters["block_high_risk"]) and risk == "Høy"
        positive_confirmation = macd_bullish or breakout_type in ["bullish", "breakout", "up"]
        confirmation_ok = positive_confirmation or not bool(parameters["require_positive_confirmation"])

        if score >= buy_score_threshold and not high_risk_block and rsi < maximum_buy_rsi and confirmation_ok:
            decision = "BUY"; emoji = "🟢"
        elif score <= sell_score_threshold or high_risk_block or rsi >= extreme_sell_rsi or breakout_type in ["bearish", "breakdown", "down"]:
            decision = "SELL / AVOID"; emoji = "🔴"
        else:
            decision = "HOLD / WAIT"; emoji = "🟡"

        if not reasons:
            reasons.append("Ingen sterk positiv bekreftelse funnet")
        if not warnings:
            warnings.append("Ingen store risikoflagg funnet")

        return {
            "score": score,
            "final_score": score,
            "decision_score": score,
            "confidence": confidence,
            "bonus": bonus,
            "risk": risk,
            "risk_score": risk_score,
            "decision": decision,
            "emoji": emoji,
            "reasons": reasons[:8],
            "warnings": warnings[:8],
            "rsi": round(rsi, 1),
            "macd_bullish": macd_bullish,
            "breakout_type": breakout_type,
            "trend": trend,
            "channel_pos": round(channel_pos, 1),
            "market_snapshot_id": snapshot.market_snapshot_id,
            "candidate_snapshot_id": snapshot.candidate_snapshot_id,
            "snapshot_checksum": snapshot.checksum,
            "snapshot_schema_version": snapshot.schema_version,
            "technical_signal_schema_version": TECHNICAL_SIGNAL_SCHEMA_VERSION,
            "technical_model_version": model_version,
            "technical_parameter_version": parameter_version,
            "technical_parameters": dict(parameters),
            "technical_parameter_checksum": technical_parameter_checksum(parameters),
        }


_default: TechnicalSignalService | None = None


def get_technical_signal_service() -> TechnicalSignalService:
    global _default
    if _default is None:
        _default = TechnicalSignalService()
    return _default
