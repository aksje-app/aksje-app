"""Autonomy activation funnel and threshold simulation for v19.8.0."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from repositories.application import RepositoryRegistry, get_repository_registry

AUTONOMY_ACTIVATION_SERVICE_VERSION = "1.0"
DEFAULT_THRESHOLD_SCENARIOS = (78.0, 76.0, 74.0, 72.0, 70.0)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _analysis_id(run_id: str, created_at: str) -> str:
    return "ACT-" + hashlib.sha256(f"{run_id}|{created_at}".encode("utf-8")).hexdigest()[:20]


def classify_blocker(row: Mapping[str, Any]) -> tuple[str, str]:
    action = str(row.get("action") or row.get("decision") or "").upper()
    if action in {"BUY", "SELL", "REDUCE"} or bool(row.get("order_executed")):
        return "TRADE_EXECUTED", "Handel utført"
    reason = str(row.get("stop_reason") or row.get("reason") or row.get("rejection_reason") or "").strip()
    text = reason.lower()
    stage = str(row.get("execution_stage") or "").upper()
    patterns = (
        ("PORTFOLIO_PAUSED", ("paus", "ikke aktiv", "portfolio_paused"), "Porteføljen er pauset"),
        ("DATA_QUALITY_BELOW_THRESHOLD", ("datakvalitet", "data quality"), "Datakvalitet under minimum"),
        ("RISK_ABOVE_LIMIT", ("risiko", "risk"), "Risiko over maksimal grense"),
        ("SCORE_BELOW_THRESHOLD", ("score", "under læringsgrense"), "Score under kjøpsgrensen"),
        ("INVALID_PRICE", ("mangler gyldig markedspris", "mangler gyldig pris", "invalid price"), "Mangler gyldig pris"),
        ("MAX_OPEN_POSITIONS", ("maks antall åpne", "maximum open positions"), "Maks antall posisjoner nådd"),
        ("ALREADY_HELD", ("finnes allerede", "already", "tilleggskjøp"), "Aksjen finnes allerede i porteføljen"),
        ("INSUFFICIENT_CAPITAL_OR_SECTOR", ("utilstrekkelig kapital", "sektorrom", "insufficient cash"), "For lite kapital eller sektorrom"),
        ("SAME_CYCLE_REENTRY", ("gjeninntreden", "same decision cycle"), "Gjeninntreden blokkert i samme syklus"),
        ("NO_ORDER_INTENT", ("ordreintensjon", "order intent"), "Ordreintensjon ble ikke opprettet"),
    )
    if stage == "PORTFOLIO_PAUSED":
        return "PORTFOLIO_PAUSED", reason or "Porteføljen er pauset"
    for code, needles, label in patterns:
        if any(needle in text for needle in needles):
            # A generic score mention should not classify a positive reason.
            if code == "SCORE_BELOW_THRESHOLD" and "under" not in text and "<" not in text:
                continue
            return code, reason or label
    if not bool(row.get("sent_to_autonomy", True)):
        return "NOT_HANDED_OFF", reason or "Kandidaten ble ikke sendt til Autonomi"
    if not bool(row.get("portfolio_check_completed", True)):
        return "PORTFOLIO_CHECK_MISSING", reason or "Porteføljekontroll ble ikke fullført"
    if not bool(row.get("order_intent_created", False)):
        return "NO_ORDER_INTENT", reason or "Ordreintensjon ble ikke opprettet"
    if not bool(row.get("order_executed", False)):
        return "ORDER_NOT_EXECUTED", reason or "Ordren ble ikke utført"
    return "OTHER", reason or "Annen eller ukjent stoppårsak"


def _score_from_row(row: Mapping[str, Any]) -> float:
    return _f(row.get("score", row.get("investment_score", row.get("final_score"))))


def _quality_from_row(row: Mapping[str, Any]) -> float:
    return _f(row.get("data_quality", row.get("data_quality_score", row.get("combined_data_quality"))), 100.0)


def _risk_from_row(row: Mapping[str, Any]) -> float:
    return _f(row.get("risk", row.get("risk_score")), 0.0)


class AutonomyActivationService:
    def __init__(self, repositories: RepositoryRegistry | None = None):
        self.repositories = repositories or get_repository_registry()
        self.analyses = self.repositories.activation_analyses

    def analyse(
        self,
        decisions: Sequence[Mapping[str, Any]],
        *,
        run_id: str = "",
        parameters: Mapping[str, Any] | None = None,
        account_metrics: Sequence[Mapping[str, Any]] | None = None,
        threshold_scenarios: Sequence[float] = DEFAULT_THRESHOLD_SCENARIOS,
        persist: bool = True,
    ) -> dict[str, Any]:
        rows = [dict(row) for row in (decisions or []) if isinstance(row, Mapping)]
        if not run_id and rows:
            run_id = str(rows[0].get("run_id") or "")
        if run_id:
            current = [row for row in rows if str(row.get("run_id") or "") == run_id]
            if current:
                rows = current
        # One candidate may receive multiple ledger rows (for example HOLD then
        # already-held). The activation funnel counts unique candidates and keeps
        # the most execution-relevant/latest row for each ticker.
        unique: dict[str, dict[str, Any]] = {}
        priorities: dict[str, int] = {}
        for index, row in enumerate(rows):
            ticker = str(row.get("ticker") or f"__row_{index}").upper()
            action = str(row.get("action") or row.get("decision") or "").upper()
            priority = (
                40 if bool(row.get("order_executed")) or action in {"BUY", "SELL", "REDUCE"}
                else 30 if bool(row.get("order_intent_created"))
                else 20 if str(row.get("execution_stage") or "")
                else 10
            )
            if priority >= priorities.get(ticker, -1):
                unique[ticker] = row
                priorities[ticker] = priority
        rows = list(unique.values())
        params = dict(parameters or {})
        min_score = _f(params.get("minimum_investment_score"), 78.0)
        min_quality = _f(params.get("minimum_data_quality"), 55.0)
        max_risk = _f(params.get("maximum_risk_score"), 65.0)

        blocker_counts: Counter[str] = Counter()
        blocker_labels: dict[str, str] = {}
        candidate_rows: list[dict[str, Any]] = []
        passed_data = passed_risk = passed_score = order_intents = executed = 0
        for raw in rows:
            code, label = classify_blocker(raw)
            blocker_counts[code] += 1
            blocker_labels.setdefault(code, label)
            score = _score_from_row(raw)
            quality = _quality_from_row(raw)
            risk = _risk_from_row(raw)
            action = str(raw.get("action") or raw.get("decision") or "").upper()
            did_execute = bool(raw.get("order_executed")) or action in {"BUY", "SELL", "REDUCE"}
            has_intent = bool(raw.get("order_intent_created")) or did_execute
            if quality >= min_quality:
                passed_data += 1
            if quality >= min_quality and risk <= max_risk:
                passed_risk += 1
            if quality >= min_quality and risk <= max_risk and score >= min_score:
                passed_score += 1
            order_intents += int(has_intent)
            executed += int(did_execute)
            candidate_rows.append({
                "run_id": str(raw.get("run_id") or run_id),
                "timestamp": raw.get("timestamp") or raw.get("evaluated_at"),
                "ticker": str(raw.get("ticker") or "").upper(),
                "score": score,
                "data_quality": quality,
                "risk": risk,
                "action": action or "UNKNOWN",
                "blocker_code": code,
                "blocker_reason": label,
                "order_intent_created": has_intent,
                "order_executed": did_execute,
                "execution_stage": raw.get("execution_stage"),
                "market_snapshot_id": raw.get("market_snapshot_id"),
                "candidate_snapshot_id": raw.get("candidate_snapshot_id"),
            })

        simulations: list[dict[str, Any]] = []
        for threshold in sorted({float(x) for x in threshold_scenarios}, reverse=True):
            eligible = [r for r in candidate_rows if r["score"] >= threshold and r["data_quality"] >= min_quality and r["risk"] <= max_risk]
            simulations.append({
                "minimum_score": threshold,
                "eligible_candidates": len(eligible),
                "tickers": [r["ticker"] for r in sorted(eligible, key=lambda x: x["score"], reverse=True)[:25]],
                "hard_data_quality_gate": min_quality,
                "hard_risk_gate": max_risk,
            })

        top_blockers = [
            {"code": code, "count": count, "label": blocker_labels.get(code, code), "share_pct": round(count / len(rows) * 100, 2) if rows else 0.0}
            for code, count in blocker_counts.most_common(12)
        ]
        near_threshold = [r for r in candidate_rows if min_score - 8 <= r["score"] < min_score and r["data_quality"] >= min_quality and r["risk"] <= max_risk]
        near_threshold = sorted(near_threshold, key=lambda r: r["score"], reverse=True)
        created_at = _now()
        recommendation = "Datagrunnlaget er for lite til en parameteranbefaling."
        if rows and executed == 0:
            eligible_72 = next((s["eligible_candidates"] for s in simulations if s["minimum_score"] == 72.0), 0)
            if blocker_counts.get("PORTFOLIO_PAUSED"):
                recommendation = "Aktiver paperkontoen før terskler vurderes; porteføljestatus blokkerer læring."
            elif blocker_counts.get("SCORE_BELOW_THRESHOLD", 0) >= max(1, len(rows) // 2) and eligible_72:
                recommendation = "Behold hovedstrategiens harde porter. Test score 72 i autonomy_learning med maks 1,5 % per posisjon."
            elif order_intents == 0 and passed_score:
                recommendation = "Kandidater passerer score/risiko/data, men ordreintensjon mangler. Feilsøk overleveringen før terskler endres."
            else:
                recommendation = "Ingen handler. Bruk funnelen og simulerte terskler før en kontrollert læringsprofil godkjennes."
        elif executed:
            recommendation = "Strategien handler. Evaluer avkastning, drawdown og uenighetsresultater før parametre endres."

        analysis = {
            "analysis_id": _analysis_id(run_id or "NO-RUN", created_at),
            "created_at": created_at,
            "run_id": run_id,
            "service_version": AUTONOMY_ACTIVATION_SERVICE_VERSION,
            "parameters": {
                "minimum_investment_score": min_score,
                "minimum_data_quality": min_quality,
                "maximum_risk_score": max_risk,
                **{k: v for k, v in params.items() if k not in {"minimum_investment_score", "minimum_data_quality", "maximum_risk_score"}},
            },
            "funnel": {
                "candidates_received": len(rows),
                "passed_data_quality": passed_data,
                "passed_risk": passed_risk,
                "passed_score": passed_score,
                "order_intents_created": order_intents,
                "orders_executed": executed,
            },
            "top_blockers": top_blockers,
            "candidate_decisions": candidate_rows,
            "near_threshold": near_threshold[:50],
            "threshold_simulations": simulations,
            "account_metrics": [dict(x) for x in (account_metrics or [])],
            "recommendation": recommendation,
            "parameter_change_applied": False,
            "approval_required": True,
            "hard_gates_unchanged": True,
        }
        analysis["checksum"] = hashlib.sha256(json.dumps(analysis, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        if persist:
            self.analyses.upsert(analysis)
        return analysis

    def latest(self) -> dict[str, Any] | None:
        rows = sorted(self.analyses.list(), key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows[0] if rows else None

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return sorted(self.analyses.list(), key=lambda row: str(row.get("created_at") or ""), reverse=True)[: max(0, int(limit))]


_default: AutonomyActivationService | None = None


def get_autonomy_activation_service() -> AutonomyActivationService:
    global _default
    if _default is None:
        _default = AutonomyActivationService()
    return _default
