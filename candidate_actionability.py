"""Candidate actionability, evidence escalation and auditable candidate passports.

The analytical ranking and permission to trade are deliberately separate.  This
module never changes a score, outcome or production gate; it explains the
decision path and prioritises read-only evidence follow-up.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence

from app_version import APP_VERSION
from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

SCHEMA_VERSION = "1.0"
PASSPORT_KEY = "candidate_actionability/passports.json"
PASSPORT_PATH = runtime_data_path("candidate_actionability", "passports.json")
MAX_EVENTS_PER_TICKER = 120
MAX_TICKERS = 500


def _now(value: str = "") -> str:
    return value or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _float(value: Any) -> float:
    try:
        number = float(value)
        return number if number == number else 0.0
    except (TypeError, ValueError):
        return 0.0


def _checksum(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_passports() -> dict[str, list[dict[str, Any]]]:
    value = read_json(PASSPORT_KEY, PASSPORT_PATH, {})
    if not isinstance(value, Mapping):
        return {}
    return {
        str(ticker).upper(): [dict(row) for row in rows if isinstance(row, Mapping)]
        for ticker, rows in value.items() if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes))
    }


def evidence_priority_tickers(limit: int = 10) -> list[str]:
    """Return repeatedly blocked former Top-3 tickers for the next bounded evidence pass."""
    ranked: list[tuple[int, str, str]] = []
    for ticker, rows in load_passports().items():
        streak = 0
        for event in reversed(rows):
            if event.get("buy_ready") or int(event.get("analysis_rank") or 9999) > 3:
                break
            streak += 1
        if streak >= 2:
            ranked.append((-streak, str((rows or [{}])[-1].get("created_at") or ""), ticker))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [ticker for _, _, ticker in ranked[:max(0, int(limit))]]


def _blockers(candidate: Mapping[str, Any]) -> list[dict[str, str]]:
    outcome = str(candidate.get("autonomy_outcome_code") or "").upper()
    action = str(candidate.get("portfolio_action") or candidate.get("decision") or "").upper()
    readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
    reentry = candidate.get("reentry_control") if isinstance(candidate.get("reentry_control"), Mapping) else {}
    blockers: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        if code not in {row["code"] for row in blockers}:
            blockers.append({"code": code, "message": message})

    if outcome == "MODERAT_KJØPSANBEFALING":
        add("MODERATE_ONLY", "Moderat analyseutfall har ikke kjøpsfullmakt")
    elif outcome != "KJØPSKANDIDAT":
        add("NOT_STRICT_BUY", f"Analyseutfallet er {outcome or 'ikke satt'}, ikke Kjøpskandidat")
    if candidate.get("valid_for_decision") is not True:
        add("INVALID_MARKET_DATA", "Markedsdata er ikke beslutningsgyldige")
    if candidate.get("evidence_valid_for_decision") is not True:
        add("INVALID_EVIDENCE", "Evidensgrunnlaget er ikke beslutningsgyldig")
    if action not in {"BUY", "KJØP", "BUY_ELIGIBLE"}:
        add("ACTION_NOT_BUY", f"Porteføljehandlingen er {action or 'ikke satt'}")
    if candidate.get("technical_entry_wait") is True:
        add("TECHNICAL_ENTRY_WAIT", "Teknisk inngangssignal er ikke bekreftet")
    if reentry.get("blocked"):
        add(str(reentry.get("code") or "REENTRY_QUARANTINE"), str(reentry.get("message") or "Aktiv gjenkjøpskarantene"))
    source_consensus = candidate.get("source_consensus") if isinstance(candidate.get("source_consensus"), Mapping) else {}
    if int(source_consensus.get("independent_sources") or 0) == 0 and candidate.get("evidence_valid_for_decision") is not True:
        add("NO_INDEPENDENT_SOURCE", "Ingen uavhengig beslutningskilde er dokumentert")
    for value in candidate.get("blockers") or []:
        text = str(value).strip()
        if text:
            add("EXISTING_GATE", text)
    return blockers


def build_actionability(
    run: MutableMapping[str, Any], *, previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach dual rankings and a no-buy receipt to each candidate."""
    candidates = [row for row in (run.get("candidates") or []) if isinstance(row, MutableMapping)]
    passports = load_passports()
    created_at = _now(str(run.get("created_at") or ""))
    report_id = str(run.get("run_id") or run.get("report_id") or "")
    sorted_rows = sorted(candidates, key=lambda row: (-_float(row.get("investment_score") or row.get("score")), str(row.get("ticker") or "")))
    analysis_top: list[dict[str, Any]] = []
    buy_ready: list[dict[str, Any]] = []
    escalations: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for rank, candidate in enumerate(sorted_rows, 1):
        ticker = str(candidate.get("ticker") or "").upper()
        blockers = _blockers(candidate)
        final_ready = bool(candidate.get("final_decision_ready") is True and not blockers)
        history = list(passports.get(ticker) or [])
        previous_blocked = 0
        first_blocked_at = created_at
        for event in reversed(history):
            if event.get("buy_ready"):
                break
            previous_blocked += 1
            first_blocked_at = str(event.get("created_at") or first_blocked_at)
        blocked_reports = previous_blocked + (0 if final_ready else 1)
        stalled = bool(not final_ready and rank <= 3 and blocked_reports >= 3)
        actionability = {
            "schema_version": SCHEMA_VERSION,
            "ticker": ticker,
            "analysis_rank": rank,
            "attractiveness_score": round(_float(candidate.get("investment_score") or candidate.get("score")), 2),
            "analysis_status": "ATTRAKTIV" if rank <= 3 else "RANGERT",
            "buy_ready": final_ready,
            "trade_authority": "JA" if final_ready else "NEI",
            "execution_status": "KJØPSKLAR" if final_ready else ("STALLED_EVIDENCE" if stalled else "BLOKKERT"),
            "blockers": blockers,
            "blocker_codes": [row["code"] for row in blockers],
            "blocked_report_count": blocked_reports,
            "first_blocked_at": first_blocked_at if not final_ready else "",
            "last_checked_at": created_at,
            "next_check": "NESTE CRON-KJØRING" if not final_ready else "ORDRELAGETS SLUTTKONTROLL",
            "evidence_priority": "KRITISK" if stalled else "HØY" if rank <= 3 and not final_ready else "NORMAL",
            "reentry_control": deepcopy(candidate.get("reentry_control") or {}),
        }
        actionability["receipt_sha256"] = _checksum(actionability)
        candidate["actionability"] = actionability
        candidate["analysis_rank"] = rank
        candidate["buy_ready"] = final_ready
        candidate["trade_authority_label"] = actionability["trade_authority"]
        receipts.append(actionability)
        compact = {"ticker": ticker, "rank": rank, "score": actionability["attractiveness_score"],
                   "status": actionability["execution_status"], "blocker_codes": actionability["blocker_codes"]}
        if len(analysis_top) < 3:
            analysis_top.append(compact)
        if final_ready and len(buy_ready) < 3:
            buy_ready.append(compact)
        if not final_ready and rank <= 3:
            escalations.append({
                **compact, "priority": actionability["evidence_priority"],
                "attempt": "PRIMÆRKILDE → GODKJENT ALTERNATIV KILDE → NY KONTROLL",
                "next_check": actionability["next_check"], "blocked_report_count": blocked_reports,
            })
    payload = {
        "schema_version": SCHEMA_VERSION, "version": APP_VERSION, "report_id": report_id,
        "created_at": created_at, "analysis_top3": analysis_top, "buy_ready_top3": buy_ready,
        "buy_ready_count": sum(bool(row.get("buy_ready")) for row in receipts),
        "blocked_count": sum(not bool(row.get("buy_ready")) for row in receipts),
        "evidence_escalations": escalations,
        "status": "OK" if buy_ready else "INGEN KJØPSKLARE KANDIDATER",
        "production_rules_changed": False, "trade_authorized": False,
    }
    payload["control_sha256"] = _checksum(payload)
    run["candidate_actionability"] = payload
    return payload


