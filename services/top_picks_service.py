from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core_models import ServiceResult, StockCandidate, TopPickItem
from services.state_service import get_state_service
from services.storage_service import get_storage_service
from services.universe_service import _extract_tickers, get_universe_service


def _ok(data: Any = None, message: str = "", status: str = "ok") -> ServiceResult:
    return ServiceResult(ok=True, status=status, message=message, data=data if data is not None else {})


class TopPicksService:
    def __init__(self, state_service=None, storage_service=None, universe_service=None):
        self.state = state_service or get_state_service()
        self.storage = storage_service or get_storage_service()
        self.universe = universe_service or get_universe_service(state_service=self.state, storage_service=self.storage)

    def _candidate_rows(self, result: Mapping[str, Any], limit: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        source_rows = result.get("top_picks") or result.get("candidates") or []
        for idx, row in enumerate(source_rows[: max(1, int(limit or 10))], start=1):
            if isinstance(row, StockCandidate):
                item = row.as_dict()
            elif isinstance(row, Mapping):
                item = dict(row)
            else:
                ticker = str(row or "").upper()
                item = {"ticker": ticker, "name": ticker}
            item.setdefault("rank", idx)
            item.setdefault("source", "Smart AI")
            rows.append(item)
        return rows

    def save_from_universe_result(self, result: Mapping[str, Any], limit: int = 10, list_name: str = "TopPicks_SmartAI") -> ServiceResult:
        rows = self._candidate_rows(result, limit)
        latest_rankings = self.state.get("latest_rankings_v148", {}) or {}
        if not isinstance(latest_rankings, dict):
            latest_rankings = {}
        latest_rankings[list_name] = rows
        self.state.set("latest_rankings_v148", latest_rankings)
        payload = {"list_name": list_name, "rows": rows, "tickers": _extract_tickers(rows)}
        self.state.set("top_picks_result", payload)
        self.storage.write_json("latest_rankings_v148.json", latest_rankings)
        self.storage.write_json("top_picks_result.json", payload)
        return _ok(payload, message=f"{len(rows)} kandidater lagret som {list_name}.")

    def get_top_picks(self, market: str = "all", limit: int = 10) -> ServiceResult:
        latest_rankings = self.state.get("latest_rankings_v148", {}) or self.storage.read_json("latest_rankings_v148.json", default={}) or {}
        rows = []
        if isinstance(latest_rankings, Mapping):
            rows = list(latest_rankings.get("TopPicks_SmartAI") or latest_rankings.get("SmartAI") or [])[: int(limit or 10)]
        items = []
        for row in rows:
            if isinstance(row, Mapping):
                items.append(TopPickItem(candidate=StockCandidate.from_mapping(row, source=str(row.get("source") or "Top Picks"))).as_dict())
        return _ok(items)


_default_top_picks_service = TopPicksService()


def get_top_picks_service(state_service=None, storage_service=None, universe_service=None) -> TopPicksService:
    if state_service is not None or storage_service is not None or universe_service is not None:
        return TopPicksService(state_service=state_service, storage_service=storage_service, universe_service=universe_service)
    return _default_top_picks_service
