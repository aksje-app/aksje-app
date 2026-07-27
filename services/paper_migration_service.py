"""Non-destructive Paper Trading migration foundation for v19.13.0."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from services.strategy_account_service import StrategyAccountService, get_strategy_account_service
from services.simulated_execution_service import SimulatedExecutionService, get_simulated_execution_service

PAPER_MIGRATION_SERVICE_VERSION = "1.0"
MIGRATION_ID = "paper-foundation-v19.13.0"
ACCOUNT_ID = "technical_benchmark_main"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalise_legacy(payload: Mapping[str, Any]) -> dict[str, Any]:
    positions: dict[str, dict[str, Any]] = {}
    raw_positions = payload.get("positions") if isinstance(payload.get("positions"), Mapping) else {}
    for ticker, raw in raw_positions.items():
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        symbol = str(row.get("ticker") or ticker).upper().strip()
        if not symbol:
            continue
        quantity = _f(row.get("quantity", row.get("shares", row.get("units"))))
        average_price = _f(row.get("average_price", row.get("entry_price", row.get("avg_price"))))
        last_price = _f(row.get("last_price"), average_price)
        positions[symbol] = {
            **row,
            "ticker": symbol,
            "quantity": quantity,
            "average_price": average_price,
            "last_price": last_price,
            "market_value": round(quantity * last_price, 2),
        }
    trades = [dict(row) for row in (payload.get("trades") or []) if isinstance(row, Mapping)]
    return {
        "cash": round(_f(payload.get("cash"), 100000.0), 2),
        "initial_cash": round(_f(payload.get("initial_cash"), 100000.0), 2),
        "realized_pnl": round(_f(payload.get("realized_pnl")), 2),
        "positions": positions,
        "trades": trades,
    }


def _position_summary(positions: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for ticker, raw in positions.items():
        if not isinstance(raw, Mapping):
            continue
        result[str(ticker).upper()] = {
            "quantity": round(_f(raw.get("quantity", raw.get("shares", raw.get("units")))), 8),
            "average_price": round(_f(raw.get("average_price", raw.get("entry_price", raw.get("avg_price")))), 8),
            "last_price": round(_f(raw.get("last_price"), _f(raw.get("average_price", raw.get("entry_price", raw.get("avg_price"))))), 8),
        }
    return result


class PaperMigrationService:
    def __init__(self, accounts: StrategyAccountService | None = None, execution: SimulatedExecutionService | None = None):
        self.accounts = accounts or get_strategy_account_service()
        self.execution = execution or get_simulated_execution_service()
        self.repositories = self.accounts.repositories

    def _binding_snapshot(self) -> list[dict[str, Any]]:
        rows = self.repositories.strategy_production_bindings.list()
        return sorted([dict(row) for row in rows], key=lambda row: str(row.get("strategy_family") or ""))

    def _ledger_counts(self) -> dict[str, int]:
        orders = [row for row in self.repositories.strategy_orders.list() if row.get("account_id") == ACCOUNT_ID]
        fills = [row for row in self.repositories.strategy_fills.list() if row.get("account_id") == ACCOUNT_ID]
        return {"orders": len(orders), "fills": len(fills)}

    def inspect(self, legacy_payload: Mapping[str, Any], *, source: str = "unknown") -> dict[str, Any]:
        legacy = normalise_legacy(legacy_payload)
        current = self.accounts.get(ACCOUNT_ID)
        binding = self._binding_snapshot()
        return {
            "migration_id": MIGRATION_ID,
            "mode": "DRY_RUN",
            "source": source,
            "source_checksum": checksum(legacy),
            "legacy": {
                "cash": legacy["cash"],
                "position_count": len(legacy["positions"]),
                "trade_count": len(legacy["trades"]),
                "market_value": round(sum(_f(row.get("market_value")) for row in legacy["positions"].values()), 2),
            },
            "canonical_before": current,
            "ledger_before": self._ledger_counts(),
            "production_bindings_checksum": checksum(binding),
            "would_create_backup": True,
            "would_sync_account": True,
            "would_mirror_trades": len(legacy["trades"]),
            "runtime_cutover": False,
            "legacy_delete": False,
            "autonomy_change": False,
        }

    def _reconcile(self, legacy: Mapping[str, Any], account: Mapping[str, Any]) -> dict[str, Any]:
        legacy_positions = _position_summary(legacy.get("positions") or {})
        account_positions = _position_summary(account.get("positions") or {})
        checks = {
            "cash": round(_f(account.get("cash")), 2) == round(_f(legacy.get("cash")), 2),
            "position_count": len(account_positions) == len(legacy_positions),
            "positions": account_positions == legacy_positions,
            "realized_pnl": round(_f(account.get("realized_pnl")), 2) == round(_f(legacy.get("realized_pnl")), 2),
        }
        return {
            "ok": all(checks.values()),
            "checks": checks,
            "legacy_positions": legacy_positions,
            "canonical_positions": account_positions,
            "legacy_cash": round(_f(legacy.get("cash")), 2),
            "canonical_cash": round(_f(account.get("cash")), 2),
        }

    def migrate(self, legacy_payload: Mapping[str, Any], *, source: str, output_dir: Path, confirmation: str, reason: str) -> dict[str, Any]:
        if str(confirmation or "").strip().upper() != "MIGRER":
            raise ValueError("Bekreftelse må være MIGRER")
        if not str(reason or "").strip():
            raise ValueError("Begrunnelse er påkrevd")
        legacy = normalise_legacy(legacy_payload)
        output_dir.mkdir(parents=True, exist_ok=True)
        before_account = self.accounts.get(ACCOUNT_ID)
        before_bindings = self._binding_snapshot()
        before_ledger = self._ledger_counts()
        source_checksum = checksum(legacy)
        backup = {
            "migration_id": MIGRATION_ID,
            "created_at": _now(),
            "source": source,
            "source_checksum": source_checksum,
            "legacy_payload": legacy,
            "canonical_before": before_account,
            "production_bindings_before": before_bindings,
            "ledger_before": before_ledger,
        }
        backup_path = output_dir / f"paper_legacy_backup_{source_checksum[:12]}.json"
        if not backup_path.exists():
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        row = self.accounts.sync_legacy_account(
            ACCOUNT_ID, legacy,
            strategy_family="technical", strategy_id="technical_benchmark",
            strategy_version_id="technical_benchmark@legacy-1.0.0",
            display_name="Teknisk benchmark", role="BENCHMARK", status="ACTIVE",
            run_id="MIGRATION-V19130",
            metadata={"migration": MIGRATION_ID, "legacy_source": source, "source_checksum": source_checksum},
        )
        mirrored = 0
        already_present = 0
        errors: list[str] = []
        for trade in legacy.get("trades") or []:
            try:
                result = self.execution.mirror_legacy_trade(account_id=ACCOUNT_ID, trade=trade, run_id="MIGRATION-V19130")
                mirrored += int(bool(result.get("mirrored")))
                already_present += int(bool(result.get("ok")) and not bool(result.get("mirrored")))
                if not result.get("ok"):
                    errors.append(str(result.get("reason") or "Ukjent handelsfeil"))
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")

        after_account = self.accounts.get(ACCOUNT_ID) or row
        after_bindings = self._binding_snapshot()
        after_ledger = self._ledger_counts()
        reconciliation = self._reconcile(legacy, after_account)
        binding_unchanged = checksum(before_bindings) == checksum(after_bindings)
        result = {
            "migration_id": MIGRATION_ID,
            "mode": "MIGRATE",
            "created_at": _now(),
            "source": source,
            "source_checksum": source_checksum,
            "reason": reason.strip(),
            "backup_path": str(backup_path),
            "backup_checksum": checksum(backup),
            "mirrored_trades": mirrored,
            "already_present_trades": already_present,
            "ledger_before": before_ledger,
            "ledger_after": after_ledger,
            "reconciliation": reconciliation,
            "production_binding_unchanged": binding_unchanged,
            "autonomy_changed": False,
            "runtime_cutover": False,
            "legacy_deleted": False,
            "errors": errors,
        }
        result["ok"] = reconciliation["ok"] and binding_unchanged and not errors
        report_path = output_dir / f"paper_migration_report_{source_checksum[:12]}.json"
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        result["report_path"] = str(report_path)
        self.repositories.documents.write(f"migrations/{MIGRATION_ID}.json", {**result, "backup_path": backup_path.name, "report_path": report_path.name})
        return result
