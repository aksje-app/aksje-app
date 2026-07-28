"""Canonical report identity, metadata and document contracts for v19.0.21.

The contract is deliberately renderer-independent. PDF, text, archive and UI
consumers receive the same serialisable ReportDocument representation. Legacy
runs are upgraded in memory, while explicit type/mission conflicts fail closed.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping, MutableMapping, Sequence

from app_version import APP_VERSION, REPORT_SCHEMA_VERSION, get_version_contract
from local_time import DEFAULT_TIMEZONE, as_local, local_display, valid_timezone


REPORT_CONTRACT_VERSION = "1.3"


class ReportContractError(ValueError):
    """Raised when report identity or document metadata is internally inconsistent."""


@dataclass(frozen=True)
class ReportSpec:
    report_type: str
    label: str
    slug: str
    mission_code: str
    mission_label: str
    objective: str


REPORT_SPECS: dict[str, ReportSpec] = {
    "MORGENRAPPORT": ReportSpec(
        "MORGENRAPPORT", "Morgenrapport", "Morgenrapport",
        "PREPARE_TRADING_DAY", "Forbered handelsdagen",
        "Oppsummer hendelser siden forrige markedsslutt og gjør kandidater, risiko og dagens hendelser klare før åpning.",
    ),
    "DAGSRAPPORT": ReportSpec(
        "DAGSRAPPORT", "Dagsrapport", "Dagsrapport",
        "MONITOR_INTRADAY", "Overvåk utviklingen intradag",
        "Forklar markedsbevegelser siden åpning og identifiser kandidater, risiko eller datagrunnlag som har endret seg.",
    ),
    "KVELDSRAPPORT": ReportSpec(
        "KVELDSRAPPORT", "Kveldsrapport", "Kveldsrapport",
        "REVIEW_TRADING_DAY", "Oppsummer dagen og forbered neste handelsdag",
        "Evaluer dagens utvikling, beslutninger og hypoteser, og opprett sporbare oppgaver for neste handelsdag.",
    ),
    "NATTRAPPORT": ReportSpec(
        "NATTRAPPORT", "Nattrapport", "Nattrapport",
        "MONITOR_OVERNIGHT_RISK", "Oppsummer USA og overvåk overnight-risiko",
        "Oppsummer USA-avslutningen, etterbørshendelser og forhold som kan påvirke neste morgenrapport.",
    ),
    "MANUELL_RAPPORT": ReportSpec(
        "MANUELL_RAPPORT", "Manuell rapport", "Manuell_rapport",
        "USER_DEFINED", "Brukerdefinert analyseoppdrag",
        "Utfør det eksplisitte analyseoppdraget som er valgt av brukeren, med samme datakrav og sporbarhet som planlagte rapporter.",
    ),
    "SHADOW_VALIDATION": ReportSpec(
        "SHADOW_VALIDATION", "Parallell validering", "Parallell_validering",
        "VALIDATE_PIPELINE", "Valider analysemodellen uten produksjonspåvirkning",
        "Sammenlign diagnostiske eller utfordrende modeller uten å endre produksjonsbeslutninger.",
    ),
}

PERIOD_LABELS = {
    "MORGENRAPPORT": "Morgenrapport",
    "DAGSRAPPORT": "Dagsrapport",
    "KVELDSRAPPORT": "Kveldsrapport",
    "NATTRAPPORT": "Nattrapport",
}


@dataclass(frozen=True)
class CandidateDecision:
    rank: int | None
    ticker: str
    market: str
    score: float | None
    action: str
    status: str
    evidence_data_ready: bool
    final_decision_ready: bool
    decision_ready: bool
    blockers: Sequence[str] = field(default_factory=tuple)
    change_conditions: Sequence[str] = field(default_factory=tuple)
    validity: Mapping[str, Any] = field(default_factory=dict)
    source_consensus: Mapping[str, Any] = field(default_factory=dict)
    confidence: Mapping[str, Any] = field(default_factory=dict)
    decision_diff: Mapping[str, Any] = field(default_factory=dict)
    counter_hypothesis: Mapping[str, Any] = field(default_factory=dict)
    critical_assumptions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    rationale: Sequence[str] = field(default_factory=tuple)
    decision_contract: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportSection:
    key: str
    title: str
    payload: Any
    order: int
    technical: bool = False


@dataclass(frozen=True)
class ReportMetadata:
    report_id: str
    run_id: str
    report_type: str
    report_label: str
    report_slug: str
    mission_code: str
    mission_label: str
    mission_objective: str
    created_at: str
    created_at_local: str
    data_cutoff_at: str
    timezone_name: str
    job_id: str
    job_name: str
    previous_report_id: str
    status: str
    revision: str
    app_version: str
    report_schema_version: str
    contract_version: str


@dataclass(frozen=True)
class ReportDocument:
    contract: str
    contract_version: str
    schema_version: str
    metadata: ReportMetadata
    versions: Mapping[str, Any]
    sections: Sequence[ReportSection] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _period_type(created_at: datetime | str | None, timezone_name: str) -> str:
    hour = as_local(created_at or datetime.now(), timezone_name).hour
    if 5 <= hour < 12:
        return "MORGENRAPPORT"
    if 12 <= hour < 17:
        return "DAGSRAPPORT"
    if 17 <= hour < 24:
        return "KVELDSRAPPORT"
    return "NATTRAPPORT"


def _spec_identity(spec: ReportSpec) -> dict[str, str]:
    return {
        "type": spec.report_type,
        "label": spec.label,
        "slug": spec.slug,
        "mission_code": spec.mission_code,
        "mission_label": spec.mission_label,
        "mission_objective": spec.objective,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "contract_version": REPORT_CONTRACT_VERSION,
    }


def build_report_identity(
    trigger: str,
    job_name: str = "",
    job_id: str = "",
    *,
    created_at: datetime | str | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, str]:
    """Build one canonical report identity from trigger, job and local time."""
    timezone_name = valid_timezone(timezone_name)
    trigger_key = str(trigger or "").upper()
    job_key = str(job_name or "").casefold()
    draft = str(job_id or "").upper() == "MI-DRAFT-AUTOSAVE" or "DRAFT" in trigger_key or "TEST" in trigger_key
    if draft:
        period_type = _period_type(created_at, timezone_name) if created_at is not None else "MORGENRAPPORT"
        period = REPORT_SPECS[period_type]
        identity = _spec_identity(period)
        identity.update({
            "type": "UTKAST",
            "label": f"Utkast – {period.label}" if created_at is not None else "Utkast",
            "slug": f"UTKAST_{period.slug}" if created_at is not None else "UTKAST",
            "period_type": period_type,
            "draft": "true",
        })
        return identity
    if created_at is not None:
        return _spec_identity(REPORT_SPECS[_period_type(created_at, timezone_name)])
    if trigger_key == "SCHEDULED" or (trigger_key == "MANUAL_FULL_CHAIN" and "morgen" in job_key):
        return _spec_identity(REPORT_SPECS["MORGENRAPPORT"])
    return _spec_identity(REPORT_SPECS["MANUELL_RAPPORT"])


def _draft_period_from_identity(stored: Mapping[str, Any], run: Mapping[str, Any]) -> str:
    explicit = str(stored.get("period_type") or "").upper()
    if explicit in PERIOD_LABELS:
        return explicit
    text = f"{stored.get('label', '')} {stored.get('slug', '')}".casefold()
    for report_type, label in PERIOD_LABELS.items():
        if label.casefold() in text:
            return report_type
    return _period_type(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE))


def resolve_report_identity(run: Mapping[str, Any]) -> dict[str, str]:
    """Resolve and validate stored identity while upgrading legacy report rows."""
    trigger = str(run.get("trigger") or "")
    job_name = str(run.get("job_name") or "")
    job_id = str(run.get("job_id") or "")
    timezone_name = str(run.get("timezone_name") or DEFAULT_TIMEZONE)
    if job_id.upper() == "MI-DRAFT-AUTOSAVE":
        return build_report_identity(
            trigger, job_name, job_id, created_at=run.get("created_at"), timezone_name=timezone_name,
        )
    stored = run.get("report_identity")
    if not isinstance(stored, Mapping):
        return build_report_identity(
            trigger, job_name, job_id, created_at=run.get("created_at"), timezone_name=timezone_name,
        )
    report_type = str(stored.get("type") or "").upper()
    if report_type == "UTKAST":
        period_type = _draft_period_from_identity(stored, run)
        expected = build_report_identity(
            "DRAFT", job_name, "MI-DRAFT-AUTOSAVE",
            created_at=run.get("created_at"), timezone_name=timezone_name,
        )
        expected["period_type"] = period_type
        expected["mission_code"] = REPORT_SPECS[period_type].mission_code
        expected["mission_label"] = REPORT_SPECS[period_type].mission_label
        expected["mission_objective"] = REPORT_SPECS[period_type].objective
        expected.update({k: str(v) for k, v in stored.items() if k not in {
            "mission_code", "mission_label", "mission_objective", "report_schema_version", "contract_version"
        } and v is not None})
        _validate_identity_mission(expected, REPORT_SPECS[period_type])
        return expected
    spec = REPORT_SPECS.get(report_type)
    if spec is None:
        # Preserve older technical report types, but make their contract explicit.
        legacy = {k: str(v) for k, v in stored.items() if v is not None}
        legacy.setdefault("type", report_type or "MANUELL_RAPPORT")
        legacy.setdefault("label", legacy["type"].replace("_", " ").title())
        legacy.setdefault("slug", legacy["type"].title().replace("_", "_"))
        legacy.setdefault("mission_code", "LEGACY_TECHNICAL")
        legacy.setdefault("mission_label", "Eldre teknisk rapportoppdrag")
        legacy.setdefault("mission_objective", "Bevar og vis en eldre rapport uten å endre dens analyseinnhold.")
        legacy["report_schema_version"] = REPORT_SCHEMA_VERSION
        legacy["contract_version"] = REPORT_CONTRACT_VERSION
        return legacy
    expected = _spec_identity(spec)
    _validate_identity_mission(stored, spec)
    expected.update({k: str(v) for k, v in stored.items() if k not in {
        "mission_code", "mission_label", "mission_objective", "report_schema_version", "contract_version"
    } and v is not None})
    expected["mission_code"] = spec.mission_code
    expected["mission_label"] = spec.mission_label
    expected["mission_objective"] = spec.objective
    expected["report_schema_version"] = REPORT_SCHEMA_VERSION
    expected["contract_version"] = REPORT_CONTRACT_VERSION
    return expected


def _validate_identity_mission(identity: Mapping[str, Any], spec: ReportSpec) -> None:
    mission = str(identity.get("mission_code") or "").upper()
    if mission and mission != spec.mission_code:
        raise ReportContractError(
            f"Rapporttype {spec.report_type} kan ikke bruke oppdrag {mission}; forventet {spec.mission_code}."
        )


def _candidate_decisions(rows: Sequence[Mapping[str, Any]], contracts: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    contract_map = {str(row.get("ticker") or "").upper(): row for row in (contracts or []) if isinstance(row, Mapping)}
    for index, row in enumerate(rows, 1):
        try:
            score = float(row.get("investment_score")) if row.get("investment_score") is not None else None
        except (TypeError, ValueError):
            score = None
        contract = contract_map.get(str(row.get("ticker") or "").upper(), {})
        confidence = contract.get("confidence") if isinstance(contract.get("confidence"), Mapping) else {}
        decision = CandidateDecision(
            rank=int(row.get("rank") or index) if row.get("rank") or index else None,
            ticker=str(row.get("ticker") or ""),
            market=str(row.get("market") or ""),
            score=score,
            action=str(row.get("portfolio_action") or row.get("status") or "REVIEW"),
            status=str(row.get("status") or ""),
            evidence_data_ready=bool(confidence.get("evidence_data_ready", row.get("valid_for_decision") and row.get("evidence_valid_for_decision", True))),
            final_decision_ready=bool(confidence.get("final_decision_ready", confidence.get("decision_ready", False))),
            decision_ready=bool(confidence.get("final_decision_ready", confidence.get("decision_ready", False))),
            blockers=tuple(contract.get("blockers") or ()),
            change_conditions=tuple(contract.get("change_conditions") or ()),
            validity=dict(contract.get("validity") or {}),
            source_consensus=dict(contract.get("source_consensus") or {}),
            confidence=dict(confidence),
            decision_diff=dict(contract.get("decision_diff") or {}),
            counter_hypothesis=dict(contract.get("counter_hypothesis") or {}),
            critical_assumptions=tuple(contract.get("critical_assumptions") or ()),
            rationale=tuple(contract.get("rationale") or ()),
            decision_contract=dict(contract.get("decision_contract") or {}),
        )
        result.append(asdict(decision))
    return result


def _section(key: str, title: str, payload: Any, order: int, technical: bool = False) -> ReportSection:
    return ReportSection(key=key, title=title, payload=deepcopy(payload), order=order, technical=technical)


def build_report_document(run: Mapping[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the canonical renderer-independent report document."""
    identity = resolve_report_identity(run)
    from decision_report import build_decision_report
    decision_report = run.get("decision_report") if isinstance(run.get("decision_report"), Mapping) else build_decision_report(run, previous, identity)
    status = run.get("report_status") if isinstance(run.get("report_status"), Mapping) else {}
    revision = run.get("report_revision") if isinstance(run.get("report_revision"), Mapping) else {}
    previous_id = str(
        (revision.get("supersedes_run_id") if isinstance(revision, Mapping) else "")
        or (previous or {}).get("run_id")
        or ""
    )
    created_at = str(run.get("created_at") or "")
    timezone_name = valid_timezone(run.get("timezone_name"))
    report_id = str(run.get("report_id") or run.get("run_id") or "")
    metadata = ReportMetadata(
        report_id=report_id,
        run_id=str(run.get("run_id") or ""),
        report_type=str(identity.get("type") or ""),
        report_label=str(identity.get("label") or "Rapport"),
        report_slug=str(identity.get("slug") or "Rapport"),
        mission_code=str(identity.get("mission_code") or ""),
        mission_label=str(identity.get("mission_label") or ""),
        mission_objective=str(identity.get("mission_objective") or ""),
        created_at=created_at,
        created_at_local=str(run.get("created_at_local") or local_display(created_at, timezone_name)),
        data_cutoff_at=str(run.get("data_cutoff_at") or created_at),
        timezone_name=timezone_name,
        job_id=str(run.get("job_id") or ""),
        job_name=str(run.get("job_name") or ""),
        previous_report_id=previous_id,
        status=str(status.get("state") or "LEGACY"),
        revision=str(revision.get("revision_label") or "R1"),
        app_version=APP_VERSION,
        report_schema_version=REPORT_SCHEMA_VERSION,
        contract_version=REPORT_CONTRACT_VERSION,
    )
    sections = (
        _section("executive_summary", "Sammendrag", {
            "summary": dict(run.get("summary") or {}),
            "report_summary": dict(run.get("report_summary") or {}),
            "executive_intelligence": dict(run.get("executive_intelligence") or {}),
            "markets": list(run.get("markets") or []),
            "completion_status": run.get("completion_status") or "",
            "data_quality": dict(run.get("data_quality") or {}),
            "combined_data_quality": dict(run.get("combined_data_quality") or {}),
        }, 10),
        _section("decision_overview", "Beslutningsoversikt", dict(decision_report.get("overview") or {}), 15),
        _section("candidate_decisions", "Kandidatbeslutninger", _candidate_decisions(
            list(run.get("candidates") or []), list(decision_report.get("candidate_contracts") or [])
        ), 20),
        _section("changes", "Endringer siden forrige rapport", dict(decision_report.get("changes") or {}), 30),
        _section("decision_diffs", "Data-, modell- og beslutningsdiff", dict(decision_report.get("decision_diffs") or {}), 32),
        _section("counter_hypotheses", "Sterkeste motargumenter", dict(decision_report.get("counter_hypotheses") or {}), 33),
        _section("next_run_tasks", "Oppgaver til neste kjøring", list(decision_report.get("next_run_tasks") or []), 35),
        _section("historical_evaluations", "Historisk evaluering", list(decision_report.get("historical_evaluations") or []), 37),
        _section("events", "Kritiske hendelser", list(decision_report.get("events") or []), 40),
        _section("confidence_profile", "Datadekning, kildesikkerhet og beslutningssikkerhet", dict(decision_report.get("confidence") or {}), 45),
        _section("report_reliability", "Rapportpålitelighet", dict(decision_report.get("reliability") or {}), 50),
        _section("source_consensus", "Kildekonsensus", dict(decision_report.get("source_consensus") or {}), 55),
        _section("controlled_learning_guard", "Kontrollert læringsvern", dict(decision_report.get("controlled_learning_guard") or {}), 58),
        _section("technical_status", "Teknisk status", {
            "errors": list(run.get("errors") or []),
            "warnings": list(run.get("warnings") or []),
            "source_health": dict(run.get("source_health") or {}),
            "integrity_preflight": dict(run.get("integrity_preflight") or {}),
            "report_integrity": dict(run.get("report_integrity") or {}),
            "report_status": dict(status),
            "report_revision": dict(revision),
        }, 900, technical=True),
    )

    versions = get_version_contract(
        component_name="market_intelligence",
        component_version=str(run.get("version") or APP_VERSION),
    )
    document = ReportDocument(
        contract="AI_AKSJE_ANALYZER_REPORT_DOCUMENT",
        contract_version=REPORT_CONTRACT_VERSION,
        schema_version=REPORT_SCHEMA_VERSION,
        metadata=metadata,
        versions=versions,
        sections=sections,
    ).to_dict()
    validate_report_document(document, raise_on_error=True)
    return document


