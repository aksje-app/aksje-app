"""Observed post-decision outcomes for Strategy Lab v19.11.0.

Outcomes are stored separately from immutable decision snapshots. The service
uses only market data observed after the snapshot date and never feeds outcome
values back into strategy evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Callable, Mapping, Sequence

from repositories.application import RepositoryRegistry, get_repository_registry

STRATEGY_OUTCOME_SERVICE_VERSION = "1.0"
PRIMARY_ATTRIBUTION_HORIZON = 5
DEFAULT_HORIZONS = (1, 5, 20)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date(value: Any):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _history_provider(ticker: str):
    from analysis import get_history
    return get_history(ticker, period="6mo")


def _close_rows(history: Any) -> list[tuple[Any, float]]:
    try:
        if history is None or getattr(history, "empty", True) or "Close" not in history:
            return []
        close = history["Close"].dropna()
        rows = []
        for index, value in close.items():
            day = index.date() if hasattr(index, "date") else _date(index)
            if day is not None:
                rows.append((day, float(value)))
        return sorted(rows, key=lambda item: item[0])
    except Exception:
        return []


def _outcome_id(candidate_snapshot_id: str, horizon: int) -> str:
    seed = f"{candidate_snapshot_id}|{int(horizon)}"
    return f"OUT-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


class StrategyOutcomeService:
    def __init__(
        self,
        repositories: RepositoryRegistry | None = None,
        history_provider: Callable[[str], Any] | None = None,
    ):
        self.repositories = repositories or get_repository_registry()
        self.outcomes = self.repositories.strategy_outcomes
        self.history_provider = history_provider or _history_provider

    def settle_snapshots(
        self,
        snapshots: Sequence[Mapping[str, Any]],
        *,
        horizons: Sequence[int] = DEFAULT_HORIZONS,
        force: bool = False,
    ) -> dict[str, Any]:
        created = existing = unavailable = errors = 0
        candidates_seen = 0
        per_ticker_history: dict[str, Any] = {}
        error_rows: list[dict[str, str]] = []
        for snapshot in snapshots or []:
            captured_at = str(snapshot.get("captured_at") or "")
            captured_date = _date(captured_at)
            if captured_date is None:
                errors += 1
                error_rows.append({"snapshot_id": str(snapshot.get("snapshot_id") or ""), "error": "invalid_captured_at"})
                continue
            for candidate in snapshot.get("candidates") or []:
                if not isinstance(candidate, Mapping):
                    continue
                candidates_seen += 1
                candidate_id = str(candidate.get("candidate_snapshot_id") or "")
                ticker = str(candidate.get("ticker") or "").upper()
                try:
                    entry_price = float(candidate.get("price") or 0.0)
                except Exception:
                    entry_price = 0.0
                if not candidate_id or not ticker or entry_price <= 0:
                    unavailable += len(tuple(horizons))
                    continue
                if ticker not in per_ticker_history:
                    try:
                        per_ticker_history[ticker] = self.history_provider(ticker)
                    except Exception as exc:
                        per_ticker_history[ticker] = None
                        errors += 1
                        error_rows.append({"ticker": ticker, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
                future_rows = [(day, price) for day, price in _close_rows(per_ticker_history[ticker]) if day > captured_date]
                for raw_horizon in horizons:
                    horizon = max(1, int(raw_horizon))
                    outcome_id = _outcome_id(candidate_id, horizon)
                    previous = self.outcomes.get(outcome_id)
                    if previous and not force:
                        existing += 1
                        continue
                    if len(future_rows) < horizon:
                        unavailable += 1
                        continue
                    observed_date, exit_price = future_rows[horizon - 1]
                    return_pct = (exit_price / entry_price - 1.0) * 100.0
                    row = {
                        "outcome_id": outcome_id,
                        "candidate_snapshot_id": candidate_id,
                        "market_snapshot_id": str(candidate.get("market_snapshot_id") or snapshot.get("snapshot_id") or ""),
                        "ticker": ticker,
                        "snapshot_captured_at": captured_at,
                        "horizon_sessions": horizon,
                        "entry_price": round(entry_price, 8),
                        "exit_price": round(exit_price, 8),
                        "return_pct": round(return_pct, 6),
                        "observed_date": observed_date.isoformat(),
                        "settled_at": _now(),
                        "source": "observed_market_close",
                        "lookahead_used_in_decision": False,
                        "service_version": STRATEGY_OUTCOME_SERVICE_VERSION,
                        "schema_version": "1.0",
                    }
                    self.outcomes.upsert(row)
                    created += 1
        return {
            "snapshot_count": len(snapshots or []),
            "candidate_count": candidates_seen,
            "created": created,
            "existing": existing,
            "unavailable": unavailable,
            "error_count": errors,
            "errors": error_rows,
            "horizons": [int(value) for value in horizons],
            "production_applied": False,
            "execution_authorized": False,
        }

    def outcome_for(self, candidate_snapshot_id: str, *, horizon: int = PRIMARY_ATTRIBUTION_HORIZON) -> dict[str, Any] | None:
        return self.outcomes.get(_outcome_id(str(candidate_snapshot_id), int(horizon)))

    def lookup(self, *, horizon: int = PRIMARY_ATTRIBUTION_HORIZON) -> dict[str, dict[str, Any]]:
        return {
            str(row.get("candidate_snapshot_id") or ""): dict(row)
            for row in self.outcomes.list()
            if int(row.get("horizon_sessions") or 0) == int(horizon) and row.get("candidate_snapshot_id")
        }