def commit_candidate_passports(run: Mapping[str, Any]) -> dict[str, Any]:
    """Persist one immutable, idempotent receipt per ticker and report."""
    passports = load_passports()
    actionability = run.get("candidate_actionability") if isinstance(run.get("candidate_actionability"), Mapping) else {}
    report_id = str(run.get("run_id") or run.get("report_id") or actionability.get("report_id") or "")
    created_at = str(run.get("created_at") or actionability.get("created_at") or _now())
    written = duplicates = 0
    for candidate in run.get("candidates") or []:
        if not isinstance(candidate, Mapping) or not isinstance(candidate.get("actionability"), Mapping):
            continue
        ticker = str(candidate.get("ticker") or "").upper()
        rows = list(passports.get(ticker) or [])
        if any(str(row.get("report_id") or "") == report_id for row in rows):
            duplicates += 1
            continue
        state = dict(candidate["actionability"])
        event = {
            "report_id": report_id, "created_at": created_at, "program_version": APP_VERSION,
            "analysis_rank": state.get("analysis_rank"), "score": state.get("attractiveness_score"),
            "buy_ready": bool(state.get("buy_ready")), "execution_status": state.get("execution_status"),
            "blocker_codes": list(state.get("blocker_codes") or []),
            "reentry_control": deepcopy(state.get("reentry_control") or {}),
        }
        event["event_sha256"] = _checksum(event)
        rows.append(event)
        passports[ticker] = rows[-MAX_EVENTS_PER_TICKER:]
        written += 1
    if len(passports) > MAX_TICKERS:
        ordered = sorted(passports, key=lambda ticker: str((passports[ticker] or [{}])[-1].get("created_at") or ""), reverse=True)
        passports = {ticker: passports[ticker] for ticker in ordered[:MAX_TICKERS]}
    write_json(PASSPORT_KEY, PASSPORT_PATH, passports)
    return {"status": "COMPLETED", "written": written, "duplicates": duplicates, "ticker_count": len(passports)}


__all__ = ["build_actionability", "commit_candidate_passports", "evidence_priority_tickers", "load_passports"]
