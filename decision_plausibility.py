"""Cross-run plausibility audit for decision and learning outputs.

This layer never authorizes trades or changes parameters. It makes persistent,
economically illogical behaviour visible and blocks contradictory outputs.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (value or []) if isinstance(row, Mapping)]


def _buy_tickers(run: Mapping[str, Any]) -> set[str]:
    return {
        str(row.get("ticker") or "").upper()
        for row in _rows(run.get("candidates"))
        if str(row.get("autonomy_outcome_code") or "").upper() == "KJØPSKANDIDAT"
        and str(row.get("portfolio_action") or "").upper() in {"BUY", "KJØP"}
        and row.get("final_decision_ready") is not False
    }


def _production_buys(run: Mapping[str, Any]) -> set[str]:
    chain = run.get("autonomous_chain") if isinstance(run.get("autonomous_chain"), Mapping) else {}
    for stage in chain.get("stages") or []:
        if isinstance(stage, Mapping) and str(stage.get("name") or "").upper() == "AUTONOMOUS_PORTFOLIO":
            detail = stage.get("detail") if isinstance(stage.get("detail"), Mapping) else {}
            return {str(value or "").upper() for value in detail.get("buy_tickers") or [] if value}
    return set()


def _learning_detail(run: Mapping[str, Any]) -> dict[str, Any]:
    chain = run.get("autonomous_chain") if isinstance(run.get("autonomous_chain"), Mapping) else {}
    for stage in chain.get("stages") or []:
        if isinstance(stage, Mapping) and str(stage.get("name") or "").upper() == "CONTROLLED_LEARNING":
            return dict(stage.get("detail") or {})
    return {}


def audit_decision_plausibility(
    run: Mapping[str, Any], previous_runs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates = _rows(run.get("candidates"))
    report_buys = _buy_tickers(run)
    production_buys = _production_buys(run)
    errors: list[str] = []
    warnings: list[str] = []
    unexplained_production_buys = production_buys - report_buys
    if unexplained_production_buys:
        errors.append(
            "Autonomi registrerte teoretiske porteføljekjøp uten tilsvarende klar rapportanbefaling: "
            + ", ".join(sorted(unexplained_production_buys))
        )

    learning = _learning_detail(run)
    evaluation = dict(learning.get("evaluation") or {})
    usable = int(evaluation.get("ordinary_closed_trades") or 0) + int(evaluation.get("learning_closed_trades") or 0)
    if learning.get("ran") and usable >= 15 and not list(evaluation.get("actions") or []):
        warnings.append(f"Kontrollert læring kjørte uten handling til tross for {usable} avsluttede utfall.")

    account = dict(run.get("autonomy_learning_account") or {})
    metrics = dict(account.get("account_metrics") or {})
    return_pct = float(metrics.get("return_pct") or 0.0)
    if abs(return_pct) > 100.0:
        errors.append(f"Læringsavkastning {return_pct:.2f}% er utenfor plausibelt regnskapsområde.")

    threshold = float((run.get("report_summary") or {}).get("production_buy_threshold") or 73.0)
    near = [row for row in candidates if threshold - 5.0 <= float(row.get("investment_score") or 0.0) < threshold]
    if candidates and not report_buys and len(near) >= max(5, len(candidates) // 5):
        warnings.append(f"Null kjøpsanbefalinger og {len(near)} kandidater samlet 0–5 poeng under terskelen {threshold:.1f}.")

    previous = [dict(row) for row in (previous_runs or []) if isinstance(row, Mapping)]
    zero_streak = 1 if candidates and not report_buys else 0
    if zero_streak:
        for old in previous:
            if _rows(old.get("candidates")) and not _buy_tickers(old):
                prior_audit = old.get("decision_plausibility") if isinstance(old.get("decision_plausibility"), Mapping) else {}
                zero_streak += max(1, int(prior_audit.get("zero_buy_streak") or 0))
            else:
                break
    if zero_streak >= 3:
        warnings.append(f"Ingen klare kjøpsanbefalinger i {zero_streak} påfølgende analyser.")

    return {
        "ok": not errors,
        "status": "ERROR" if errors else ("WARNING" if warnings else "OK"),
        "errors": errors,
        "warnings": warnings,
        "candidate_count": len(candidates),
        "report_buy_tickers": sorted(report_buys),
        "autonomy_buy_tickers": sorted(production_buys),
        "near_threshold_count": len(near),
        "zero_buy_streak": zero_streak,
        "learning_evidence_count": usable,
        "production_parameters_changed": False,
    }
