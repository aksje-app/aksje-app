"""Controlled Autonomy learning account executed by the shared v19.8.0 engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from services.simulated_execution_service import SimulatedExecutionService
from services.strategy_account_service import StrategyAccountService

AUTONOMY_LEARNING_ACCOUNT_SERVICE_VERSION = "2.1"
LEARNING_POLICY_PROFILE_VERSION = "2.0"
LEARNING_OUTCOME_HORIZONS = (1, 5, 10, 20, 60)


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
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for value in (
        row.get("price"), row.get("current_price"), row.get("last_price"),
        raw.get("price"), raw.get("current_price"), raw.get("last_price"), raw.get("regularMarketPrice"),
    ):
        price = _f(value)
        if price > 0:
            return price
    return 0.0


def _paper_signal(row: Mapping[str, Any]) -> dict[str, Any]:
    paper = dict(row.get("paper_engine_input") or {})
    decisions = [dict(item) for item in list(paper.get("technical_decisions") or []) if isinstance(item, Mapping)]
    actions = [str(item.get("action") or item.get("raw_decision") or "").upper() for item in decisions]
    action = "BUY" if any(value in {"BUY", "KJØP"} for value in actions) else "SELL" if any(value in {"SELL", "SALG"} for value in actions) else "NEUTRAL"
    return {
        "available": bool(decisions), "action": action,
        "confidence": max((_f(item.get("confidence")) for item in decisions), default=0.0),
        "source_run_id": paper.get("source_run_id") or paper.get("run_id"),
        "execution_authorized": False,
    }


def _critical_integrity_errors(row: Mapping[str, Any]) -> list[str]:
    errors = list(row.get("integrity_errors") or row.get("critical_integrity_errors") or [])
    if row.get("integrity_ok") is False or row.get("critical_integrity_error") is True:
        errors.append("Kritisk integritetskontroll feilet")
    return [str(value) for value in errors if str(value).strip()]


def _production_blockers(row: Mapping[str, Any], parameters: Mapping[str, Any] | None) -> list[str]:
    params = dict(parameters or {})
    score = _score(row); risk = _risk(row); quality = _quality(row)
    blockers: list[str] = []
    if str(row.get("autonomy_outcome_code") or "").upper() != "KJØPSKANDIDAT": blockers.append("Autonomiutfallet er ikke Kjøpskandidat")
    if str(row.get("portfolio_action") or "").upper() not in {"BUY", "KJØP"}: blockers.append("Porteføljelaget ga ikke KJØP")
    if row.get("valid_for_decision") is not True: blockers.append("Markedsdata ikke beslutningsgyldige")
    if row.get("evidence_valid_for_decision") is not True: blockers.append("Evidens ikke beslutningsgyldig")
    if score < _f(params.get("minimum_investment_score"), 78.0): blockers.append("Score under produksjonsgrensen")
    if risk > _f(params.get("maximum_risk_score"), 65.0): blockers.append("Risiko over produksjonsgrensen")
    if quality < _f(params.get("minimum_data_quality"), 55.0): blockers.append("Datakvalitet under produksjonsgrensen")
    return list(dict.fromkeys(blockers))


class AutonomyLearningAccountService:
    def __init__(self, accounts: StrategyAccountService | None = None, execution: SimulatedExecutionService | None = None):
        self.accounts = accounts or StrategyAccountService()
        self.execution = execution or SimulatedExecutionService(self.accounts.repositories, self.accounts)

    def policy(self) -> dict[str, Any]:
        account = self.accounts.get("autonomy_learning") or {}
        metadata = dict(account.get("metadata") or {})
        return {
            "minimum_score": _f(metadata.get("minimum_score"), 63.0),
            "minimum_data_quality": _f(metadata.get("minimum_data_quality"), 55.0),
            "maximum_risk_score": _f(metadata.get("maximum_risk_score"), 75.0),
            "notional_value": _f(metadata.get("notional_value"), 15000.0),
            "maximum_position_pct": _f(metadata.get("maximum_position_pct"), 1.5),
            "reserve_cash_pct": _f(metadata.get("reserve_cash_pct"), 15.0),
            "maximum_open_positions": int(metadata.get("maximum_open_positions") or 20),
            "maximum_buys_per_cycle": int(metadata.get("maximum_buys_per_cycle") or 3),
            "stop_loss_pct": _f(metadata.get("stop_loss_pct"), 6.0),
            "trailing_stop_pct": _f(metadata.get("trailing_stop_pct"), 10.0),
            "take_profit_pct": _f(metadata.get("take_profit_pct"), 15.0),
            "score_exit_threshold": _f(metadata.get("score_exit_threshold"), 55.0),
            "horizon_days": int(metadata.get("horizon_days") or 60),
            "profile_version": str(metadata.get("learning_policy_profile_version") or "1.0"),
            "hard_risk_gates_unchanged": False,
            "hard_production_gates_unchanged": True,
            "parameter_change_applied": False,
        }

    def update_policy(self, changes: Mapping[str, Any], *, approved_by: str = "user", reason: str = "") -> dict[str, Any]:
        """Apply an explicitly approved learning-policy revision with hard safety caps."""
        self.accounts.ensure_defaults()
        account = self.accounts.get("autonomy_learning") or {}
        current = self.policy()
        proposed = {**current, **dict(changes or {})}
        bounded = {
            "minimum_score": max(60.0, min(65.0, _f(proposed.get("minimum_score"), 63.0))),
            "minimum_data_quality": max(55.0, min(100.0, _f(proposed.get("minimum_data_quality"), 55.0))),
            "maximum_risk_score": max(0.0, min(75.0, _f(proposed.get("maximum_risk_score"), 75.0))),
            "notional_value": max(100.0, min(15000.0, _f(proposed.get("notional_value"), 15000.0))),
            "maximum_position_pct": max(0.25, min(2.0, _f(proposed.get("maximum_position_pct"), 1.5))),
            "reserve_cash_pct": max(10.0, min(50.0, _f(proposed.get("reserve_cash_pct"), 15.0))),
            "maximum_open_positions": max(1, min(25, int(proposed.get("maximum_open_positions") or 20))),
            "maximum_buys_per_cycle": max(0, min(5, int(proposed.get("maximum_buys_per_cycle") or 3))),
            "stop_loss_pct": max(2.0, min(12.0, _f(proposed.get("stop_loss_pct"), 6.0))),
            "trailing_stop_pct": max(2.0, min(20.0, _f(proposed.get("trailing_stop_pct"), 10.0))),
            "take_profit_pct": max(5.0, min(30.0, _f(proposed.get("take_profit_pct"), 15.0))),
            "score_exit_threshold": max(40.0, min(70.0, _f(proposed.get("score_exit_threshold"), 55.0))),
            "horizon_days": max(1, min(365, int(proposed.get("horizon_days") or 60))),
            "learning_policy_profile_version": LEARNING_POLICY_PROFILE_VERSION,
            "hard_risk_gates_unchanged": False,
            "hard_production_gates_unchanged": True,
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

    def ensure_approved_profile(self) -> dict[str, Any]:
        """Apply the user-approved v2 learning profile once; production is untouched."""
        current = self.policy()
        if current.get("profile_version") == LEARNING_POLICY_PROFILE_VERSION:
            return current
        return self.update_policy({
            "minimum_score": 63.0, "maximum_risk_score": 75.0,
            "notional_value": 15000.0, "maximum_buys_per_cycle": 3,
            "trailing_stop_pct": 10.0, "horizon_days": 60,
        }, approved_by="USER_GO_2026-08-08", reason="Aktiver kontrollert læring før produksjonsinnstramming")["policy"]

    def run_cycle(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        run_id: str,
        main_trades: Sequence[Mapping[str, Any]] | None = None,
        market_snapshot_id: str = "",
        maximum_buys_override: int | None = None,
        production_parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.accounts.ensure_defaults()
        account = self.accounts.get("autonomy_learning") or {}
        policy = self.ensure_approved_profile()
        account = self.accounts.get("autonomy_learning") or account
        account_metadata = dict(account.get("metadata") or {})
        processed_run_ids = [str(value) for value in list(account_metadata.get("processed_run_ids") or [])]
        if str(run_id) in processed_run_ids:
            return {
                "run_id": run_id, "status": "ALREADY_PROCESSED", "idempotent_replay": True,
                "policy": policy, "decisions": [], "orders": [], "fills": [],
                "buy_count": 0, "sell_count": 0,
                "account_metrics": self.accounts.metrics("autonomy_learning"),
                "parameter_change_applied": False,
                "hard_production_gates_unchanged": True,
                "service_version": AUTONOMY_LEARNING_ACCOUNT_SERVICE_VERSION,
            }
        decisions: list[dict[str, Any]] = []
        orders: list[dict[str, Any]] = []
        fills: list[dict[str, Any]] = []
        exited_this_cycle: set[str] = set()
        if str(account.get("status") or "").upper() != "ACTIVE":
            return {"run_id": run_id, "status": "PAUSED", "decisions": [], "orders": [], "fills": [], "policy": policy}

        candidate_map = {str(row.get("ticker") or "").upper(): dict(row) for row in candidates if str(row.get("ticker") or "").strip()}
        # Mark and evaluate exits first.
        for ticker, position in list((account.get("positions") or {}).items()):
            candidate = candidate_map.get(str(ticker).upper(), {})
            price = _price(candidate) or _f(position.get("last_price"), _f(position.get("average_price")))
            entry = _f(position.get("average_price"), price)
            score = _score(candidate) if candidate else _f(position.get("entry_score"), 100.0)
            paper = _paper_signal(candidate) if candidate else {"action": "NEUTRAL"}
            position["last_price"] = price
            position["highest_price"] = max(_f(position.get("highest_price"), price), price)
            metadata = dict(position.get("metadata") or {})
            market_date = str(candidate.get("market_date") or candidate.get("price_date") or candidate.get("as_of_date") or _now()[:10])[:10]
            dates = list(metadata.get("evaluation_dates") or [])
            if candidate and market_date not in dates: dates.append(market_date)
            metadata["evaluation_dates"] = dates[-120:]
            metadata["observation_days"] = len(dates)
            measurements = list(metadata.get("outcome_measurements") or [])
            measured = {int(item.get("horizon_days") or 0) for item in measurements if isinstance(item, Mapping)}
            for horizon in LEARNING_OUTCOME_HORIZONS:
                if len(dates) >= horizon and horizon not in measured:
                    measurements.append({"horizon_days": horizon, "measured_at": _now(), "market_date": market_date, "price": round(price, 4), "return_pct": round((price / entry - 1) * 100, 4) if entry else 0.0, "score": round(score, 2)})
            metadata["outcome_measurements"] = measurements
            position["metadata"] = metadata
            account.setdefault("positions", {})[ticker] = position
            self.accounts.upsert(account)
            reason = ""
            if price > 0 and entry > 0 and price <= entry * (1 - policy["stop_loss_pct"] / 100):
                reason = "Læringskonto stop-loss"
            elif price > 0 and price <= _f(position.get("highest_price"), price) * (1 - policy["trailing_stop_pct"] / 100):
                reason = "Læringskonto trailing stop"
            elif price > 0 and entry > 0 and price >= entry * (1 + policy["take_profit_pct"] / 100):
                reason = "Læringskonto gevinstmål"
            elif candidate and score < policy["score_exit_threshold"]:
                reason = f"Læringsscore falt til {score:.1f}"
            elif candidate and paper.get("action") == "SELL":
                reason = "Paper-motoren ga salgssignal"
            elif len(dates) >= policy["horizon_days"]:
                reason = f"Læringshorisont {policy['horizon_days']} observasjonsdager fullført"
            if reason and price > 0:
                result = self.execution.execute_order(
                    account_id="autonomy_learning", run_id=run_id, ticker=ticker, side="SELL",
                    reference_price=price, quantity=_f(position.get("quantity")), reason=reason,
                    market_snapshot_id=market_snapshot_id,
                    candidate_snapshot_id=str(candidate.get("candidate_snapshot_id") or ""),
                    execution_authorized=True,
                    risk_context={"policy": policy, "score": score},
                    metadata={
                        "account_role": "LEARNING", "source": "autonomy_learning_cycle",
                        "observation_days": len(dates),
                        "outcome_measurements": measurements,
                        "production_blockers_at_entry": metadata.get("production_blockers_at_entry", []),
                        "paper_signal_at_exit": paper,
                    },
                )
                orders.append(result["order"])
                if result.get("fill"): fills.append(result["fill"])
                if result.get("account"): account = dict(result["account"])
                if result.get("ok"): exited_this_cycle.add(str(ticker).upper())
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SELL" if result["ok"] else "SKIP", "reason": reason if result["ok"] else result["order"].get("rejection_reason"), "order_executed": bool(result["ok"]), "account_id": "autonomy_learning"})
            else:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Ingen læringsexit utløst", "score": score, "account_id": "autonomy_learning"})

        self.accounts.upsert(account)
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
            if ticker in exited_this_cycle:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Solgt tidligere i samme læringssyklus", "account_id": "autonomy_learning"})
                continue
            account = self.accounts.get("autonomy_learning") or account
            if ticker in (account.get("positions") or {}):
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Finnes allerede i læringskonto", "account_id": "autonomy_learning"})
                continue
            score = _score(candidate); quality = _quality(candidate); risk = _risk(candidate); price = _price(candidate)
            paper = _paper_signal(candidate)
            production_blockers = _production_blockers(candidate, production_parameters)
            blocker = ""
            integrity_errors = _critical_integrity_errors(candidate)
            if integrity_errors:
                blocker = "Kritisk integritetsfeil: " + "; ".join(integrity_errors)
            elif candidate.get("valid_for_decision") is not True:
                blocker = "Markedsdata er ikke beslutningsgyldige"
            elif quality < policy["minimum_data_quality"]:
                blocker = f"Datakvalitet {quality:.1f} under hard grense {policy['minimum_data_quality']:.1f}"
            elif risk > policy["maximum_risk_score"]:
                blocker = f"Risiko {risk:.1f} over hard grense {policy['maximum_risk_score']:.1f}"
            elif bool(candidate.get("technical_entry_wait")) and paper["action"] != "BUY":
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
            target = min(available, policy["notional_value"])
            quantity = target / price if price > 0 else 0.0
            reason = f"Kontrollert læringskjøp: score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}"
            result = self.execution.execute_order(
                account_id="autonomy_learning", run_id=run_id, ticker=ticker, side="BUY",
                reference_price=price, quantity=quantity, reason=reason,
                market_snapshot_id=market_snapshot_id,
                candidate_snapshot_id=str(candidate.get("candidate_snapshot_id") or ""),
                execution_authorized=True,
                risk_context={"score": score, "base_score": _f(candidate.get("autonomy_base_investment_score"), score), "data_quality": quality, "risk": risk, "policy": policy, "technical_timing": candidate.get("technical_timing"), "production_blockers_at_entry": production_blockers},
                metadata={"account_role": "LEARNING", "source": "autonomy_learning_cycle", "main_strategy_buys": len(main_buys), "technical_strategy_version_id": candidate.get("technical_strategy_version_id"), "technical_contribution_points": candidate.get("technical_contribution_points"), "paper_signal": paper, "production_blockers_at_entry": production_blockers, "evidence_valid_at_entry": candidate.get("evidence_valid_for_decision") is True, "evaluation_dates": [], "observation_days": 0, "outcome_measurements": []},
            )
            orders.append(result["order"])
            if result.get("fill"): fills.append(result["fill"])
            decisions.append({
                "timestamp": _now(), "run_id": run_id, "ticker": ticker,
                "action": "BUY" if result["ok"] else "SKIP",
                "reason": reason if result["ok"] else result["order"].get("rejection_reason"),
                "score": score, "base_score": _f(candidate.get("autonomy_base_investment_score"), score), "data_quality": quality, "risk": risk,
                "technical_timing": candidate.get("technical_timing"), "technical_score_100": candidate.get("technical_score_100"), "technical_contribution_points": candidate.get("technical_contribution_points"), "technical_strategy_version_id": candidate.get("technical_strategy_version_id"),
                "paper_signal": paper, "production_blockers_at_entry": production_blockers,
                "account_id": "autonomy_learning", "order_intent_created": True,
                "order_executed": bool(result["ok"]), "order_id": result["order"].get("order_id"),
            })
            buys += int(bool(result["ok"]))

        account = self.accounts.get("autonomy_learning") or account
        account_metadata = dict(account.get("metadata") or {})
        completed_ids = [str(value) for value in list(account_metadata.get("processed_run_ids") or []) if str(value) != str(run_id)]
        completed_ids.append(str(run_id))
        account_metadata["processed_run_ids"] = completed_ids[-250:]
        account_metadata["last_completed_learning_cycle"] = {"run_id": str(run_id), "completed_at": _now(), "buy_count": sum(1 for row in fills if row.get("side") == "BUY"), "sell_count": sum(1 for row in fills if row.get("side") == "SELL")}
        account["metadata"] = account_metadata
        account["last_run_id"] = str(run_id)
        account["updated_at"] = _now()
        self.accounts.upsert(account)
        final_metrics = self.accounts.metrics("autonomy_learning")
        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "policy": policy,
            "decisions": decisions,
            "orders": orders,
            "fills": fills,
            "buy_count": sum(1 for row in fills if row.get("side") == "BUY"),
            "sell_count": sum(1 for row in fills if row.get("side") == "SELL"),
            "account_metrics": final_metrics,
            "parameter_change_applied": False,
            "hard_risk_gates_unchanged": False,
            "hard_production_gates_unchanged": True,
            "service_version": AUTONOMY_LEARNING_ACCOUNT_SERVICE_VERSION,
        }


_default: AutonomyLearningAccountService | None = None


def get_autonomy_learning_account_service() -> AutonomyLearningAccountService:
    global _default
    if _default is None:
        _default = AutonomyLearningAccountService()
    return _default
