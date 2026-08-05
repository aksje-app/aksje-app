#!/usr/bin/env python3
"""Historical purchase-chain replay without producing PDF reports.

Accepts report JSON files, directories or ZIP report bundles.  The audit keeps
production parameters unchanged and separates analytical blockers from
Autonomis simulated-portfolio execution blockers.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

ANALYTICAL_GATE_KEYS = {
    "mission_eligible",
    "valid_for_decision",
    "evidence_valid_for_decision",
    "technical_timing",
    "score",
    "data_quality",
    "risk",
    "price",
}
EXECUTION_GATE_KEYS = {
    "portfolio_active",
    "position_capacity",
    "addition_policy",
    "portfolio_layer_buy",
    "autonomy_outcome_buy",
}


def _json_documents(path: Path) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if path.is_dir():
        for child in sorted(path.rglob("*.json")):
            yield from _json_documents(child)
        return
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith(".json"):
                    continue
                try:
                    value = json.loads(archive.read(name).decode("utf-8"))
                except Exception:
                    continue
                if isinstance(value, Mapping) and (value.get("run_id") or value.get("candidates")):
                    yield f"{path.name}:{name}", value
        return
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(value, Mapping) and (value.get("run_id") or value.get("candidates")):
            yield str(path), value


def _walk_statuses(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in {"status", "coverage", "state"} and isinstance(item, str):
                yield item.upper()
            yield from _walk_statuses(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_statuses(item)


def _candidate_rows(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    funnel = run.get("decision_funnel") if isinstance(run.get("decision_funnel"), Mapping) else {}
    rows = [row for row in (funnel.get("candidates") or []) if isinstance(row, Mapping)]
    if rows:
        return rows
    return [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]


def _analysis_result(row: Mapping[str, Any]) -> tuple[bool, list[str]]:
    if row.get("analytical_recommendation"):
        passed = str(row.get("analytical_recommendation")) == "BUY_RECOMMENDED"
        reasons = [str(x) for x in (row.get("analytical_reasons") or [])]
        return passed, reasons
    gates = row.get("analytical_gates") if isinstance(row.get("analytical_gates"), Mapping) else row.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    relevant = {key: bool(value) for key, value in gates.items() if key in ANALYTICAL_GATE_KEYS}
    if not relevant:
        # Legacy fallback: only count as analytical recommendation when the
        # independent score/evidence/data/risk fields explicitly pass.
        score = float(row.get("score") or row.get("investment_score") or 0)
        threshold = float(row.get("production_threshold") or 78)
        passed = score >= threshold and row.get("valid_for_decision") is True and row.get("evidence_valid_for_decision") is True
        return passed, [] if passed else ["legacy_fields_not_sufficient"]
    failed = [key for key, value in relevant.items() if not value]
    return not failed, failed


def _execution_result(row: Mapping[str, Any], analytical_buy: bool) -> tuple[str, list[str]]:
    explicit = str(row.get("trade_execution_status") or "")
    if explicit:
        return explicit, [str(x) for x in (row.get("trade_reasons") or [])]
    gates = row.get("execution_gates") if isinstance(row.get("execution_gates"), Mapping) else row.get("gates")
    gates = gates if isinstance(gates, Mapping) else {}
    execution = {key: bool(value) for key, value in gates.items() if key in EXECUTION_GATE_KEYS}
    failed = [key for key, value in execution.items() if not value]
    if not analytical_buy:
        return "NOT_ANALYTICALLY_RECOMMENDED", failed
    if any(key in failed for key in ("portfolio_active", "position_capacity", "addition_policy")):
        return "BLOCKED_AUTONOMY_PORTFOLIO", failed
    if failed:
        return "BLOCKED_PRODUCTION_DECISION_CHAIN", failed
    return "EXECUTABLE", []


def audit(paths: list[Path]) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    market_counts: Counter[str] = Counter()
    analytical_blockers: Counter[str] = Counter()
    execution_blockers: Counter[str] = Counter()
    execution_statuses: Counter[str] = Counter()
    not_searched = 0
    all_candidates = 0
    analytical_buys = 0
    executable = 0
    portfolio_blocked = 0
    capacity_blocked = 0
    over_threshold = 0

    seen: set[str] = set()
    for path in paths:
        for source, run in _json_documents(path):
            run_id = str(run.get("run_id") or source)
            if run_id in seen:
                continue
            seen.add(run_id)
            markets = [str(x) for x in (run.get("markets") or [])]
            for market in markets:
                market_counts[market] += 1
            rows = _candidate_rows(run)
            highest = max((float(row.get("score") or row.get("investment_score") or 0) for row in rows), default=0.0)
            threshold = float((run.get("decision_funnel") or {}).get("production_threshold") or 78)
            run_analytical = 0
            run_executable = 0
            run_portfolio_blocked = 0
            for row in rows:
                all_candidates += 1
                score = float(row.get("score") or row.get("investment_score") or 0)
                if score >= float(row.get("production_threshold") or threshold):
                    over_threshold += 1
                analytical_buy, analytical_reasons = _analysis_result(row)
                if analytical_buy:
                    analytical_buys += 1
                    run_analytical += 1
                else:
                    for reason in analytical_reasons:
                        analytical_blockers[str(reason)] += 1
                execution_status, trade_reasons = _execution_result(row, analytical_buy)
                execution_statuses[execution_status] += 1
                if execution_status == "EXECUTABLE":
                    executable += 1
                    run_executable += 1
                if execution_status == "BLOCKED_AUTONOMY_PORTFOLIO":
                    portfolio_blocked += 1
                    run_portfolio_blocked += 1
                for reason in trade_reasons:
                    execution_blockers[str(reason)] += 1
                    if str(reason) == "position_capacity" or "posisjon" in str(reason).lower():
                        capacity_blocked += 1
            run_not_searched = sum(1 for status in _walk_statuses(run.get("candidates") or []) if status == "NOT_SEARCHED")
            not_searched += run_not_searched
            runs.append({
                "run_id": run_id,
                "source": source,
                "app_version": run.get("app_version") or (run.get("report_metadata") or {}).get("app_version"),
                "markets": markets,
                "market_profile": run.get("market_profile"),
                "candidate_count": len(rows),
                "highest_score": round(highest, 2),
                "production_threshold": threshold,
                "candidates_at_or_above_threshold": sum(float(row.get("score") or row.get("investment_score") or 0) >= float(row.get("production_threshold") or threshold) for row in rows),
                "analytical_buy_recommendations": run_analytical,
                "trade_executable": run_executable,
                "portfolio_blocked_buy_recommendations": run_portfolio_blocked,
                "not_searched_statuses": run_not_searched,
            })

    return {
        "schema": "purchase-chain-audit-v19.22.0-rc9",
        "mode": "DIAGNOSTIC_ONLY",
        "production_parameters_changed": False,
        "reports_analyzed": len(runs),
        "candidate_rows_analyzed": all_candidates,
        "market_run_counts": dict(market_counts),
        "candidates_at_or_above_production_threshold": over_threshold,
        "analytical_buy_recommendations": analytical_buys,
        "trade_executable": executable,
        "portfolio_blocked_buy_recommendations": portfolio_blocked,
        "position_capacity_block_events": capacity_blocked,
        "not_searched_statuses": not_searched,
        "analytical_blockers": dict(analytical_blockers),
        "execution_blockers": dict(execution_blockers),
        "execution_statuses": dict(execution_statuses),
        "runs": runs,
        "interpretation": (
            "Analytisk anbefaling måles uten Autonomis porteføljekapasitet. "
            "Handelsstatus måles separat og endrer ikke produksjonsreglene."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("reports_analyzed", "candidate_rows_analyzed", "analytical_buy_recommendations", "trade_executable", "portfolio_blocked_buy_recommendations")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
