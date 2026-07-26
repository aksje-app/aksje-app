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

EVALUATION_EXPORT_SERVICE_VERSION = "1.0"
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
        created_at = _now()
        export_id = "EXP-" + hashlib.sha256(f"{created_at}|{analysis.get('analysis_id')}".encode("utf-8")).hexdigest()[:20]
        parameter_snapshot = {
            "analysis_parameters": analysis.get("parameters") or {},
            "strategy_versions": versions,
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
            "additional_metadata": dict(additional_metadata or {}),
            "privacy": "Sanitised export. Known credential fields and secret-like values are redacted.",
        }
        funnel_rows = []
        for stage, count in dict(analysis.get("funnel") or {}).items():
            funnel_rows.append({"stage": stage, "count": count, "run_id": analysis.get("run_id")})
        for row in analysis.get("top_blockers") or []:
            funnel_rows.append({"stage": "blocker", **dict(row), "run_id": analysis.get("run_id")})
        trades = [{**dict(fill), "order_status": next((o.get("status") for o in orders if o.get("order_id") == fill.get("order_id")), "FILLED")} for fill in fills]
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
            "strategy_comparison.csv": _csv_bytes(accounts),
            "candidate_decisions.csv": _csv_bytes(decisions),
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
