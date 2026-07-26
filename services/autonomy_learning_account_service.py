"""Controlled Autonomy learning account executed by the shared v19.8.0 engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from services.simulated_execution_service import SimulatedExecutionService
from services.strategy_account_service import StrategyAccountService

AUTONOMY_LEARNING_ACCOUNT_SERVICE_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _score(row: Mapping[str, Any]) -> float:
    return _f(row.get("autonomy_adjusted_investment_score", row.get("investment_score", row.get("final_score", row.get("score")))))


def _quality(row: Mapping[str, Any]) -> float:
    value = row.get("data_quality_score", row.get("data_quality", row.get("combined_data_quality")))
    if isinstance(value, Mapping):
        value = value.get("score", value.get("value"))
    return _f(value, 0.0)


def _risk(row: Mapping[str, Any]) -> float:
    return _f(row.get("risk_score", row.get("risk")), 100.0)


def _price(row: Mapping[str, Any]) -> float:
    return _f(row.get("price", row.get("current_price", row.get("last_price"))))


class AutonomyLearningAccountService:
    def __init__(self, accounts: StrategyAccountService | None = None, execution: SimulatedExecutionService | None = None):
        self.accounts = accounts or StrategyAccountService()
        self.execution = execution or SimulatedExecutionService(self.accounts.repositories, self.accounts)

    def policy(self) -> dict[str, Any]:
        account = self.accounts.get("autonomy_learning") or {}
        metadata = dict(account.get("metadata") or {})
        return {
            "minimum_score": _f(metadata.get("minimum_score"), 72.0),
            "minimum_data_quality": _f(metadata.get("minimum_data_quality"), 55.0),
            "maximum_risk_score": _f(metadata.get("maximum_risk_score"), 65.0),
            "maximum_position_pct": _f(metadata.get("maximum_position_pct"), 1.5),
            "reserve_cash_pct": _f(metadata.get("reserve_cash_pct"), 15.0),
            "maximum_open_positions": int(metadata.get("maximum_open_positions") or 20),
            "maximum_buys_per_cycle": int(metadata.get("maximum_buys_per_cycle") or 3),
            "stop_loss_pct": _f(metadata.get("stop_loss_pct"), 6.0),
            "take_profit_pct": _f(metadata.get("take_profit_pct"), 15.0),
            "score_exit_threshold": _f(metadata.get("score_exit_threshold"), 55.0),
            "hard_risk_gates_unchanged": True,
            "parameter_change_applied": False,
        }

    def update_policy(self, changes: Mapping[str, Any], *, approved_by: str = "user", reason: str = "") -> dict[str, Any]:
        """Apply an explicitly approved learning-policy revision with hard safety caps."""
        self.accounts.ensure_defaults()
        account = self.accounts.get("autonomy_learning") or {}
        current = self.policy()
        proposed = {**current, **dict(changes or {})}
        bounded = {
            "minimum_score": max(65.0, min(78.0, _f(proposed.get("minimum_score"), 72.0))),
            "minimum_data_quality": max(55.0, min(100.0, _f(proposed.get("minimum_data_quality"), 55.0))),
            "maximum_risk_score": max(0.0, min(65.0, _f(proposed.get("maximum_risk_score"), 65.0))),
            "maximum_position_pct": max(0.25, min(2.0, _f(proposed.get("maximum_position_pct"), 1.5))),
            "reserve_cash_pct": max(10.0, min(50.0, _f(proposed.get("reserve_cash_pct"), 15.0))),
            "maximum_open_positions": max(1, min(25, int(proposed.get("maximum_open_positions") or 20))),
            "maximum_buys_per_cycle": max(0, min(5, int(proposed.get("maximum_buys_per_cycle") or 3))),
            "stop_loss_pct": max(2.0, min(12.0, _f(proposed.get("stop_loss_pct"), 6.0))),
            "take_profit_pct": max(5.0, min(30.0, _f(proposed.get("take_profit_pct"), 15.0))),
            "score_exit_threshold": max(40.0, min(70.0, _f(proposed.get("score_exit_threshold"), 55.0))),
            "hard_risk_gates_unchanged": True,
            "parameter_change_applied": True,
        }
        metadata = dict(account.get("metadata") or {})
        history = list(metadata.get("policy_history") or [])
        history.insert(0, {
            "changed_at": _now(), "approved_by": str(approved_by or "user"), "reason": str(reason or ""),
            "before": current, "after": bounded, "rollback": current,
        })
        metadata.update(bounded)
        metadata["policy_history"] = history[:100]
        metadata["last_policy_change_approved"] = True
        metadata["main_strategy_unchanged"] = True
        account["metadata"] = metadata
        account["parameter_version"] = "learning-policy-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        account["updated_at"] = _now()
        saved = self.accounts.upsert(account)
        return {"account": saved, "policy": self.policy(), "before": current, "approved_by": approved_by, "reason": reason}

    def run_cycle(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        run_id: str,
        main_trades: Sequence[Mapping[str, Any]] | None = None,
        market_snapshot_id: str = "",
        maximum_buys_override: int | None = None,
    ) -> dict[str, Any]:
        self.accounts.ensure_defaults()
        account = self.accounts.get("autonomy_learning") or {}
        policy = self.policy()
        decisions: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        fills: list[dict[str, Any]] = []
        if str(account.get("status") or "").upper() != "ACTIVE":
            return {"run_id": run_id, "status": "PAUSED", "decisions": [], "orders": [], "fills": [], "policy": policy}

        candidate_map = {str(row.get("ticker") or "").upper(): dict(row) for row in candidates if str(row.get("ticker") or "").strip()}
        # Mark and evaluate exits first.
        for ticker, position in list((account.get("positions") or {}).items()):
            candidate = candidate_map.get(str(ticker).upper(), {})
            price = _price(candidate) or _f(position.get("last_price"), _f(position.get("average_price")))
            entry = _f(position.get("average_price"), price)
            score = _score(candidate) if candidate else _f(position.get("entry_score"), 100.0)
            reason = ""
            if price > 0 and entry > 0 and price <= entry * (1 - policy["stop_loss_pct"] / 100):
                reason = "Læringskonto stop-loss"
            elif price > 0 and entry > 0 and price >= entry * (1 + policy["take_profit_pct"] / 100):
                reason = "Læringskonto gevinstmål"
            elif candidate and score < policy["score_exit_threshold"]:
                reason = f"Læringsscore falt til {score:.1f}"
            if reason and price > 0:
                result = self.execution.execute_order(
                    account_id="autonomy_learning", run_id=run_id, ticker=ticker, side="SELL",
                    reference_price=price, quantity=_f(position.get("quantity")), reason=reason,
                    market_snapshot_id=market_snapshot_id,
                    candidate_snapshot_id=str(candidate.get("candidate_snapshot_id") or ""),
                    execution_authorized=True,
                    risk_context={"policy": policy, "score": score},
                    metadata={"account_role": "LEARNING", "source": "autonomy_learning_cycle"},
                )
                orders.append(result["order"])
                if result.get("fill"): fills.append(result["fill"])
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SELL" if result["ok"] else "SKIP", "reason": reason if result["ok"] else result["order"].get("rejection_reason"), "order_executed": bool(result["ok"]), "account_id": "autonomy_learning"})
            else:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Ingen læringsexit utløst", "score": score, "account_id": "autonomy_learning"})

        account = self.accounts.get("autonomy_learning") or account
        main_buys = [row for row in (main_trades or []) if str(row.get("action") or row.get("side") or "").upper() == "BUY"]
        buy_budget = int(maximum_buys_override if maximum_buys_override is not None else policy["maximum_buys_per_cycle"])
        # The learning account runs every cycle, but does not duplicate the same ticker.
        ranked = sorted((dict(row) for row in candidates), key=_score, reverse=True)
        buys = 0
        for candidate in ranked:
            ticker = str(candidate.get("ticker") or "").upper()
            if not ticker or buys >= buy_budget:
                break
            account = self.accounts.get("autonomy_learning") or account
            if ticker in (account.get("positions") or {}):
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Finnes allerede i læringskonto", "account_id": "autonomy_learning"})
                continue
            score = _score(candidate); quality = _quality(candidate); risk = _risk(candidate); price = _price(candidate)
            blocker = ""
            if quality < policy["minimum_data_quality"]:
                blocker = f"Datakvalitet {quality:.1f} under hard grense {policy['minimum_data_quality']:.1f}"
            elif risk > policy["maximum_risk_score"]:
                blocker = f"Risiko {risk:.1f} over hard grense {policy['maximum_risk_score']:.1f}"
            elif bool(candidate.get("technical_entry_wait")):
                blocker = str(candidate.get("technical_entry_wait_reason") or "Teknisk timing gir VENT")
            elif score < policy["minimum_score"]:
                blocker = f"Justert score {score:.1f} under læringsgrense {policy['minimum_score']:.1f}"
            elif price <= 0:
                blocker = "Mangler gyldig markedspris"
            elif len(account.get("positions") or {}) >= policy["maximum_open_positions"]:
                blocker = "Maks antall læringsposisjoner"
            if blocker:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "WAIT" if bool(candidate.get("technical_entry_wait")) else "SKIP", "reason": blocker, "score": score, "base_score": _f(candidate.get("autonomy_base_investment_score"), score), "data_quality": quality, "risk": risk, "account_id": "autonomy_learning", "order_intent_created": False, "order_executed": False, "technical_timing": candidate.get("technical_timing"), "technical_score_100": candidate.get("technical_score_100"), "technical_contribution_points": candidate.get("technical_contribution_points"), "technical_strategy_version_id": candidate.get("technical_strategy_version_id")})
                continue

            equity = self.accounts.equity(account)
            reserve = equity * policy["reserve_cash_pct"] / 100
            available = max(0.0, _f(account.get("cash")) - reserve)
            target = min(available, equity * policy["maximum_position_pct"] / 100)
            quantity = target / price if price > 0 else 0.0
            reason = f"Kontrollert læringskjøp: score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}"
            result = self.execution.execute_order(
                account_id="autonomy_learning", run_id=run_id, ticker=ticker, side="BUY",
                reference_price=price, quantity=quantity, reason=reason,
                market_snapshot_id=market_snapshot_id,
                candidate_snapshot_id=str(candidate.get("candidate_snapshot_id") or ""),
                execution_authorized=True,
                risk_context={"score": score, "base_score": _f(candidate.get("autonomy_base_investment_score"), score), "data_quality": quality, "risk": risk, "policy": policy, "technical_timing": candidate.get("technical_timing")},
                metadata={"account_role": "LEARNING", "source": "autonomy_learning_cycle", "main_strategy_buys": len(main_buys), "technical_strategy_version_id": candidate.get("technical_strategy_version_id"), "technical_contribution_points": candidate.get("technical_contribution_points")},
            )
            orders.append(result["order"])
            if result.get("fill"): fills.append(result["fill"])
            decisions.append({
                "timestamp": _now(), "run_id": run_id, "ticker": ticker,
                "action": "BUY" if result["ok"] else "SKIP",
                "reason": reason if result["ok"] else result["order"].get("rejection_reason"),
                "score": score, "base_score": _f(candidate.get("autonomy_base_investment_score"), score), "data_quality": quality, "risk": risk,
                "technical_timing": candidate.get("technical_timing"), "technical_score_100": candidate.get("technical_score_100"), "technical_contribution_points": candidate.get("technical_contribution_points"), "technical_strategy_version_id": candidate.get("technical_strategy_version_id"),
                "account_id": "autonomy_learning", "order_intent_created": True,
                "order_executed": bool(result["ok"]), "order_id": result["order"].get("order_id"),
            })
            buys += int(bool(result["ok"]))

        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "policy": policy,
            "decisions": decisions,
            "orders": orders,
            "fills": fills,
            "buy_count": sum(1 for row in fills if row.get("side") == "BUY"),
            "sell_count": sum(1 for row in fills if row.get("side") == "SELL"),
            "account_metrics": self.accounts.metrics("autonomy_learning"),
            "parameter_change_applied": False,
            "hard_risk_gates_unchanged": True,
            "service_version": AUTONOMY_LEARNING_ACCOUNT_SERVICE_VERSION,
        }


_default: AutonomyLearningAccountService | None = None


def get_autonomy_learning_account_service() -> AutonomyLearningAccountService:
    global _default
    if _default is None:
        _default = AutonomyLearningAccountService()
    return _default
