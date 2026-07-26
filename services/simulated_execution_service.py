"""Unified simulated order and portfolio engine for v19.8.0."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping

from domain.strategy_account import (
    AccountStatus,
    OrderIntent,
    OrderSide,
    OrderStatus,
    SimulatedFill,
    build_fill_id,
    build_order_id,
    validate_order_intent,
)
from repositories.application import RepositoryRegistry, get_repository_registry
from services.strategy_account_service import StrategyAccountService

SIMULATED_EXECUTION_SERVICE_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


class SimulatedExecutionService:
    def __init__(self, repositories: RepositoryRegistry | None = None, accounts: StrategyAccountService | None = None):
        self.repositories = repositories or get_repository_registry()
        self.accounts = accounts or StrategyAccountService(self.repositories)
        self.orders = self.repositories.strategy_orders
        self.fills = self.repositories.strategy_fills

    def create_intent(
        self,
        *,
        account_id: str,
        run_id: str,
        ticker: str,
        side: str,
        reference_price: float,
        quantity: float = 0.0,
        notional: float = 0.0,
        reason: str = "",
        market_snapshot_id: str = "",
        candidate_snapshot_id: str = "",
        execution_authorized: bool = False,
        risk_context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        account = self.accounts.get(account_id)
        if not account:
            raise ValueError(f"Ukjent strategikonto: {account_id}")
        intent = OrderIntent(
            order_id=build_order_id(account_id=account_id, run_id=run_id, ticker=ticker, side=side),
            account_id=account_id,
            strategy_family=str(account.get("strategy_family") or ""),
            strategy_id=str(account.get("strategy_id") or ""),
            strategy_version_id=str(account.get("strategy_version_id") or ""),
            run_id=run_id,
            ticker=str(ticker).upper(),
            side=str(side).upper(),
            requested_quantity=max(0.0, _f(quantity)),
            requested_notional=max(0.0, _f(notional)),
            reference_price=_f(reference_price),
            reason=reason,
            market_snapshot_id=market_snapshot_id,
            candidate_snapshot_id=candidate_snapshot_id,
            execution_authorized=bool(execution_authorized),
            risk_context=dict(risk_context or {}),
            metadata={**dict(metadata or {}), "service_version": SIMULATED_EXECUTION_SERVICE_VERSION},
        ).to_dict()
        check = validate_order_intent(intent)
        if not check["ok"]:
            intent["status"] = OrderStatus.REJECTED.value
            intent["rejection_code"] = "INVALID_ORDER"
            intent["rejection_reason"] = "; ".join(check["errors"])
        self.orders.upsert(intent)
        return intent

    def _reject(self, intent: Mapping[str, Any], code: str, reason: str) -> dict[str, Any]:
        row = dict(intent)
        row["status"] = OrderStatus.REJECTED.value
        row["rejection_code"] = code
        row["rejection_reason"] = reason
        row["completed_at"] = _now()
        self.orders.upsert(row)
        return {"ok": False, "order": row, "fill": None, "account": self.accounts.get(str(row.get("account_id") or ""))}

    def execute(
        self,
        intent: Mapping[str, Any],
        *,
        fee_pct: float = 0.0,
        slippage_bps: float = 0.0,
        allow_fractional: bool = True,
        minimum_order_value: float = 100.0,
    ) -> dict[str, Any]:
        row = dict(intent or {})
        account_id = str(row.get("account_id") or "")
        account = self.accounts.get(account_id)
        if not account:
            return self._reject(row, "ACCOUNT_NOT_FOUND", "Strategikontoen finnes ikke")
        if str(account.get("status") or "").upper() != AccountStatus.ACTIVE.value:
            return self._reject(row, "ACCOUNT_NOT_ACTIVE", f"Kontostatus er {account.get('status')}")
        if not bool(row.get("execution_authorized")):
            return self._reject(row, "EXECUTION_NOT_AUTHORIZED", "Ordreintensjonen er read-only")
        if str(account.get("execution_mode") or "").upper() != "PAPER":
            return self._reject(row, "EXECUTION_MODE_BLOCKED", "Kun PAPER-kontoer kan utføre simulerte ordre")
        if str(row.get("status") or "").upper() == OrderStatus.REJECTED.value:
            return {"ok": False, "order": row, "fill": None, "account": account}

        side = str(row.get("side") or "").upper()
        ticker = str(row.get("ticker") or "").upper()
        reference = _f(row.get("reference_price"))
        if reference <= 0:
            return self._reject(row, "INVALID_PRICE", "Referansepris må være positiv")
        slip = max(0.0, _f(slippage_bps)) / 10000.0
        fill_price = reference * (1 + slip if side == OrderSide.BUY.value else 1 - slip)
        quantity = _f(row.get("requested_quantity"))
        if quantity <= 0:
            quantity = _f(row.get("requested_notional")) / fill_price if fill_price > 0 else 0.0
        quantity = quantity if allow_fractional else math.floor(quantity)
        quantity = math.floor(quantity * 100000000) / 100000000
        if quantity <= 0:
            return self._reject(row, "INVALID_QUANTITY", "Beregnet antall er null")

        positions = {str(k).upper(): dict(v) for k, v in (account.get("positions") or {}).items()}
        fee_rate = max(0.0, _f(fee_pct)) / 100.0
        gross = quantity * fill_price
        fee = gross * fee_rate
        slippage_value = abs(fill_price - reference) * quantity
        realized_pnl = 0.0

        if side == OrderSide.BUY.value:
            total_cost = gross + fee
            if total_cost < minimum_order_value:
                return self._reject(row, "MINIMUM_ORDER_VALUE", f"Ordreverdi {total_cost:.2f} er under minimum {minimum_order_value:.2f}")
            cash = _f(account.get("cash"))
            if total_cost > cash + 0.01:
                return self._reject(row, "INSUFFICIENT_CASH", f"Behov {total_cost:.2f}, tilgjengelig {cash:.2f}")
            old = positions.get(ticker, {})
            old_qty = _f(old.get("quantity"))
            old_avg = _f(old.get("average_price"), fill_price)
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_avg) + gross + fee) / new_qty if new_qty else fill_price
            positions[ticker] = {
                **old,
                "ticker": ticker,
                "quantity": new_qty,
                "average_price": new_avg,
                "last_price": fill_price,
                "opened_at": old.get("opened_at") or _now(),
                "updated_at": _now(),
                "source_order_id": row.get("order_id"),
                "strategy_version_id": row.get("strategy_version_id"),
                "market_snapshot_id": row.get("market_snapshot_id"),
                "candidate_snapshot_id": row.get("candidate_snapshot_id"),
                "metadata": dict(row.get("metadata") or {}),
            }
            account["cash"] = round(cash - total_cost, 8)
        elif side == OrderSide.SELL.value:
            old = positions.get(ticker)
            if not old:
                return self._reject(row, "POSITION_NOT_FOUND", "Kan ikke selge en posisjon som ikke finnes")
            held = _f(old.get("quantity"))
            if quantity > held + 1e-8:
                return self._reject(row, "INSUFFICIENT_POSITION", f"Forsøkte å selge {quantity}, eier {held}")
            proceeds = gross - fee
            realized_pnl = quantity * (fill_price - _f(old.get("average_price"))) - fee
            remaining = held - quantity
            if remaining <= 1e-8:
                del positions[ticker]
            else:
                old["quantity"] = remaining
                old["last_price"] = fill_price
                old["updated_at"] = _now()
                positions[ticker] = old
            account["cash"] = round(_f(account.get("cash")) + proceeds, 8)
            account["realized_pnl"] = round(_f(account.get("realized_pnl")) + realized_pnl, 8)
        else:
            return self._reject(row, "INVALID_SIDE", f"Ukjent ordreside {side}")

        account["positions"] = positions
        account["fees_paid"] = round(_f(account.get("fees_paid")) + fee, 8)
        account["slippage_paid"] = round(_f(account.get("slippage_paid")) + slippage_value, 8)
        account["last_run_id"] = str(row.get("run_id") or "")
        account["updated_at"] = _now()
        saved_account = self.accounts.upsert(account)

        fill = SimulatedFill(
            fill_id=build_fill_id(str(row.get("order_id") or "")),
            order_id=str(row.get("order_id") or ""),
            account_id=account_id,
            run_id=str(row.get("run_id") or ""),
            ticker=ticker,
            side=side,
            quantity=quantity,
            reference_price=reference,
            fill_price=fill_price,
            gross_value=gross,
            fee=fee,
            slippage_value=slippage_value,
            realized_pnl=realized_pnl,
            metadata={"service_version": SIMULATED_EXECUTION_SERVICE_VERSION, **dict(row.get("metadata") or {})},
        ).to_dict()
        self.fills.upsert(fill)
        row["status"] = OrderStatus.FILLED.value
        row["filled_at"] = fill["filled_at"]
        row["fill_id"] = fill["fill_id"]
        row["filled_quantity"] = quantity
        row["fill_price"] = fill_price
        row["fee"] = fee
        row["slippage_value"] = slippage_value
        self.orders.upsert(row)
        self.accounts.snapshot(account_id, run_id=str(row.get("run_id") or ""), source="simulated_execution")
        return {"ok": True, "order": row, "fill": fill, "account": saved_account}

    def execute_order(self, **kwargs: Any) -> dict[str, Any]:
        intent = self.create_intent(**kwargs)
        return self.execute(intent)


    def mirror_legacy_trade(self, *, account_id: str, trade: Mapping[str, Any], run_id: str = "") -> dict[str, Any]:
        """Store a legacy simulated trade in the common order/fill ledger once.

        Account state must already be synchronised from the legacy portfolio.
        The method never applies the cash/position mutation a second time.
        """
        ticker = str(trade.get("ticker") or trade.get("symbol") or "").upper()
        side = str(trade.get("action") or trade.get("side") or trade.get("type") or "").upper()
        if side not in {"BUY", "SELL"} or not ticker:
            return {"ok": False, "reason": "Ikke en kjøp/salg-handel"}
        legacy_id = str(trade.get("trade_id") or trade.get("id") or "")
        order_id = f"LEGACY-{account_id}-{legacy_id}" if legacy_id else build_order_id(account_id=account_id, run_id=run_id or str(trade.get("run_id") or "LEGACY"), ticker=ticker, side=side, nonce=str(trade.get("timestamp") or trade.get("time") or ""))
        existing = self.orders.get(order_id)
        if existing:
            return {"ok": True, "order": existing, "fill": self.fills.get(str(existing.get("fill_id") or "")), "mirrored": False}
        account = self.accounts.get(account_id)
        if not account:
            return {"ok": False, "reason": "Ukjent strategikonto"}
        price = _f(trade.get("price"))
        quantity = _f(trade.get("quantity", trade.get("shares", trade.get("units"))))
        gross = _f(trade.get("value", trade.get("amount", trade.get("notional"))), quantity * price)
        intent = OrderIntent(
            order_id=order_id, account_id=account_id, strategy_family=str(account.get("strategy_family") or ""),
            strategy_id=str(account.get("strategy_id") or ""), strategy_version_id=str(account.get("strategy_version_id") or ""),
            run_id=run_id or str(trade.get("run_id") or "LEGACY"), ticker=ticker, side=side,
            requested_quantity=quantity, requested_notional=gross, reference_price=price,
            reason=str(trade.get("reason") or "Legacy paper trade"), execution_authorized=True, status=OrderStatus.FILLED.value,
            metadata={"legacy_mirror": True, "legacy_trade_id": legacy_id, **dict(trade)},
        ).to_dict()
        fill_id = f"FILL-{order_id}"
        fill = SimulatedFill(
            fill_id=fill_id, order_id=order_id, account_id=account_id, run_id=intent["run_id"], ticker=ticker, side=side,
            quantity=quantity, reference_price=price, fill_price=price, gross_value=gross, fee=_f(trade.get("fee")),
            slippage_value=_f(trade.get("slippage_value")), realized_pnl=_f(trade.get("pnl")),
            filled_at=str(trade.get("timestamp") or trade.get("time") or _now()), metadata={"legacy_mirror": True},
        ).to_dict()
        intent.update({"fill_id": fill_id, "filled_at": fill["filled_at"], "filled_quantity": quantity, "fill_price": price})
        self.orders.upsert(intent); self.fills.upsert(fill)
        return {"ok": True, "order": intent, "fill": fill, "mirrored": True}

    def recent_orders(self, limit: int = 500) -> list[dict[str, Any]]:
        return sorted(self.orders.list(), key=lambda row: str(row.get("created_at") or ""), reverse=True)[: max(0, int(limit))]

    def recent_fills(self, limit: int = 500) -> list[dict[str, Any]]:
        return sorted(self.fills.list(), key=lambda row: str(row.get("filled_at") or ""), reverse=True)[: max(0, int(limit))]


_default: SimulatedExecutionService | None = None


def get_simulated_execution_service() -> SimulatedExecutionService:
    global _default
    if _default is None:
        _default = SimulatedExecutionService()
    return _default
