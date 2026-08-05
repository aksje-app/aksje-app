"""Deterministic, offline decision replay for RC16.

Replay consumes only stored report input. It never enriches data, writes
portfolio state, sends notifications, or executes trades. The original stored
decision is compared with the current portfolio-decision gateway.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping


def _original_action(candidate: Mapping[str, Any]) -> str:
    portfolio = candidate.get("portfolio_decision") if isinstance(candidate.get("portfolio_decision"), Mapping) else {}
    return str(candidate.get("portfolio_action") or portfolio.get("action") or candidate.get("autonomy_outcome") or candidate.get("status") or "UNKNOWN")


def _candidate_context(run: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("portfolio_context", "portfolio_snapshot"):
        value = run.get(key)
        if isinstance(value, Mapping) and value:
            # A raw portfolio snapshot without persisted limits is not enough
            # for deterministic replay and must not be combined with today's
            # production configuration.
            if key == "portfolio_snapshot" and "limits" not in value:
                return None
            return value
    execution = run.get("autonomy_execution") if isinstance(run.get("autonomy_execution"), Mapping) else {}
    value = execution.get("portfolio_context")
    return value if isinstance(value, Mapping) and value else None


def replay_report(run: Mapping[str, Any]) -> dict[str, Any]:
    from autonomi_core.portfolio_decisions.layer import assess_candidate

    context = _candidate_context(run)
    rows = [item for item in (run.get("candidates") or []) if isinstance(item, Mapping)]
    report_id = str(run.get("report_id") or run.get("run_id") or "UNKNOWN")
    if context is None:
        return {
            "report_id": report_id,
            "status": "UNAVAILABLE",
            "reason": "PORTFOLIO_CONTEXT_MISSING",
            "candidate_count": len(rows),
            "results": [],
        }
    results = []
    for source in rows:
        candidate = copy.deepcopy(dict(source))
        original = _original_action(candidate)
        try:
            decision = assess_candidate(candidate, copy.deepcopy(dict(context)))
            current = str(decision.get("action") or "UNKNOWN")
            results.append({
                "report_id": report_id,
                "run_id": run.get("run_id"),
                "ticker": candidate.get("ticker"),
                "market": candidate.get("market"),
                "investment_score": candidate.get("investment_score"),
                "original_action": original,
                "rc16_action": current,
                "changed": original != current,
                "first_blocker_code": decision.get("first_blocker_code") or "",
                "blocker_codes": decision.get("blocker_codes") or [],
                "reason": decision.get("reason") or "",
                "gates": decision.get("gates") or {},
                "thresholds": decision.get("thresholds") or {},
            })
        except Exception as exc:
            results.append({
                "report_id": report_id,
                "run_id": run.get("run_id"),
                "ticker": candidate.get("ticker"),
                "market": candidate.get("market"),
                "investment_score": candidate.get("investment_score"),
                "original_action": original,
                "rc16_action": "ERROR",
                "changed": False,
                "first_blocker_code": "REPLAY_ERROR",
                "blocker_codes": ["REPLAY_ERROR"],
                "reason": str(exc),
                "gates": {},
                "thresholds": {},
            })
    return {
        "report_id": report_id,
        "status": "COMPLETED",
        "candidate_count": len(results),
        "changed_count": sum(bool(row.get("changed")) for row in results),
        "results": results,
    }


def summarize_replays(reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [row for report in reports for row in (report.get("results") or []) if isinstance(row, Mapping)]
    original = Counter(str(row.get("original_action") or "UNKNOWN") for row in rows)
    current = Counter(str(row.get("rc16_action") or "UNKNOWN") for row in rows)
    blockers = Counter(str(row.get("first_blocker_code") or "NONE") for row in rows)
    unresolved = [row for row in rows if str(row.get("rc16_action")) in {"ERROR", "UNKNOWN"} or (str(row.get("rc16_action")) != "BUY" and not str(row.get("first_blocker_code") or ""))]
    return {
        "reports_total": len(reports),
        "reports_completed": sum(str(report.get("status")) == "COMPLETED" for report in reports),
        "reports_unavailable": sum(str(report.get("status")) != "COMPLETED" for report in reports),
        "candidates_replayed": len(rows),
        "changed_decisions": sum(bool(row.get("changed")) for row in rows),
        "original_actions": dict(sorted(original.items())),
        "rc16_actions": dict(sorted(current.items())),
        "first_blockers": dict(sorted(blockers.items())),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
    }
