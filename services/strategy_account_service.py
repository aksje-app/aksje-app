"""Persistent strategy accounts and legacy account bridges for v19.8.0."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from domain.strategy_account import (
    AccountRole,
    AccountStatus,
    StrategyAccount,
    validate_strategy_account,
)
from repositories.application import RepositoryRegistry, get_repository_registry
from services.strategy_registry_service import StrategyRegistryService
from app_version import AUTONOMY_POLICY_VERSION, AUTONOMY_STRATEGY_VERSION_ID

STRATEGY_ACCOUNT_SERVICE_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalise_position(ticker: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(raw or {})
    quantity = _f(row.get("quantity", row.get("shares", row.get("units"))))
    average_price = _f(row.get("average_price", row.get("entry_price", row.get("avg_price"))))
    last_price = _f(row.get("last_price"), average_price)
    return {
        **row,
        "ticker": str(row.get("ticker") or ticker).upper(),
        "quantity": quantity,
        "average_price": average_price,
        "last_price": last_price,
        "market_value": round(quantity * last_price, 2),
    }


class StrategyAccountService:
    def __init__(self, repositories: RepositoryRegistry | None = None, registry: StrategyRegistryService | None = None):
        self.repositories = repositories or get_repository_registry()
        self.registry = registry or StrategyRegistryService(self.repositories)
        self.accounts = self.repositories.strategy_accounts
        self.snapshots = self.repositories.strategy_account_snapshots

    def list_accounts(self) -> list[dict[str, Any]]:
        self.ensure_defaults()
        return sorted(self.accounts.list(), key=lambda row: (str(row.get("strategy_family") or ""), str(row.get("account_id") or "")))

    def get(self, account_id: str) -> dict[str, Any] | None:
        return self.accounts.get(account_id)

    def upsert(self, value: StrategyAccount | Mapping[str, Any]) -> dict[str, Any]:
        row = value.to_dict() if isinstance(value, StrategyAccount) else dict(value or {})
        row["updated_at"] = _now()
        validation = validate_strategy_account(row)
        if not validation["ok"]:
            raise ValueError("; ".join(validation["errors"]))
        self.accounts.upsert(row)
        return row

    def ensure_defaults(self) -> list[dict[str, Any]]:
        self.registry.ensure_defaults()
        technical = self.registry.production_for_family("technical") or {}
        autonomy = self.registry.production_for_family("autonomy") or {}
        defaults = [
            StrategyAccount(
                account_id="technical_benchmark_main",
                display_name="Teknisk benchmark",
                strategy_family="technical",
                strategy_id=str(technical.get("strategy_id") or "technical_benchmark"),
                strategy_version_id=str(technical.get("version_id") or "technical_benchmark@legacy-1.0.0"),
                role=AccountRole.BENCHMARK.value,
                status=AccountStatus.ACTIVE.value,
                execution_mode="PAPER",
                initial_cash=100000.0,
                cash=100000.0,
                high_watermark=100000.0,
                parameter_version=str(technical.get("parameter_version") or "paper-trading-rules-current"),
                metadata={"legacy_source": "paper_store", "canonical_execution": True},
            ),
            StrategyAccount(
                account_id="autonomy_main",
                display_name="Autonomi hovedstrategi",
                strategy_family="autonomy",
                strategy_id=str(autonomy.get("strategy_id") or "autonomy_main"),
                strategy_version_id=str(autonomy.get("version_id") or AUTONOMY_STRATEGY_VERSION_ID),
                role=AccountRole.PRODUCTION.value,
                status=AccountStatus.PAUSED.value,
                execution_mode="PAPER",
                initial_cash=500000.0,
                cash=500000.0,
                high_watermark=500000.0,
                parameter_version=str(autonomy.get("parameter_version") or AUTONOMY_POLICY_VERSION),
                metadata={"legacy_source": "autonomous_portfolio", "canonical_execution": True},
            ),
            StrategyAccount(
                account_id="autonomy_learning",
                display_name="Autonomi læringskonto",
                strategy_family="autonomy",
                strategy_id="autonomy_learning",
                strategy_version_id="autonomy_learning@1.0.0",
                role=AccountRole.LEARNING.value,
                status=AccountStatus.ACTIVE.value,
                execution_mode="PAPER",
                initial_cash=100000.0,
                cash=100000.0,
                high_watermark=100000.0,
                parameter_version="learning-policy-2.0",
                metadata={
                    "purpose": "Kontrollert aktivitet med små paper-posisjoner",
                    "maximum_position_pct": 1.5,
                    "minimum_score": 63.0,
                    "minimum_data_quality": 55.0,
                    "maximum_risk_score": 75.0,
                    "notional_value": 15000.0,
                    "reserve_cash_pct": 15.0,
                    "maximum_open_positions": 20,
                    "maximum_buys_per_cycle": 3,
                    "trailing_stop_pct": 10.0,
                    "horizon_days": 60,
                    "learning_policy_profile_version": "2.0",
                    "hard_production_gates_unchanged": True,
                    "canonical_execution": True,
                },
            ),
        ]
        rows: list[dict[str, Any]] = []
        for item in defaults:
            existing = self.get(item.account_id)
            rows.append(existing or self.upsert(item))
        return rows

    def sync_legacy_account(
        self,
        account_id: str,
        legacy_portfolio: Mapping[str, Any],
        *,
        strategy_family: str,
        strategy_id: str,
        strategy_version_id: str,
        display_name: str,
        role: str,
        execution_mode: str = "PAPER",
        status: str | None = None,
        run_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get(account_id) or {}
        raw_positions = legacy_portfolio.get("positions") if isinstance(legacy_portfolio.get("positions"), Mapping) else {}
        positions = {str(ticker).upper(): _normalise_position(str(ticker), raw) for ticker, raw in raw_positions.items() if isinstance(raw, Mapping)}
        cash = _f(legacy_portfolio.get("cash"), _f(current.get("cash")))
        initial_cash = _f(legacy_portfolio.get("initial_cash"), _f(current.get("initial_cash"), cash))
        market_value = sum(_f(row.get("market_value")) for row in positions.values())
        equity = cash + market_value
        strategy = self.registry.get(strategy_version_id) or {}
        row = StrategyAccount(
            account_id=account_id,
            display_name=display_name,
            strategy_family=strategy_family,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            role=role,
            status=str(status or legacy_portfolio.get("status") or current.get("status") or AccountStatus.ACTIVE.value).upper(),
            execution_mode=execution_mode,
            initial_cash=initial_cash,
            cash=max(0.0, cash),
            positions=positions,
            realized_pnl=_f(legacy_portfolio.get("realized_pnl"), _f(current.get("realized_pnl"))),
            fees_paid=_f(current.get("fees_paid")),
            slippage_paid=_f(current.get("slippage_paid")),
            high_watermark=max(_f(current.get("high_watermark"), equity), equity),
            created_at=str(current.get("created_at") or _now()),
            updated_at=_now(),
            last_run_id=run_id or str(legacy_portfolio.get("last_run_id") or current.get("last_run_id") or ""),
            parameter_version=str(strategy.get("parameter_version") or current.get("parameter_version") or "legacy-current"),
            metadata={**dict(current.get("metadata") or {}), **dict(metadata or {}), "legacy_sync": True, "equity": round(equity, 2)},
        ).to_dict()
        saved = self.upsert(row)
        self.snapshot(account_id, run_id=run_id or saved.get("last_run_id") or "LEGACY-SYNC", source="legacy_sync")
        return saved

    def equity(self, account: Mapping[str, Any]) -> float:
        return _f(account.get("cash")) + sum(
            _f(pos.get("quantity")) * _f(pos.get("last_price"), _f(pos.get("average_price")))
            for pos in (account.get("positions") or {}).values()
        )

    def metrics(self, account_id: str) -> dict[str, Any]:
        account = self.get(account_id) or {}
        metadata = dict(account.get("metadata") or {})
        accounting_mode = str(metadata.get("accounting_mode") or "CASH_ACCOUNT").upper()
        positions_value = sum(
            _f(pos.get("quantity")) * _f(pos.get("last_price"), _f(pos.get("average_price")))
            for pos in (account.get("positions") or {}).values()
        )
        if accounting_mode == "INDEPENDENT_NOTIONAL_OBSERVATIONS":
            entry_notional = _f(metadata.get("entry_notional")) or sum(
                _f(pos.get("quantity")) * _f(pos.get("average_price"))
                for pos in (account.get("positions") or {}).values()
            )
            total_pnl = positions_value - entry_notional + _f(account.get("realized_pnl"))
            initial = entry_notional
            equity = entry_notional + total_pnl
        else:
            equity = self.equity(account)
            initial = _f(account.get("initial_cash"), equity)
        high = (
            max(initial, equity)
            if accounting_mode == "INDEPENDENT_NOTIONAL_OBSERVATIONS"
            else max(_f(account.get("high_watermark"), equity), equity)
        )
        return {
            "account_id": account_id,
            "display_name": account.get("display_name"),
            "strategy_family": account.get("strategy_family"),
            "role": account.get("role"),
            "status": account.get("status"),
            "cash": round(_f(account.get("cash")), 2),
            "positions_value": round(positions_value, 2),
            "equity": round(equity, 2),
            "return_value": round(equity - initial, 2),
            "return_pct": round(((equity / initial) - 1) * 100, 4) if initial else 0.0,
            "drawdown_pct": round(max(0.0, (1 - equity / high) * 100), 4) if high else 0.0,
            "open_positions": len(account.get("positions") or {}),
            "realized_pnl": round(_f(account.get("realized_pnl")), 2),
            "fees_paid": round(_f(account.get("fees_paid")), 2),
            "slippage_paid": round(_f(account.get("slippage_paid")), 2),
            "last_run_id": account.get("last_run_id"),
            "updated_at": account.get("updated_at"),
            "accounting_mode": accounting_mode,
            "return_basis": "ENTRY_NOTIONAL" if accounting_mode == "INDEPENDENT_NOTIONAL_OBSERVATIONS" else "INITIAL_CASH",
        }

    def snapshot(self, account_id: str, *, run_id: str, source: str = "strategy_account_service") -> dict[str, Any]:
        account = self.get(account_id)
        if not account:
            raise ValueError(f"Ukjent strategikonto: {account_id}")
        metrics = self.metrics(account_id)
        snapshot_id = f"{account_id}:{run_id}:{str(account.get('updated_at') or '')}"
        row = {
            "account_snapshot_id": snapshot_id,
            "account_id": account_id,
            "run_id": run_id,
            "source": source,
            "created_at": _now(),
            "account": account,
            "metrics": metrics,
            "service_version": STRATEGY_ACCOUNT_SERVICE_VERSION,
        }
        self.snapshots.upsert(row)
        return row

    def comparison(self) -> list[dict[str, Any]]:
        return [self.metrics(row["account_id"]) for row in self.list_accounts()]


_default: StrategyAccountService | None = None


def get_strategy_account_service() -> StrategyAccountService:
    global _default
    if _default is None:
        _default = StrategyAccountService()
    return _default
