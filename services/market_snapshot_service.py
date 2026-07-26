"""Build and persist canonical market snapshots without changing decisions."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from domain.market_snapshot import (
    CANDIDATE_SNAPSHOT_SCHEMA_VERSION,
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    CandidateSnapshot,
    MarketSnapshot,
    build_market_snapshot_id,
    candidate_checksum_payload,
    infer_market,
    normalise_ticker,
    stable_checksum,
    utc_now_iso,
    validate_candidate_snapshot,
    validate_market_snapshot,
)
from repositories.application import RepositoryRegistry, get_repository_registry

SNAPSHOT_SERVICE_VERSION = "1.0"
_EXCLUDED_INPUT_KEYS = {"hist", "history", "dataframe", "df", "client", "session", "raw_bytes"}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _pick_number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _finite(row.get(key))
        if value is not None:
            return value
    return None


def _json_input_copy(item: Mapping[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, value in dict(item or {}).items():
        if str(key).lower() in _EXCLUDED_INPUT_KEYS:
            continue
        if hasattr(value, "to_json") and not isinstance(value, (str, bytes, Mapping, list, tuple)):
            continue
        copied[str(key)] = value
    return copied


class MarketSnapshotService:
    def __init__(self, repositories: RepositoryRegistry | None = None):
        self.repositories = repositories or get_repository_registry()
        self.snapshots = self.repositories.market_snapshots

    def new_snapshot_id(self, *, run_id: str = "", source: str = "", captured_at: str = "") -> str:
        return build_market_snapshot_id(run_id=run_id, source=source, captured_at=captured_at or utc_now_iso())

    def technical_context_from_history(self, hist: Any) -> dict[str, Any]:
        """Return the exact technical inputs used by the legacy paper scanner."""
        try:
            if hist is None or getattr(hist, "empty", True) or "Close" not in hist:
                return {}
            from technical import calculate_rsi, calculate_macd, detect_trend
            from patterns import breakout_scanner, detect_head_shoulders, detect_inverse_head_shoulders

            rsi_series = calculate_rsi(hist)
            rsi_clean = rsi_series.dropna()
            latest_rsi = float(rsi_clean.iloc[-1]) if len(rsi_clean) else 50.0

            macd, macd_signal, _ = calculate_macd(hist)
            macd_clean = macd.dropna()
            signal_clean = macd_signal.dropna()
            latest_macd = float(macd_clean.iloc[-1]) if len(macd_clean) else 0.0
            latest_signal = float(signal_clean.iloc[-1]) if len(signal_clean) else 0.0

            trend_text = str(detect_trend(hist))
            if "Opptrend" in trend_text:
                trend = "up"
            elif "Nedtrend" in trend_text:
                trend = "down"
            else:
                trend = "neutral"

            breakout = breakout_scanner(hist) or {}
            hs = detect_head_shoulders(hist) or {}
            inv = detect_inverse_head_shoulders(hist) or {}

            close = hist["Close"].dropna()
            recent = close.tail(80)
            if len(recent) > 5:
                low = float(recent.min())
                high = float(recent.max())
                last = float(close.iloc[-1])
                channel_pos = ((last - low) / (high - low) * 100) if high != low else 50.0
            else:
                channel_pos = 50.0

            return {
                "rsi": latest_rsi,
                "macd_bullish": latest_macd > latest_signal,
                "breakout_type": breakout.get("type", "neutral"),
                "trend": trend,
                "channel_pos": channel_pos,
                "head_shoulders_found": bool(hs.get("found")),
                "inverse_head_shoulders_found": bool(inv.get("found")),
            }
        except Exception:
            return {}

    def _price_and_timestamp(self, item: Mapping[str, Any]) -> tuple[float | None, str]:
        raw = item.get("raw") if isinstance(item.get("raw"), Mapping) else {}
        for key in ("price", "current_price", "last_price", "close", "regularMarketPrice", "last"):
            value = _finite(item.get(key, raw.get(key)))
            if value is not None and value > 0:
                return value, str(item.get("price_timestamp") or item.get("data_timestamp") or "")
        hist = item.get("hist")
        try:
            if hist is not None and "Close" in hist:
                close = hist["Close"].dropna()
                if len(close):
                    timestamp = ""
                    try:
                        timestamp = close.index[-1].isoformat()
                    except Exception:
                        timestamp = str(close.index[-1])
                    return float(close.iloc[-1]), timestamp
        except Exception:
            pass
        return None, str(item.get("price_timestamp") or item.get("data_timestamp") or "")

    def build_candidate_snapshot(
        self,
        item: Mapping[str, Any],
        technical_context: Mapping[str, Any] | None = None,
        *,
        market_snapshot_id: str = "",
        run_id: str = "",
        source: str = "",
        captured_at: str = "",
        provenance: Mapping[str, Any] | None = None,
    ) -> CandidateSnapshot:
        if isinstance(item, Mapping) and item.get("candidate_snapshot_id") and item.get("decision_inputs") is not None:
            snapshot = CandidateSnapshot.from_mapping(item)
            validation = validate_candidate_snapshot(snapshot.to_dict())
            if validation["ok"]:
                return snapshot

        row = dict(item or {})
        ticker = normalise_ticker(row.get("ticker") or row.get("symbol"))
        captured_at = str(captured_at or utc_now_iso())
        source = str(source or row.get("snapshot_source") or "legacy_decision_input")
        market_snapshot_id = str(
            market_snapshot_id
            or row.get("market_snapshot_id")
            or self.new_snapshot_id(run_id=run_id, source=source, captured_at=captured_at)
        )
        hist = row.get("hist")
        technical = dict(technical_context or row.get("technical") or row.get("technical_context") or {})
        if not technical and hist is not None:
            technical = self.technical_context_from_history(hist)
        price, data_timestamp = self._price_and_timestamp(row)
        decision_inputs = _json_input_copy(row)
        decision_inputs.setdefault("ticker", ticker)
        if row.get("score") is not None:
            decision_inputs["score"] = row.get("score")
        if price is not None:
            decision_inputs.setdefault("price", price)

        provisional = {
            "market_snapshot_id": market_snapshot_id,
            "ticker": ticker,
            "captured_at": captured_at,
            "source": source,
            "run_id": str(run_id or row.get("run_id") or ""),
            "name": str(row.get("name") or ticker),
            "market": str(row.get("market") or infer_market(ticker)),
            "currency": str(row.get("currency") or row.get("market_cap_currency") or row.get("financialCurrency") or ""),
            "price": price,
            "data_timestamp": data_timestamp,
            "base_score": _pick_number(row, "score", "investment_score", "decision_score", "combined_score"),
            "data_quality": _pick_number(row, "data_quality", "quality_score", "confidence_score"),
            "source_consensus": _pick_number(row, "source_consensus", "source_confidence", "consensus_score"),
            "liquidity": _pick_number(row, "liquidity", "liquidity_score", "average_volume"),
            "technical": technical,
            "decision_inputs": decision_inputs,
            "provenance": {
                "service_version": SNAPSHOT_SERVICE_VERSION,
                "source": source,
                **dict(provenance or {}),
            },
            "schema_version": CANDIDATE_SNAPSHOT_SCHEMA_VERSION,
        }
        checksum = stable_checksum(candidate_checksum_payload(provisional))
        candidate_id = f"CS-{ticker or 'UNKNOWN'}-{checksum[:20]}"
        snapshot = CandidateSnapshot(candidate_snapshot_id=candidate_id, checksum=checksum, **provisional)
        validation = validate_candidate_snapshot(snapshot.to_dict())
        if not validation["ok"]:
            raise ValueError("; ".join(validation["errors"]))
        return snapshot

    def build_market_snapshot(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        run_id: str = "",
        source: str = "",
        captured_at: str = "",
        snapshot_id: str = "",
        market_context: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MarketSnapshot:
        captured_at = str(captured_at or utc_now_iso())
        source = str(source or "market_snapshot")
        snapshot_id = str(snapshot_id or self.new_snapshot_id(run_id=run_id, source=source, captured_at=captured_at))
        built: list[dict[str, Any]] = []
        for candidate in candidates or []:
            if isinstance(candidate, Mapping) and candidate.get("candidate_snapshot_id"):
                value = dict(candidate)
                if value.get("market_snapshot_id") != snapshot_id:
                    value = self.build_candidate_snapshot(
                        value.get("decision_inputs") or value,
                        value.get("technical") or {},
                        market_snapshot_id=snapshot_id,
                        run_id=run_id,
                        source=source,
                        captured_at=value.get("captured_at") or captured_at,
                        provenance=value.get("provenance") or {},
                    ).to_dict()
                built.append(value)
            else:
                built.append(self.build_candidate_snapshot(
                    candidate,
                    market_snapshot_id=snapshot_id,
                    run_id=run_id,
                    source=source,
                    captured_at=captured_at,
                ).to_dict())
        provisional = {
            "snapshot_id": snapshot_id,
            "captured_at": captured_at,
            "source": source,
            "run_id": str(run_id or ""),
            "candidates": built,
            "market_context": dict(market_context or {}),
            "metadata": {"service_version": SNAPSHOT_SERVICE_VERSION, **dict(metadata or {})},
            "schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
        }
        checksum = stable_checksum(provisional)
        snapshot = MarketSnapshot(checksum=checksum, **provisional)
        validation = validate_market_snapshot(snapshot.to_dict())
        if not validation["ok"]:
            raise ValueError("; ".join(validation["errors"]))
        return snapshot

    def save(self, snapshot: MarketSnapshot | Mapping[str, Any]) -> dict[str, Any]:
        value = snapshot.to_dict() if isinstance(snapshot, MarketSnapshot) else dict(snapshot or {})
        validation = validate_market_snapshot(value)
        if not validation["ok"]:
            return {"ok": False, "saved": False, "errors": validation["errors"], "snapshot_id": value.get("snapshot_id", "")}
        try:
            self.snapshots.upsert(value)
            return {"ok": True, "saved": True, "errors": [], "snapshot_id": value.get("snapshot_id", "")}
        except Exception as exc:
            # Snapshot persistence is evidence collection and may not stop a valid decision.
            return {"ok": False, "saved": False, "errors": [str(exc)], "snapshot_id": value.get("snapshot_id", "")}

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        return self.snapshots.get(snapshot_id)


_default: MarketSnapshotService | None = None


def get_market_snapshot_service() -> MarketSnapshotService:
    global _default
    if _default is None:
        _default = MarketSnapshotService()
    return _default
