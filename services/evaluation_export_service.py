"""Sanitised ZIP export of strategy tests and activation findings for v19.8.0."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import re
from typing import Any, Iterable, Mapping, Sequence
import zipfile

from app_version import APP_VERSION, get_version_contract
from repositories.application import RepositoryRegistry, get_repository_registry
from services.autonomy_activation_service import AutonomyActivationService
from services.strategy_account_service import StrategyAccountService
from services.simulated_execution_service import SimulatedExecutionService

EVALUATION_EXPORT_SERVICE_VERSION = "1.4"
_SECRET_KEY_RE = re.compile(r"(token|secret|password|api[_-]?key|user[_-]?key|authorization|database_url)", re.I)
_SECRET_VALUE_RE = re.compile(r"(?i)(bearer\s+[a-z0-9._-]+|https?://[^\s:@]+:[^\s@]+@|(?:token|secret|password|api[_-]?key|user[_-]?key|authorization|database[_-]?url)\s*[:=]\s*\S+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): ("[REDACTED]" if _SECRET_KEY_RE.search(str(k)) else _sanitize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE_RE.sub("[REDACTED]", value)
    return value


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    clean = [_sanitize(dict(row)) for row in rows]
    fields: list[str] = []
    seen = set()
    for row in clean:
        for key in row:
            if key not in seen:
                fields.append(key); seen.add(key)
    buf = io.StringIO()
    if fields:
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in clean:
            writer.writerow({k: (json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v) for k, v in row.items()})
    return buf.getvalue().encode("utf-8-sig")


def _summary_markdown(analysis: Mapping[str, Any], accounts: Sequence[Mapping[str, Any]]) -> str:
    funnel = dict(analysis.get("funnel") or {})
    lines = [
        f"# Autonomi testresultater – {APP_VERSION}",
        "",
        f"Opprettet: {analysis.get('created_at') or _now()}",
        f"Kjøring: {analysis.get('run_id') or '-'}",
        "",
        "## Aktiveringsfunnel",
        "",
        f"- Kandidater mottatt: {funnel.get('candidates_received', 0)}",
        f"- Bestått datakvalitet: {funnel.get('passed_data_quality', 0)}",
        f"- Bestått risiko: {funnel.get('passed_risk', 0)}",
        f"- Bestått score: {funnel.get('passed_score', 0)}",
        f"- Ordreintensjoner: {funnel.get('order_intents_created', 0)}",
        f"- Utførte paperordrer: {funnel.get('orders_executed', 0)}",
        "",
        "## Teknisk bidrag til Autonomi",
        "",
        f"- Kandidater med teknisk bidrag: {sum(1 for row in analysis.get('candidate_decisions') or [] if row.get('technical_contribution_applied'))}",
        f"- Teknisk VENT: {sum(1 for row in analysis.get('candidate_decisions') or [] if row.get('technical_entry_wait') or row.get('execution_stage') == 'TECHNICAL_TIMING_WAIT')}",
        f"- Kjøpsgrense krysset med teknisk bidrag: {sum(1 for row in analysis.get('candidate_decisions') or [] if float(row.get('base_score') or row.get('autonomy_base_investment_score') or row.get('score') or 0) < float((analysis.get('parameters') or {}).get('minimum_investment_score') or 78) <= float(row.get('score') or row.get('autonomy_adjusted_investment_score') or 0))}",
        "",
        "## Vanligste blokkeringer",
        "",
    ]
    blockers = list(analysis.get("top_blockers") or [])
    lines.extend([f"- {row.get('label')}: {row.get('count')} ({row.get('share_pct')} %)" for row in blockers] or ["- Ingen blokkeringer registrert."])
    lines += ["", "## Strategikontoer", ""]
    lines.extend([f"- {row.get('display_name') or row.get('account_id')}: {row.get('return_pct', 0):+.2f} %, drawdown {row.get('drawdown_pct', 0):.2f} %, {row.get('open_positions', 0)} posisjoner" for row in accounts] or ["- Ingen kontodata."])
    lines += ["", "## Anbefaling", "", str(analysis.get("recommendation") or "Ingen anbefaling."), "", "Ingen parameterendring er utført av eksporten."]
    return "\n".join(lines) + "\n"


class EvaluationExportService:
    def __init__(
        self,
        repositories: RepositoryRegistry | None = None,
        activation: AutonomyActivationService | None = None,
        accounts: StrategyAccountService | None = None,
        execution: SimulatedExecutionService | None = None,
    ):
        self.repositories = repositories or get_repository_registry()
        self.activation = activation or AutonomyActivationService(self.repositories)
        self.accounts = accounts or StrategyAccountService(self.repositories)
        self.execution = execution or SimulatedExecutionService(self.repositories, self.accounts)
        self.exports = self.repositories.evaluation_exports

    def build_zip(
        self,
        *,
        analysis: Mapping[str, Any] | None = None,
        errors: Sequence[Mapping[str, Any] | str] | None = None,
        additional_metadata: Mapping[str, Any] | None = None,
    ) -> bytes:
        analysis = dict(analysis or self.activation.latest() or {})
        accounts = self.accounts.comparison()
        decisions = list(analysis.get("candidate_decisions") or self.repositories.strategy_decisions.list())
        orders = self.execution.recent_orders(5000)
        fills = self.execution.recent_fills(5000)
        strategy_runs = self.repositories.strategy_runs.list()
        versions = self.repositories.strategy_versions.list()
        lab_experiments = self.repositories.strategy_lab_experiments.list()
        lab_runs = self.repositories.strategy_lab_runs.list()
        lab_approvals = self.repositories.strategy_lab_approvals.list()
        strategy_outcomes = self.repositories.strategy_outcomes.list()
        latest_lab_run = max(lab_runs, key=lambda row: str(row.get("completed_at") or ""), default={})
        created_at = _now()
        export_id = "EXP-" + hashlib.sha256(f"{created_at}|{analysis.get('analysis_id')}".encode("utf-8")).hexdigest()[:20]
        technical_policy = self.repositories.configurations.get("autonomy_technical_contribution_policy") or {}
        parameter_snapshot = {
            "analysis_parameters": analysis.get("parameters") or {},
            "autonomy_technical_contribution_policy": technical_policy,
            "strategy_versions": versions,
            "strategy_lab_experiments": lab_experiments,
            "strategy_accounts": [{k: v for k, v in row.items() if k != "positions"} for row in self.accounts.list_accounts()],
            "parameter_change_applied": False,
            "approval_required": True,
        }
        run_metadata = {
            "export_id": export_id,
            "created_at": created_at,
            "app_version": APP_VERSION,
            "version_contract": get_version_contract(component_name="evaluation_export", component_version=EVALUATION_EXPORT_SERVICE_VERSION),
            "analysis_id": analysis.get("analysis_id"),
            "run_id": analysis.get("run_id"),
            "strategy_runs": strategy_runs,
            "strategy_lab_runs": [{k: v for k, v in row.items() if k != "decisions"} for row in lab_runs],
            "latest_outcome_coverage": latest_lab_run.get("outcome_coverage") or {},
            "latest_outcome_settlement": latest_lab_run.get("outcome_settlement") or {},
            "strategy_outcome_count": len(strategy_outcomes),
            "additional_metadata": dict(additional_metadata or {}),
            "privacy": "Sanitised export. Known credential fields and secret-like values are redacted.",
        }
        funnel_rows = []
        for stage, count in dict(analysis.get("funnel") or {}).items():
            funnel_rows.append({"stage": stage, "count": count, "run_id": analysis.get("run_id")})
        for row in analysis.get("top_blockers") or []:
            funnel_rows.append({"stage": "blocker", **dict(row), "run_id": analysis.get("run_id")})
        trades = [{**dict(fill), "order_status": next((o.get("status") for o in orders if o.get("order_id") == fill.get("order_id")), "FILLED")} for fill in fills]
        technical_rows = []
        for row in decisions:
            if row.get("technical_contribution_applied") or row.get("technical_strategy_version_id") or row.get("technical_timing"):
                technical_rows.append({
                    "run_id": row.get("run_id"), "ticker": row.get("ticker"), "action": row.get("action"),
                    "base_score": row.get("base_score", row.get("autonomy_base_investment_score")),
                    "adjusted_score": row.get("score", row.get("autonomy_adjusted_investment_score")),
                    "contribution_points": row.get("technical_contribution_points"),
                    "technical_score_100": row.get("technical_score_100"),
                    "technical_confidence": row.get("technical_signal_confidence"),
                    "technical_action": row.get("technical_signal_action"),
                    "technical_timing": row.get("technical_timing"),
                    "technical_entry_wait": row.get("technical_entry_wait"),
                    "strategy_version_id": row.get("technical_strategy_version_id"),
                    "model_version": row.get("technical_model_version"),
                    "parameter_version": row.get("technical_parameter_version"),
                    "policy_version": row.get("technical_contribution_policy_version"),
                    "execution_stage": row.get("execution_stage"),
                    "reason": row.get("reason"),
                })
        quality_rows = []
        for row in self.repositories.strategy_decisions.list():
            metadata = dict(row.get("metadata") or {})
            quality = dict(metadata.get("technical_quality_result") or {})
            if row.get("strategy_id") == "technical_quality_challenger" or quality:
                quality_rows.append({
                    "run_id": row.get("run_id"),
                    "ticker": row.get("ticker"),
                    "action": row.get("action"),
                    "score": row.get("score"),
                    "confidence": row.get("confidence"),
                    "strategy_version_id": row.get("strategy_version_id"),
                    "technical_base_score": metadata.get("technical_base_score", quality.get("technical_base_score")),
                    "quality_adjustment": metadata.get("quality_adjustment", quality.get("quality_adjustment")),
                    "quality_component_count": metadata.get("quality_component_count", quality.get("quality_component_count")),
                    "quality_blockers": metadata.get("quality_blockers", quality.get("quality_blockers")),
                    "quality_blocker_codes": metadata.get("quality_blocker_codes", quality.get("quality_blocker_codes")),
                    "quality_evidence_sufficient": metadata.get("quality_evidence_sufficient", quality.get("quality_evidence_sufficient")),
                    "quality_missing_components": metadata.get("quality_missing_components", quality.get("quality_missing_components")),
                    "quality_invalid_components": metadata.get("quality_invalid_components", quality.get("quality_invalid_components")),
                    "quality_diagnostics": metadata.get("quality_diagnostics", quality.get("quality_diagnostics")),
                    "quality_evidence": quality.get("quality_evidence"),
                    "quality_policy_version": quality.get("quality_policy_version"),
                    "market_snapshot_id": row.get("market_snapshot_id"),
                    "candidate_snapshot_id": row.get("candidate_snapshot_id"),
                    "execution_authorized": row.get("execution_authorized"),
                })
        quality_diagnostic_rows = []
        diagnostics = dict(latest_lab_run.get("quality_diagnostics") or {})
        for row in diagnostics.get("components") or []:
            quality_diagnostic_rows.append({"diagnostic_type": "component", **dict(row)})
        for row in diagnostics.get("blocker_counts") or []:
            quality_diagnostic_rows.append({"diagnostic_type": "blocker", **dict(row)})
        for row in diagnostics.get("blocker_combinations") or []:
            quality_diagnostic_rows.append({"diagnostic_type": "blocker_combination", **dict(row)})
        for row in diagnostics.get("missing_components") or []:
            quality_diagnostic_rows.append({"diagnostic_type": "missing", **dict(row)})
        for row in diagnostics.get("invalid_components") or []:
            quality_diagnostic_rows.append({"diagnostic_type": "invalid", **dict(row)})
        quality_diagnostic_rows.append({
            "diagnostic_type": "summary",
            "quality_decisions": diagnostics.get("quality_decisions"),
            "sufficient_evidence_count": diagnostics.get("sufficient_evidence_count"),
            "insufficient_evidence_count": diagnostics.get("insufficient_evidence_count"),
            "sufficient_evidence_pct": diagnostics.get("sufficient_evidence_pct"),
        })
        attribution_rows = []
        for row in latest_lab_run.get("result_attribution") or []:
            base = {k: v for k, v in dict(row).items() if k not in {"blocker_outcomes", "component_attribution"}}
            attribution_rows.append({"attribution_type": "summary", **base})
            for detail in row.get("blocker_outcomes") or []:
                attribution_rows.append({"attribution_type": "blocker_outcome", "challenger_version_id": row.get("challenger_version_id"), **dict(detail)})
            for detail in row.get("component_attribution") or []:
                attribution_rows.append({"attribution_type": "component", "challenger_version_id": row.get("challenger_version_id"), **dict(detail)})
        error_lines: list[str] = []
        for item in errors or []:
            if isinstance(item, Mapping):
                error_lines.append(json.dumps(_sanitize(dict(item)), ensure_ascii=False, sort_keys=True))
            else:
                error_lines.append(str(_sanitize(str(item))))
        if not error_lines:
            error_lines.append("Ingen eksplisitte feil inkludert i eksporten.")

        files: dict[str, bytes] = {
            "test_summary.md": _summary_markdown(analysis, accounts).encode("utf-8"),
            "activation_funnel.csv": _csv_bytes(funnel_rows),
            "strategy_comparison.csv": _csv_bytes(list(latest_lab_run.get("metrics") or [])),
            "candidate_decisions.csv": _csv_bytes(decisions),
            "technical_contribution.csv": _csv_bytes(technical_rows),
            "technical_quality_challenger.csv": _csv_bytes(quality_rows),
            "strategy_lab_experiments.csv": _csv_bytes(lab_experiments),
            "strategy_lab_runs.csv": _csv_bytes([{k: v for k, v in row.items() if k != "decisions"} for row in lab_runs]),
            "strategy_lab_approvals.csv": _csv_bytes(lab_approvals),
            "quality_diagnostics.csv": _csv_bytes(quality_diagnostic_rows),
            "result_attribution.csv": _csv_bytes(attribution_rows),
            "strategy_outcomes.csv": _csv_bytes(strategy_outcomes),
            "orders.csv": _csv_bytes(orders),
            "trades.csv": _csv_bytes(trades),
            "portfolio_metrics.csv": _csv_bytes(accounts),
            "parameter_snapshot.json": json.dumps(_sanitize(parameter_snapshot), ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8"),
            "run_metadata.json": json.dumps(_sanitize(run_metadata), ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8"),
            "errors_sanitized.txt": ("\n".join(error_lines) + "\n").encode("utf-8"),
        }
        checksums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        manifest = {
            "schema_version": "1.0",
            "export_id": export_id,
            "created_at": created_at,
            "app_version": APP_VERSION,
            "service_version": EVALUATION_EXPORT_SERVICE_VERSION,
            "files": checksums,
            "contains_secrets": False,
            "safe_to_share_after_user_review": True,
        }
        files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(files):
                archive.writestr(name, files[name])
        payload = buffer.getvalue()
        self.exports.upsert({
            "export_id": export_id,
            "created_at": created_at,
            "analysis_id": analysis.get("analysis_id"),
            "run_id": analysis.get("run_id"),
            "file_count": len(files),
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "contains_secrets": False,
        })
        return payload


_default: EvaluationExportService | None = None


def get_evaluation_export_service() -> EvaluationExportService:
    global _default
    if _default is None:
        _default = EvaluationExportService()
    return _default
