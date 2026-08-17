"""Canonical market and candidate snapshot contracts for v19.6.0.

Snapshots are immutable, JSON-serialisable decision evidence. They contain the
normalised values consumed by strategies, never live DataFrames, clients or
cache objects. The contract does not calculate scores or execute orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

MARKET_SNAPSHOT_SCHEMA_VERSION = "1.0"
CANDIDATE_SNAPSHOT_SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalise_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def infer_market(ticker: str) -> str:
    ticker = normalise_ticker(ticker)
    if ticker.endswith(".OL"):
        return "NORGE"
    if ticker.endswith(".ST"):
        return "SVERIGE"
    if ticker.endswith(".HE"):
        return "FINLAND"
    if ticker.endswith(".CO"):
        return "DANMARK"
    if ticker.endswith(".SA"):
        return "BRASIL"
    return "USA"


def build_market_snapshot_id(*, run_id: str = "", source: str = "", captured_at: str = "") -> str:
    timestamp = str(captured_at or utc_now_iso())
    seed = {"run_id": str(run_id or ""), "source": str(source or ""), "captured_at": timestamp}
    prefix = re.sub(r"[^A-Z0-9]+", "-", str(run_id or "MARKET").upper()).strip("-")[:32] or "MARKET"
    return f"MS-{prefix}-{stable_checksum(seed)[:16]}"


@dataclass(frozen=True)
class CandidateSnapshot:
    candidate_snapshot_id: str
    market_snapshot_id: str
    ticker: str
    captured_at: str
    source: str
    run_id: str = ""
    name: str = ""
    market: str = ""
    currency: str = ""
    price: float | None = None
    data_timestamp: str = ""
    base_score: float | None = None
    data_quality: float | None = None
    source_consensus: float | None = None
    liquidity: float | None = None
    quality_evidence: Mapping[str, Any] = field(default_factory=dict)
    quality_coverage: Mapping[str, Any] = field(default_factory=dict)
    technical: Mapping[str, Any] = field(default_factory=dict)
    decision_inputs: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    checksum: str = ""
    schema_version: str = CANDIDATE_SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_snapshot_id": self.candidate_snapshot_id,
            "market_snapshot_id": self.market_snapshot_id,
            "ticker": self.ticker, "captured_at": self.captured_at,
            "source": self.source, "run_id": self.run_id, "name": self.name,
            "market": self.market, "currency": self.currency, "price": self.price,
            "data_timestamp": self.data_timestamp, "base_score": self.base_score,
            "data_quality": self.data_quality, "source_consensus": self.source_consensus,
            "liquidity": self.liquidity,
            "quality_evidence": dict(self.quality_evidence),
            "quality_coverage": dict(self.quality_coverage),
            "technical": dict(self.technical),
            "decision_inputs": dict(self.decision_inputs),
            "provenance": dict(self.provenance),
            "checksum": self.checksum, "schema_version": self.schema_version,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateSnapshot":
        row = dict(value or {})
        return cls(
            candidate_snapshot_id=str(row.get("candidate_snapshot_id") or ""),
            market_snapshot_id=str(row.get("market_snapshot_id") or row.get("snapshot_id") or ""),
            ticker=normalise_ticker(row.get("ticker")),
            captured_at=str(row.get("captured_at") or utc_now_iso()),
            source=str(row.get("source") or "unknown"),
            run_id=str(row.get("run_id") or ""),
            name=str(row.get("name") or ""),
            market=str(row.get("market") or infer_market(row.get("ticker"))),
            currency=str(row.get("currency") or ""),
            price=_finite_or_none(row.get("price")),
            data_timestamp=str(row.get("data_timestamp") or ""),
            base_score=_finite_or_none(row.get("base_score")),
            data_quality=_finite_or_none(row.get("data_quality")),
            source_consensus=_finite_or_none(row.get("source_consensus")),
            liquidity=_finite_or_none(row.get("liquidity")),
            quality_evidence=dict(row.get("quality_evidence") or {}),
            quality_coverage=dict(row.get("quality_coverage") or {}),
            technical=dict(row.get("technical") or {}),
            decision_inputs=dict(row.get("decision_inputs") or {}),
            provenance=dict(row.get("provenance") or {}),
            checksum=str(row.get("checksum") or ""),
            schema_version=str(row.get("schema_version") or CANDIDATE_SNAPSHOT_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MarketSnapshot:
    snapshot_id: str
    captured_at: str
    source: str
    run_id: str
    candidates: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    market_context: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    checksum: str = ""
    schema_version: str = MARKET_SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id, "captured_at": self.captured_at,
            "source": self.source, "run_id": self.run_id,
            "candidates": [dict(item) for item in self.candidates],
            "market_context": dict(self.market_context),
            "metadata": dict(self.metadata), "checksum": self.checksum,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MarketSnapshot":
        row = dict(value or {})
        return cls(
            snapshot_id=str(row.get("snapshot_id") or ""),
            captured_at=str(row.get("captured_at") or utc_now_iso()),
            source=str(row.get("source") or "unknown"),
            run_id=str(row.get("run_id") or ""),
            candidates=tuple(dict(item) for item in (row.get("candidates") or []) if isinstance(item, Mapping)),
            market_context=dict(row.get("market_context") or {}),
            metadata=dict(row.get("metadata") or {}),
            checksum=str(row.get("checksum") or ""),
            schema_version=str(row.get("schema_version") or MARKET_SNAPSHOT_SCHEMA_VERSION),
        )


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def candidate_checksum_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    row.pop("checksum", None)
    row.pop("candidate_snapshot_id", None)
    return _json_safe(row)


def market_checksum_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    row.pop("checksum", None)
    return _json_safe(row)


def validate_candidate_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    for key in ("candidate_snapshot_id", "market_snapshot_id", "ticker", "captured_at", "source"):
        if not str(row.get(key) or "").strip():
            errors.append(f"Mangler {key}")
    if str(row.get("schema_version") or "") != CANDIDATE_SNAPSHOT_SCHEMA_VERSION:
        errors.append("Ugyldig candidate snapshot schema")
    expected = stable_checksum(candidate_checksum_payload(row))
    if row.get("checksum") and str(row.get("checksum")) != expected:
        errors.append("Candidate snapshot checksum stemmer ikke")
    return {"ok": not errors, "errors": errors, "expected_checksum": expected}


def validate_market_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value or {})
    errors: list[str] = []
    for key in ("snapshot_id", "captured_at", "source"):
        if not str(row.get(key) or "").strip():
            errors.append(f"Mangler {key}")
    if str(row.get("schema_version") or "") != MARKET_SNAPSHOT_SCHEMA_VERSION:
        errors.append("Ugyldig market snapshot schema")
    candidates = row.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates må være en liste")
    else:
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                errors.append(f"Kandidat {index} er ikke et objekt")
                continue
            result = validate_candidate_snapshot(candidate)
            errors.extend(f"Kandidat {index}: {error}" for error in result["errors"])
            if str(candidate.get("market_snapshot_id") or "") != str(row.get("snapshot_id") or ""):
                errors.append(f"Kandidat {index}: market_snapshot_id avviker")
    expected = stable_checksum(market_checksum_payload(row))
    if row.get("checksum") and str(row.get("checksum")) != expected:
        errors.append("Market snapshot checksum stemmer ikke")
    return {"ok": not errors, "errors": errors, "expected_checksum": expected}
