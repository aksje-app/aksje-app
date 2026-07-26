"""Controlled technical contribution to Autonomy entry decisions for v19.9.0.

The service consumes the read-only production technical benchmark decision from
exactly the same MarketSnapshot as Autonomy.  It never calls execution and it
cannot weaken hard data-quality, risk, cash, sector or position gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from repositories.application import RepositoryRegistry, get_repository_registry

AUTONOMY_TECHNICAL_CONTRIBUTION_SERVICE_VERSION = "1.0"
AUTONOMY_TECHNICAL_POLICY_VERSION = "v19.9.0-default-1"
_POLICY_ID = "autonomy_technical_contribution_policy"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _base_score(row: Mapping[str, Any]) -> float:
    for key in ("autonomy_base_investment_score", "investment_score", "final_score", "score", "combined_score", "decision_score"):
        if row.get(key) is not None:
            return _clamp(_f(row.get(key)), 0.0, 100.0)
    return 0.0


def _technical_score_100(decision: Mapping[str, Any]) -> float:
    score = _f(decision.get("score"), 0.0)
    return _clamp(score * 10.0 if score <= 10.0 else score, 0.0, 100.0)


def _technical_decisions(parallel_run: Mapping[str, Any] | None, bound_version_id: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for raw in list((parallel_run or {}).get("decisions") or []):
        row = dict(raw or {})
        if str(row.get("strategy_family") or "").lower() != "technical":
            continue
        if str(row.get("strategy_status") or "").upper() != "PRODUCTION":
            continue
        if str(row.get("strategy_version_id") or "") != str(bound_version_id or ""):
            continue
        if str(row.get("action") or "").upper() == "ERROR" or row.get("error"):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            output[ticker] = row
    return output


class AutonomyTechnicalContributionService:
    def __init__(self, repositories: RepositoryRegistry | None = None):
        self.repositories = repositories or get_repository_registry()
        self.configurations = self.repositories.configurations
        self.events = self.repositories.strategy_events

    @staticmethod
    def default_policy() -> dict[str, Any]:
        return {
            "config_id": _POLICY_ID,
            "policy_version": AUTONOMY_TECHNICAL_POLICY_VERSION,
            "service_version": AUTONOMY_TECHNICAL_CONTRIBUTION_SERVICE_VERSION,
            "enabled": True,
            "scope": "ENTRY_ONLY",
            "execution_scope": "PAPER_ONLY",
            "weight_pct": 15.0,
            "neutral_technical_score": 50.0,
            "maximum_positive_points": 4.0,
            "maximum_negative_points": 6.0,
            "minimum_base_score_floor": 74.0,
            "wait_below_technical_score": 35.0,
            "wait_minimum_confidence": 60.0,
            "production_technical_only": True,
            "bound_technical_strategy_version_id": "technical_benchmark@legacy-1.0.0",
            "hard_gates_unchanged": True,
            "automatic_policy_changes": False,
            "updated_at": _now(),
            "approved_by": "release-v19.9.0",
            "approval_reason": "Kontrollert standardprofil for paper Autonomi",
            "history": [],
        }

    def _normalise(self, value: Mapping[str, Any] | None) -> dict[str, Any]:
        row = {**self.default_policy(), **dict(value or {})}
        row.update({
            "config_id": _POLICY_ID,
            "policy_version": str(row.get("policy_version") or AUTONOMY_TECHNICAL_POLICY_VERSION),
            "service_version": AUTONOMY_TECHNICAL_CONTRIBUTION_SERVICE_VERSION,
            "enabled": bool(row.get("enabled", True)),
            "scope": "ENTRY_ONLY",
            "execution_scope": "PAPER_ONLY",
            "weight_pct": _clamp(_f(row.get("weight_pct"), 15.0), 0.0, 20.0),
            "neutral_technical_score": 50.0,
            "maximum_positive_points": _clamp(_f(row.get("maximum_positive_points"), 4.0), 0.0, 5.0),
            "maximum_negative_points": _clamp(_f(row.get("maximum_negative_points"), 6.0), 0.0, 8.0),
            "minimum_base_score_floor": _clamp(_f(row.get("minimum_base_score_floor"), 74.0), 70.0, 78.0),
            "wait_below_technical_score": _clamp(_f(row.get("wait_below_technical_score"), 35.0), 20.0, 45.0),
            "wait_minimum_confidence": _clamp(_f(row.get("wait_minimum_confidence"), 60.0), 50.0, 90.0),
            "production_technical_only": True,
            "bound_technical_strategy_version_id": str(row.get("bound_technical_strategy_version_id") or "technical_benchmark@legacy-1.0.0"),
            "hard_gates_unchanged": True,
            "automatic_policy_changes": False,
        })
        row["history"] = list(row.get("history") or [])[:100]
        return row

    def policy(self) -> dict[str, Any]:
        existing = self.configurations.get(_POLICY_ID)
        policy = self._normalise(existing)
        if existing is None:
            self.configurations.upsert(policy)
        return policy

    def update_policy(self, changes: Mapping[str, Any], *, approved_by: str, reason: str) -> dict[str, Any]:
        if not str(approved_by or "").strip():
            raise ValueError("approved_by er påkrevd")
        if not str(reason or "").strip():
            raise ValueError("Begrunnelse er påkrevd")
        before = self.policy()
        proposed = self._normalise({**before, **dict(changes or {})})
        history = list(before.get("history") or [])
        history.insert(0, {
            "changed_at": _now(),
            "approved_by": str(approved_by),
            "reason": str(reason),
            "before": {k: v for k, v in before.items() if k != "history"},
            "after": {k: v for k, v in proposed.items() if k != "history"},
            "rollback": {k: v for k, v in before.items() if k != "history"},
        })
        proposed.update({
            "history": history[:100],
            "updated_at": _now(),
            "approved_by": str(approved_by),
            "approval_reason": str(reason),
            "policy_version": "technical-contribution-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        })
        self.configurations.upsert(proposed)
        self.events.append({
            "timestamp": _now(),
            "event": "AUTONOMY_TECHNICAL_POLICY_UPDATED",
            "approved_by": str(approved_by),
            "reason": str(reason),
            "before": before,
            "after": proposed,
            "hard_gates_unchanged": True,
        })
        return {"before": before, "policy": self.policy(), "rollback": before, "parameter_change_applied": True}

    def apply(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        parallel_strategy_run: Mapping[str, Any] | None,
        run_id: str,
        minimum_investment_score: float,
    ) -> dict[str, Any]:
        policy = self.policy()
        technical = _technical_decisions(parallel_strategy_run, str(policy.get("bound_technical_strategy_version_id") or ""))
        output: list[dict[str, Any]] = []
        contributions: list[dict[str, Any]] = []
        for raw in candidates or []:
            row = dict(raw or {})
            ticker = str(row.get("ticker") or "").upper()
            base = _base_score(row)
            decision = technical.get(ticker)
            enriched = dict(row)
            enriched["autonomy_base_investment_score"] = round(base, 4)
            enriched["autonomy_adjusted_investment_score"] = round(base, 4)
            enriched["technical_contribution_applied"] = False
            enriched["technical_entry_wait"] = False
            enriched["technical_timing"] = "UNAVAILABLE"
            enriched["technical_contribution_policy_version"] = policy["policy_version"]
            enriched["technical_contribution_service_version"] = AUTONOMY_TECHNICAL_CONTRIBUTION_SERVICE_VERSION

            if not policy["enabled"] or decision is None:
                enriched["technical_contribution_reason"] = "Teknisk bidrag deaktivert" if not policy["enabled"] else "Mangler teknisk produksjonsbeslutning på samme snapshot"
                output.append(enriched)
                contributions.append({
                    "run_id": run_id, "ticker": ticker, "base_score": base, "adjusted_score": base,
                    "applied": False, "reason": enriched["technical_contribution_reason"],
                })
                continue

            tech_score = _technical_score_100(decision)
            tech_confidence = _clamp(_f(decision.get("confidence"), 0.0), 0.0, 100.0)
            action = str(decision.get("action") or decision.get("raw_decision") or "HOLD").upper()
            raw_delta = (tech_score - policy["neutral_technical_score"]) * policy["weight_pct"] / 100.0
            if raw_delta >= 0:
                delta = min(raw_delta, policy["maximum_positive_points"])
                if base < policy["minimum_base_score_floor"]:
                    delta = 0.0
                    positive_gate = "BASE_SCORE_FLOOR"
                else:
                    positive_gate = "PASSED"
            else:
                delta = max(raw_delta, -policy["maximum_negative_points"])
                positive_gate = "NOT_APPLICABLE"
            adjusted = _clamp(base + delta, 0.0, 100.0)
            wait = bool(
                action in {"SELL", "AVOID"}
                or (tech_confidence >= policy["wait_minimum_confidence"] and tech_score <= policy["wait_below_technical_score"])
            )
            timing = "WAIT" if wait else ("GOOD" if action == "BUY" and tech_score >= 60.0 else "NEUTRAL")
            technical_result = dict((decision.get("metadata") or {}).get("technical_result") or {})
            reason = (
                f"Teknisk produksjonsbenchmark {decision.get('strategy_version_id') or '-'}: "
                f"{action}, {tech_score:.1f}/100, confidence {tech_confidence:.1f}; bidrag {delta:+.2f} poeng"
            )
            enriched.update({
                "autonomy_adjusted_investment_score": round(adjusted, 4),
                "technical_contribution_points": round(delta, 4),
                "technical_contribution_applied": True,
                "technical_contribution_reason": reason,
                "technical_score_100": round(tech_score, 4),
                "technical_signal_action": action,
                "technical_signal_raw_decision": str(decision.get("raw_decision") or ""),
                "technical_signal_confidence": round(tech_confidence, 4),
                "technical_timing": timing,
                "technical_entry_wait": wait,
                "technical_entry_wait_reason": reason if wait else "",
                "technical_strategy_version_id": str(decision.get("strategy_version_id") or ""),
                "technical_strategy_version": str(decision.get("strategy_version") or ""),
                "technical_model_version": str(technical_result.get("technical_model_version") or ""),
                "technical_parameter_version": str(technical_result.get("technical_parameter_version") or ""),
                "technical_candidate_snapshot_id": str(decision.get("candidate_snapshot_id") or ""),
                "technical_market_snapshot_id": str(decision.get("market_snapshot_id") or ""),
                "technical_positive_gate": positive_gate,
                "technical_hard_gates_unchanged": True,
                "technical_can_authorize_execution": False,
            })
            output.append(enriched)
            contributions.append({
                "run_id": run_id,
                "ticker": ticker,
                "base_score": round(base, 4),
                "adjusted_score": round(adjusted, 4),
                "technical_score_100": round(tech_score, 4),
                "technical_confidence": round(tech_confidence, 4),
                "technical_action": action,
                "contribution_points": round(delta, 4),
                "timing": timing,
                "entry_wait": wait,
                "crossed_buy_threshold": bool(base < minimum_investment_score <= adjusted),
                "strategy_version_id": str(decision.get("strategy_version_id") or ""),
                "candidate_snapshot_id": str(decision.get("candidate_snapshot_id") or ""),
                "market_snapshot_id": str(decision.get("market_snapshot_id") or ""),
                "applied": True,
            })

        summary = {
            "run_id": run_id,
            "policy": policy,
            "candidate_count": len(output),
            "applied_count": sum(1 for row in contributions if row.get("applied")),
            "wait_count": sum(1 for row in contributions if row.get("entry_wait")),
            "positive_count": sum(1 for row in contributions if _f(row.get("contribution_points")) > 0),
            "negative_count": sum(1 for row in contributions if _f(row.get("contribution_points")) < 0),
            "threshold_crossings": sum(1 for row in contributions if row.get("crossed_buy_threshold")),
            "production_technical_only": True,
            "bound_technical_strategy_version_id": policy.get("bound_technical_strategy_version_id"),
            "hard_gates_unchanged": True,
            "execution_authorized": False,
            "contributions": contributions,
            "service_version": AUTONOMY_TECHNICAL_CONTRIBUTION_SERVICE_VERSION,
        }
        self.events.append({"timestamp": _now(), "event": "AUTONOMY_TECHNICAL_CONTRIBUTION_APPLIED", **summary})
        return {"candidates": output, "summary": summary, "policy": policy}


_default: AutonomyTechnicalContributionService | None = None


def get_autonomy_technical_contribution_service() -> AutonomyTechnicalContributionService:
    global _default
    if _default is None:
        _default = AutonomyTechnicalContributionService()
    return _default
