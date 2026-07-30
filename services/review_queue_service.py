from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from paper_store import load_portfolio, save_portfolio

VALID_STATUSES = {"ÅPEN", "GODKJENT", "AVVIST", "KJØPT"}


class ReviewQueueService:
    def _load(self) -> Dict[str, Any]:
        portfolio = load_portfolio() or {}
        portfolio.setdefault("review_queue", [])
        return portfolio

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        queue = self._load().get("review_queue", []) or []
        rows = [deepcopy(row) for row in queue if isinstance(row, dict)]
        if status:
            status = str(status).upper()
            rows = [row for row in rows if str(row.get("status", "ÅPEN")).upper() == status]
        return rows

    def add(self, item: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        portfolio = self._load()
        queue = portfolio["review_queue"]
        symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
        asset_type = str(item.get("asset_type") or "Aksje")
        if not symbol:
            return False, "Ticker mangler", {}
        for row in queue:
            if str(row.get("symbol") or row.get("ticker") or "").upper() == symbol and str(row.get("asset_type") or "Aksje") == asset_type and str(row.get("status") or "ÅPEN").upper() in {"ÅPEN", "GODKJENT"}:
                row.update({k: v for k, v in item.items() if v not in (None, "")})
                row["updated_at"] = datetime.now().isoformat(timespec="seconds")
                save_portfolio(portfolio)
                return True, "Eksisterende vurdering oppdatert", deepcopy(row)
        record = dict(item)
        record.setdefault("symbol", symbol)
        record.setdefault("ticker", symbol)
        record.setdefault("status", "ÅPEN")
        record.setdefault("note", "")
        record.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        record["updated_at"] = record["created_at"]
        queue.insert(0, record)
        portfolio["review_queue"] = queue[:500]
        save_portfolio(portfolio)
        return True, "Lagt til manuell vurdering", deepcopy(record)

    def update(self, symbol: str, *, status: Optional[str] = None, note: Optional[str] = None, asset_type: str = "Aksje") -> Tuple[bool, str]:
        portfolio = self._load()
        symbol = str(symbol or "").strip().upper()
        for row in portfolio["review_queue"]:
            row_symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
            if row_symbol == symbol and str(row.get("asset_type") or "Aksje") == asset_type:
                if status is not None:
                    normalized = str(status).upper()
                    if normalized not in VALID_STATUSES:
                        return False, f"Ugyldig status: {status}"
                    row["status"] = normalized
                if note is not None:
                    row["note"] = str(note)
                row["updated_at"] = datetime.now().isoformat(timespec="seconds")
                save_portfolio(portfolio)
                return True, "Vurdering oppdatert"
        return False, "Vurdering ikke funnet"


_default_review_queue_service = ReviewQueueService()


def get_review_queue_service() -> ReviewQueueService:
    return _default_review_queue_service
