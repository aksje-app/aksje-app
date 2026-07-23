"""Verification contract for one self-contained Autonomy execution (v18.9.2)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


VERSION = "v18.9.2"
STAGES = (
    (1, "PORTFOLIO_NEEDS", "Leser porteføljebehov"),
    (2, "MISSION", "Oppretter oppdrag"),
    (3, "DISCOVERY_DATA", "Oppdaterer univers og datakilder"),
    (4, "CANDIDATES", "Finner nye og etablerte kandidater"),
    (5, "ANALYSIS", "Utfører analyse"),
    (6, "MULTI_STRATEGY_RANKING", "Rangerer etter flere strategier"),
    (7, "CANONICAL_TOP_PICKS", "Oppdaterer Top Picks"),
    (8, "PORTFOLIO_RISK", "Kontrollerer porteføljerisiko"),
    (9, "THEORETICAL_DECISIONS", "Lager teoretiske beslutninger"),
    (10, "DASHBOARD", "Oppdaterer Dashboard"),
    (11, "REPORT", "Genererer rapport"),
    (12, "NOTIFICATIONS", "Sender varsler"),
    (13, "HISTORY_LEARNING", "Lagrer historikk og læringsgrunnlag"),
)


def _stage(number: int, code: str, label: str, status: str, evidence: Any) -> dict[str, Any]:
    return {"number": number, "code": code, "label": label, "status": status, "evidence": evidence}


def build_full_execution_receipt(run: Mapping[str, Any]) -> dict[str, Any]:
    """Derive a fail-closed receipt from actual outputs of the single run."""
    portfolio = dict(run.get("portfolio_decisions") or {})
    context = dict(portfolio.get("portfolio_context") or {})
    preflight = dict(run.get("portfolio_need_preflight") or {})
    mission_id = str(run.get("mission_id") or (run.get("investment_mission") or {}).get("mission_id") or "")
    discovery = dict(run.get("discovery_data") or {})
    candidates = [x for x in run.get("candidates") or [] if isinstance(x, Mapping)]
    analyzed = [x for x in candidates if x.get("analysis_ranking") or x.get("investment_score") is not None]
    multi = [x for x in candidates if x.get("strategy_scores") or x.get("strategy_matches")]
    top = dict(run.get("canonical_top_picks") or {})
    decisions = list(portfolio.get("decisions") or [])
    chain = dict(run.get("autonomous_chain") or {})
    chain_stages = {str(x.get("name")): str(x.get("status")) for x in chain.get("stages") or [] if isinstance(x, Mapping)}
    decision_stage = chain_stages.get("AUTONOMOUS_PORTFOLIO", "")
    persistence = dict(run.get("persistence") or {})
    notification = dict(run.get("notification") or {})
    learning = dict(run.get("historical_learning") or {})
    canonical = dict(run.get("canonical_result") or {})
    pdf_delivery = dict(run.get("pdf_delivery") or {})
    report_ok = bool(
        persistence.get("ok")
        and (
            not pdf_delivery.get("required")
            or (pdf_delivery.get("generated") and pdf_delivery.get("validated") and pdf_delivery.get("published"))
        )
    )

    rows = [
        _stage(1, *STAGES[0][1:], "OK" if preflight.get("read_at") and preflight.get("context") else "FAILED", {"read_at": preflight.get("read_at"), "source": preflight.get("source"), "positions": preflight.get("position_count", 0), "needs": preflight.get("needs", [])}),
        _stage(2, *STAGES[1][1:], "OK" if mission_id else "FAILED", {"mission_id": mission_id, "configuration_version": run.get("configuration_version")}),
        _stage(3, *STAGES[2][1:], "OK" if discovery.get("markets") or run.get("market_runs") else "FAILED", {"markets": run.get("markets"), "selected": discovery.get("selected", 0)}),
        _stage(4, *STAGES[3][1:], "OK" if candidates else "FAILED", {"candidates": len(candidates), "new": len((run.get("changes") or {}).get("new", []))}),
        _stage(5, *STAGES[4][1:], "OK" if analyzed else "FAILED", {"analyzed": len(analyzed)}),
        _stage(6, *STAGES[5][1:], "OK" if multi else "FAILED", {"multi_strategy_candidates": len(multi)}),
        _stage(7, *STAGES[6][1:], "OK" if top.get("published") else "FAILED", {"result_id": top.get("result_id"), "top_picks": len(top.get("top_picks") or [])}),
        _stage(8, *STAGES[7][1:], "OK" if decisions and all(x.get("portfolio_assessed") for x in decisions) else "FAILED", {"decisions": len(decisions), "actions": portfolio.get("actions")}),
        _stage(9, *STAGES[8][1:], "OK" if chain.get("status") == "OK" and decision_stage in {"OK", "SKIPPED"} else "FAILED", {"status": chain.get("status"), "decision_stage": decision_stage, "execution": chain.get("execution", "THEORETICAL_ONLY")}),
        _stage(10, *STAGES[9][1:], "OK" if top.get("published") else "FAILED", {"source": "CANONICAL_TOP_PICKS", "result_id": top.get("result_id")}),
        _stage(11, *STAGES[10][1:], "OK" if report_ok else "FAILED", {
            "archive": persistence.get("archive_saved"), "json": persistence.get("run_json_saved"),
            "pdf": run.get("pdf_path"), "pdf_delivery": pdf_delivery,
        }),
        _stage(12, *STAGES[11][1:], ("OK" if notification.get("sent") else ("FAILED" if notification.get("required") and not any(token in str(notification.get("detail") or "") for token in ("Ingen feil", "Ingen kvalifiserende", "deaktivert")) else "SKIPPED_POLICY")), {"sent": notification.get("sent", False), "required": notification.get("required", False), "detail": notification.get("detail")}),
        _stage(13, *STAGES[12][1:], "OK" if canonical.get("stored_once") and "snapshots_created" in learning and not learning.get("error") else "FAILED", {"result_id": canonical.get("result_id"), "snapshots": learning.get("snapshots_created"), "error": learning.get("error")}),
    ]
    failed = [row for row in rows if row["status"] == "FAILED"]
    return {
        "version": VERSION, "run_id": run.get("run_id"), "mission_id": mission_id,
        "completed_at": datetime.now(timezone.utc).isoformat(), "stages": rows,
        "completed_steps": sum(row["status"] != "FAILED" for row in rows),
        "total_steps": len(rows), "status": "COMPLETED" if not failed else "INCOMPLETE",
        "self_contained": not failed, "manual_dependencies": [],
        "approval_rule": "Ingen annen modul må kjøres manuelt før eller etter Autonomi",
        "failed_stages": [row["code"] for row in failed], "theoretical_only": True,
    }


def execution_manifest() -> dict[str, Any]:
    return {"version": VERSION, "stages": [{"number": n, "code": c, "label": l} for n, c, l in STAGES], "manual_dependencies": []}


def prepublication_gate(run: Mapping[str, Any]) -> dict[str, Any]:
    """Validate every prerequisite before canonical Top Picks may change."""
    shadow = dict(run)
    shadow["canonical_top_picks"] = {
        "published": True, "result_id": (run.get("canonical_result") or {}).get("result_id"), "top_picks": [],
    }
    receipt = build_full_execution_receipt(shadow)
    failed = [code for code in receipt.get("failed_stages") or [] if code not in {"CANONICAL_TOP_PICKS", "DASHBOARD"}]
    return {"ok": not failed, "failed_stages": failed}
