"""Canonical strategy account, order and fill contracts for v19.8.0.

The contracts are deliberately execution-agnostic. They describe theoretical
strategy accounts and simulated orders only; no broker or live-trading fields
are supported.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

STRATEGY_ACCOUNT_SCHEMA_VERSION = "1.0"
ORDER_INTENT_SCHEMA_VERSION = "1.0"
SIMULATED_FILL_SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_id(value: Any, fallback: str = "item") -> str:
    text = re.sub(r"[^a-zA-Z0-9_.:@-]+", "-", str(value or "").strip()).strip("-")
    return text or fallback


def stable_payload_checksum(value: Mapping[str, Any] | None) -> str:
    payload = json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    SHADOW = "SHADOW"
    RETIRED = "RETIRED"


class AccountRole(str, Enum):
    PRODUCTION = "PRODUCTION"
    LEARNING = "LEARNING"
    BENCHMARK = "BENCHMARK"
    CHALLENGER = "CHALLENGER"
    SHADOW = "SHADOW"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class StrategyAccount:
    account_id: str
    display_name: str
    strategy_family: str
    strategy_id: str
    strategy_version_id: str
    role: str
    status: str
    execution_mode: str
    initial_cash: float
    cash: float
    positions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    slippage_paid: float = 0.0
    high_watermark: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_run_id: str = ""
    parameter_version: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = STRATEGY_ACCOUNT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["positions"] = {str(k): dict(v) for k, v in dict(self.positions or {}).items()}
        row["metadata"] = dict(self.metadata or {})
        return row


@dataclass(frozen=True)
class OrderIntent:
    order_id: str
    account_id: str
    strategy_family: str
    strategy_id: str
    strategy_version_id: str
    run_id: str
    ticker: str
    side: str
    requested_quantity: float = 0.0
    requested_notional: float = 0.0
    reference_price: float = 0.0
    reason: str = ""
    market_snapshot_id: str = ""
    candidate_snapshot_id: str = ""
    execution_authorized: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    status: str = OrderStatus.CREATED.value
    rejection_code: str = ""
    rejection_reason: str = ""
    risk_context: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = ORDER_INTENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["risk_context"] = dict(self.risk_context or {})
        row["metadata"] = dict(self.metadata or {})
        return row


@dataclass(frozen=True)
class SimulatedFill:
    fill_id: str
    order_id: str
    account_id: str
    run_id: str
    ticker: str
    side: str
    quantity: float
    reference_price: float
    fill_price: float
    gross_value: float
    fee: float
    slippage_value: float
    realized_pnl: float = 0.0
    filled_at: str = field(default_factory=utc_now_iso)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SIMULATED_FILL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["metadata"] = dict(self.metadata or {})
        return row


def build_order_id(*, account_id: str, run_id: str, ticker: str, side: str, nonce: str = "") -> str:
    raw = "|".join([account_id, run_id, ticker.upper(), side.upper(), nonce or utc_now_iso()])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]
    return f"ORD-{_clean_id(account_id)[:28]}-{digest}"


def build_fill_id(order_id: str) -> str:
    digest = hashlib.sha256(f"{order_id}|{utc_now_iso()}".encode("utf-8")).hexdigest()[:18]
    return f"FILL-{digest}"


def validate_strategy_account(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    for key in ("account_id", "display_name", "strategy_family", "strategy_id", "role", "status", "execution_mode"):
        if not str(row.get(key) or "").strip():
            errors.append(f"Mangler {key}")
    try:
        initial = float(row.get("initial_cash") or 0)
        cash = float(row.get("cash") or 0)
        if initial < 0 or cash < -0.01:
            errors.append("Kontantverdier kan ikke være negative")
    except Exception:
        errors.append("Ugyldige kontantverdier")
    if not isinstance(row.get("positions", {}), Mapping):
        errors.append("positions må være et objekt")
    status = str(row.get("status") or "").upper()
    if status not in {item.value for item in AccountStatus}:
        errors.append("Ugyldig kontostatus")
    role = str(row.get("role") or "").upper()
    if role not in {item.value for item in AccountRole}:
        errors.append("Ugyldig kontorolle")
    return {"ok": not errors, "errors": errors, "schema_version": STRATEGY_ACCOUNT_SCHEMA_VERSION}


def validate_order_intent(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    for key in ("order_id", "account_id", "strategy_family", "strategy_id", "run_id", "ticker", "side"):
        if not str(row.get(key) or "").strip():
            errors.append(f"Mangler {key}")
    side = str(row.get("side") or "").upper()
    if side not in {item.value for item in OrderSide}:
        errors.append("Ugyldig ordreside")
    try:
        qty = float(row.get("requested_quantity") or 0)
        notional = float(row.get("requested_notional") or 0)
        price = float(row.get("reference_price") or 0)
        if qty <= 0 and notional <= 0:
            errors.append("Ordren må ha quantity eller notional")
        if price <= 0:
            errors.append("reference_price må være positiv")
    except Exception:
        errors.append("Ugyldige ordreverdier")
    return {"ok": not errors, "errors": errors, "schema_version": ORDER_INTENT_SCHEMA_VERSION}
