"""Canonical Top Picks publisher for successful Autonomy runs (v18.9.1)."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from services.storage_service import get_storage_service


VERSION = "v18.9.1"
ROOT = Path(__file__).resolve().parents[2] / ".app_runtime" / "data" / "autonomi_core"
LATEST_KEY = "autonomi_core/canonical_top_picks/latest_valid.json"
LATEST_PATH = ROOT / "canonical_top_picks" / "latest_valid.json"
_PUBLISH_LOCK = threading.RLock()


def load_canonical_top_picks() -> dict[str, Any]:
    value = read_json(LATEST_KEY, LATEST_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or "").strip().upper()


def _quality(row: Mapping[str, Any]) -> Any:
    contract = dict(row.get("data_contract") or {})
    return contract.get("quality") or contract.get("data_quality") or row.get("data_quality") or row.get("data_quality_score")


def _why(row: Mapping[str, Any]) -> str:
    decision = dict(row.get("portfolio_decision") or {})
    analysis = dict(row.get("analysis_ranking") or {})
    reasons = decision.get("reasons") or decision.get("reason") or analysis.get("summary") or row.get("recommendation_reason") or row.get("why")
    if isinstance(reasons, (list, tuple)):
        return "; ".join(str(x) for x in reasons if x)
    return str(reasons or "Valgt av oppdragsstyrt analyse, datakontroll og porteføljevurdering")


def _strategy(row: Mapping[str, Any]) -> str:
    matches = row.get("strategy_matches") or []
    if isinstance(matches, (list, tuple)) and matches:
        return ", ".join(str(x) for x in matches)
    return str(row.get("strategy_match") or row.get("strategy") or "Ikke klassifisert")


def _successful(payload: Mapping[str, Any]) -> tuple[bool, str]:
    if bool(payload.get("analysis_aborted")):
        return False, "Analysen ble avbrutt"
    status = str(payload.get("completion_status") or "").upper()
    if status not in {"FULLFØRT", "FULLFØRT MED MARKEDSFEIL"}:
        return False, f"Ikke vellykket sluttstatus: {status or 'MANGLER'}"
    chain_status = str((payload.get("autonomous_chain") or {}).get("status") or "OK").upper()
    if chain_status in {"ERROR", "FAILED", "COMPLETED_WITH_ERRORS"}:
        return False, f"Autonomi-kjeden feilet: {chain_status}"
    validation = dict(payload.get("validation") or {})
    if validation.get("valid_for_ranking") is False:
        return False, "Resultatet er ikke gyldig for rangering"
    candidates = [x for x in payload.get("candidates") or [] if isinstance(x, Mapping)]
    if not any(bool(x.get("valid_for_decision", True)) for x in candidates):
        return False, "Ingen beslutningsgyldige kandidater"
    return True, "OK"


def build_canonical_top_picks(record: Mapping[str, Any], previous: Mapping[str, Any] | None = None, *, limit: int = 30) -> dict[str, Any]:
    payload = dict(record.get("payload") or {})
    ok, reason = _successful(payload)
    if not ok:
        return {"published": False, "reason": reason, "preserved_result_id": (previous or {}).get("result_id")}
    previous = dict(previous or {})
    previous_rows = {_ticker(x): dict(x) for x in previous.get("full_ranking") or [] if isinstance(x, Mapping) and _ticker(x)}
    ranked = sorted(
        [deepcopy(dict(x)) for x in payload.get("candidates") or [] if isinstance(x, Mapping) and _ticker(x)],
        key=lambda x: float(x.get("investment_score") or 0), reverse=True,
    )
    current_tickers = {_ticker(x) for x in ranked}
    previous_tickers = set(previous_rows)
    enriched = []
    for rank, row in enumerate(ranked, 1):
        ticker = _ticker(row)
        prior = previous_rows.get(ticker, {})
        prior_score = prior.get("investment_score")
        delta = None if prior_score is None else round(float(row.get("investment_score") or 0) - float(prior_score or 0), 2)
        row.update({
            "rank": rank, "mission_id": payload.get("mission_id"),
            "canonical_result_id": record.get("result_id"), "run_id": record.get("run_id"),
            "selected_at": payload.get("created_at_local") or payload.get("created_at"),
            "strategy": _strategy(row), "canonical_data_quality": _quality(row),
            "selection_reason": _why(row), "score_delta_since_previous": delta,
            "candidate_state": "GJENTATT" if ticker in previous_tickers else "NY",
        })
        enriched.append(row)
    top = [x for x in enriched if bool(x.get("valid_for_decision", True)) and str(x.get("portfolio_action") or "").upper() not in {"SKIP", "SELL"}][:max(1, int(limit))]
    buy_now = [x for x in top if str(x.get("portfolio_action") or "").upper() == "BUY"]
    dropped = [{**previous_rows[t], "candidate_state": "FALT UT", "dropped_at": payload.get("created_at_local") or payload.get("created_at")} for t in sorted(previous_tickers - current_tickers)]
    return {
        "published": True, "version": VERSION, "result_id": record.get("result_id"),
        "run_id": record.get("run_id"), "mission_id": payload.get("mission_id"),
        "configuration_version": payload.get("configuration_version"),
        "created_at": payload.get("created_at"), "created_at_local": payload.get("created_at_local"),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "full_ranking": enriched, "top_picks": top, "buy_now": buy_now,
        "new_candidates": [x for x in enriched if x["candidate_state"] == "NY"],
        "repeated_candidates": [x for x in enriched if x["candidate_state"] == "GJENTATT"],
        "dropped_candidates": dropped,
        "portfolio_proposal": deepcopy(payload.get("portfolio_proposal") or {}),
        "source_content_hash": record.get("content_hash"),
    }


def publish_canonical_top_picks(record: Mapping[str, Any], *, limit: int = 30) -> dict[str, Any]:
    """Publish atomically. Invalid runs return diagnostics and preserve latest."""
    with _PUBLISH_LOCK:
        previous = load_canonical_top_picks()
        package = build_canonical_top_picks(record, previous, limit=limit)
        if not package.get("published"):
            return package
        if str(previous.get("created_at") or "") > str(package.get("created_at") or ""):
            return {"published": False, "reason": "Et nyere gyldig resultat er allerede publisert", "preserved_result_id": previous.get("result_id")}
        write_json(LATEST_KEY, LATEST_PATH, package)
        storage = get_storage_service()
        # Compatibility projections. All old surfaces now read the same rows.
        rankings = storage.read_json("latest_rankings_v148.json", default={}) or {}
        rankings = dict(rankings) if isinstance(rankings, Mapping) else {}
        rankings["TopPicks_Canonical"] = package["top_picks"]
        rankings["TopPicks_SmartAI"] = package["top_picks"]
        rankings["Canonical_Full_Ranking"] = package["full_ranking"]
        storage.write_json("latest_rankings_v148.json", rankings)
        storage.write_json("top_picks_result.json", {
            "list_name": "TopPicks_Canonical", "rows": package["top_picks"],
            "tickers": [_ticker(x) for x in package["top_picks"]],
            "result_id": package["result_id"], "mission_id": package["mission_id"],
        })
        storage.write_json("canonical_buy_now.json", package["buy_now"])
        storage.write_json("canonical_portfolio_proposal.json", package["portfolio_proposal"])
        return package