def validate_report_document(document: Mapping[str, Any], *, raise_on_error: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    if str(document.get("contract") or "") != "AI_AKSJE_ANALYZER_REPORT_DOCUMENT":
        errors.append("Ukjent rapportkontrakt")
    if str(document.get("schema_version") or "") != REPORT_SCHEMA_VERSION:
        errors.append("Ugyldig rapportskjemaversjon")
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    if not metadata.get("run_id"):
        errors.append("run_id mangler")
    report_type = str(metadata.get("report_type") or "").upper()
    mission_code = str(metadata.get("mission_code") or "").upper()
    spec = REPORT_SPECS.get(report_type)
    if spec and mission_code != spec.mission_code:
        errors.append(f"{report_type} har oppdrag {mission_code}, forventet {spec.mission_code}")
    if report_type == "UTKAST" and mission_code not in {x.mission_code for x in REPORT_SPECS.values()}:
        errors.append("Utkast mangler gyldig periodeoppdrag")
    sections = document.get("sections") if isinstance(document.get("sections"), Sequence) else []
    keys = [str(row.get("key") or "") for row in sections if isinstance(row, Mapping)]
    for required in (
        "executive_summary", "decision_overview", "candidate_decisions", "changes",
        "next_run_tasks", "events", "confidence_profile", "report_reliability",
        "source_consensus", "decision_diffs", "counter_hypotheses",
        "historical_evaluations", "controlled_learning_guard", "technical_status",
    ):
        if required not in keys:
            errors.append(f"Påkrevd seksjon mangler: {required}")
    result = {"ok": not errors, "errors": errors, "schema_version": REPORT_SCHEMA_VERSION}
    if errors and raise_on_error:
        raise ReportContractError("; ".join(errors))
    return result


def ensure_report_document(
    run: Mapping[str, Any], previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and, when possible, attach the current canonical document to a run."""
    identity = resolve_report_identity(run)
    from decision_report import enrich_decision_report
    enrich_decision_report(run, previous, identity)
    document = build_report_document(run, previous)
    if isinstance(run, MutableMapping):
        run["version"] = APP_VERSION
        run["report_identity"] = dict(document["metadata"] | {
            "type": document["metadata"]["report_type"],
            "label": document["metadata"]["report_label"],
            "slug": document["metadata"]["report_slug"],
        })
        # Keep the compact historical identity shape while retaining mission fields.
        run["report_identity"] = {
            "type": document["metadata"]["report_type"],
            "label": document["metadata"]["report_label"],
            "slug": document["metadata"]["report_slug"],
            "mission_code": document["metadata"]["mission_code"],
            "mission_label": document["metadata"]["mission_label"],
            "mission_objective": document["metadata"]["mission_objective"],
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "contract_version": REPORT_CONTRACT_VERSION,
        }
        run["version_contract"] = dict(document["versions"])
        run["report_document"] = document
        run["report_contract_validation"] = validate_report_document(document)
    return document


def section_payload(document: Mapping[str, Any], key: str, default: Any = None) -> Any:
    for section in document.get("sections") or []:
        if isinstance(section, Mapping) and str(section.get("key") or "") == key:
            return deepcopy(section.get("payload"))
    return deepcopy(default)


__all__ = [
    "REPORT_CONTRACT_VERSION", "REPORT_SPECS", "ReportContractError",
    "build_report_document", "build_report_identity", "ensure_report_document",
    "resolve_report_identity", "section_payload", "validate_report_document",
]
