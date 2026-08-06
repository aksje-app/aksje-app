"""Read-only report-package and replay-archive export for RC16.

The exporter never calls external services, sends notifications, or mutates the
production report/portfolio stores.  It copies the durable state that is still
available into deterministic ZIP packages with manifests and SHA-256 hashes.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app_version import APP_VERSION

EXPORT_SCHEMA_VERSION = "1.0"
_SECRET_KEY = re.compile(
    r"(^|_)(api[_-]?key|secret|password|passwd|token|remember[_-]?token|authorization|cookie|database[_-]?url|dsn)($|_)",
    re.IGNORECASE,
)
_SECRET_QUERY_KEYS = {"key", "api_key", "apikey", "token", "access_token", "secret", "password", "signature"}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_component(value: Any, fallback: str = "unknown") -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
    return clean or fallback


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        query = []
        for key, item in parse_qsl(parsed.query, keep_blank_values=True):
            query.append((key, "REDACTED" if key.casefold() in _SECRET_QUERY_KEYS else item))
        hostname = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{hostname}{port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), parsed.fragment))
    except Exception:
        return value


def sanitize_for_export(value: Any, *, parent_key: str = "") -> Any:
    """Return a JSON-safe copy with credentials and secret URL parameters removed."""
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _SECRET_KEY.search(key):
                clean[key] = "REDACTED"
            else:
                clean[key] = sanitize_for_export(item, parent_key=key)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_export(item, parent_key=parent_key) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"byte_length": len(value), "sha256": _sha256(value)}
    if isinstance(value, str):
        return _redact_url(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _report_identity(run: Mapping[str, Any], archive_entry: Mapping[str, Any] | None = None) -> dict[str, str]:
    archive = dict(archive_entry or {})
    report_id = str(
        run.get("report_id")
        or (run.get("report_identity") or {}).get("report_id")
        or archive.get("report_id")
        or run.get("run_id")
        or archive.get("run_id")
        or "UNKNOWN"
    )
    run_id = str(run.get("run_id") or archive.get("run_id") or report_id)
    version = str(run.get("app_version") or run.get("version") or archive.get("app_version") or APP_VERSION)
    created_at = str(run.get("created_at") or run.get("generated_at") or archive.get("created_at") or "")
    return {"report_id": report_id, "run_id": run_id, "app_version": version, "created_at": created_at}


def _read_pdf_without_side_effects(run: Mapping[str, Any], archive_entry: Mapping[str, Any] | None = None) -> bytes | None:
    archive = dict(archive_entry or {})
    candidates: list[Path] = []
    for raw in (run.get("pdf_path"), archive.get("pdf_path")):
        if raw:
            candidates.append(Path(str(raw)))
    try:
        from report_delivery import PUBLIC_REPORT_DIR
        public_name = str(run.get("public_pdf_name") or archive.get("public_pdf_name") or "").strip()
        if public_name:
            candidates.insert(0, PUBLIC_REPORT_DIR / Path(public_name).name)
    except Exception:
        pass
    for path in candidates:
        try:
            data = path.read_bytes()
            if data.startswith(b"%PDF-"):
                return data
        except Exception:
            continue
    try:
        from market_intelligence import build_pdf
        candidate = build_pdf(copy.deepcopy(dict(run)))
        if candidate and bytes(candidate).startswith(b"%PDF-"):
            return bytes(candidate)
    except Exception:
        return None
    return None


def _build_canonical_pdf(run: Mapping[str, Any]) -> bytes:
    """Render a fresh PDF from the same canonical object as TXT and JSON."""
    from market_intelligence import build_pdf
    payload = bytes(build_pdf(copy.deepcopy(dict(run))))
    if not payload.startswith(b"%PDF-"):
        raise RuntimeError("Canonical PDF-rendering returnerte ikke en gyldig PDF")
    return payload


def _build_text(run: Mapping[str, Any]) -> str:
    try:
        from market_intelligence import build_text_report
        return str(build_text_report(copy.deepcopy(dict(run))))
    except Exception:
        return json.dumps(sanitize_for_export(run), ensure_ascii=False, indent=2, default=str)


def _candidate_trace(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for candidate in run.get("candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        portfolio = candidate.get("portfolio_decision") if isinstance(candidate.get("portfolio_decision"), Mapping) else {}
        rows.append(sanitize_for_export({
            "ticker": candidate.get("ticker"),
            "market": candidate.get("market"),
            "investment_score": candidate.get("investment_score"),
            "data_quality": candidate.get("data_quality"),
            "risk_score": candidate.get("risk_score"),
            "valid_for_decision": candidate.get("valid_for_decision"),
            "evidence_valid_for_decision": candidate.get("evidence_valid_for_decision"),
            "mission_eligible": candidate.get("mission_eligible"),
            "status": candidate.get("status"),
            "autonomy_outcome": candidate.get("autonomy_outcome"),
            "autonomy_outcome_label": candidate.get("autonomy_outcome_label"),
            "portfolio_action": candidate.get("portfolio_action"),
            "portfolio_decision": portfolio,
            "decision_blockers": candidate.get("decision_blockers") or portfolio.get("blockers") or [],
            "strategy_matches": candidate.get("strategy_matches") or [],
        }))
    return rows


def _input_snapshot(run: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "report_id", "run_id", "created_at", "timezone_name", "app_version", "job_id", "job_name",
        "markets", "market_profile", "configuration_version", "mission", "mission_contract",
        "pipeline_config", "portfolio_context", "portfolio_snapshot", "autonomy_parameters",
        "source_health", "evidence_search_summary", "summary", "candidates",
    )
    return sanitize_for_export({key: copy.deepcopy(run.get(key)) for key in keys if key in run})


def classify_replay_case(run: Mapping[str, Any]) -> tuple[str, list[str]]:
    missing: list[str] = []
    candidates = [item for item in (run.get("candidates") or []) if isinstance(item, Mapping)]
    if not candidates:
        return "REPORT_ONLY", ["candidates"]
    has_scores = all(item.get("investment_score") is not None for item in candidates)
    has_decisions = all(
        item.get("portfolio_action") is not None
        or item.get("autonomy_outcome") is not None
        or item.get("status") is not None
        for item in candidates
    )
    has_evidence = all(
        item.get("evidence_valid_for_decision") is not None
        or item.get("evidence_status") is not None
        or item.get("evidence") is not None
        for item in candidates
    )
    has_portfolio = bool(run.get("portfolio_context") or run.get("portfolio_snapshot") or run.get("autonomous_portfolio"))
    if not has_scores: missing.append("candidate_scores")
    if not has_decisions: missing.append("candidate_decisions")
    if not has_evidence: missing.append("candidate_evidence")
    if not has_portfolio: missing.append("portfolio_snapshot")
    if has_scores and has_decisions and has_evidence and has_portfolio:
        return "FULL_REPLAY", []
    if has_scores and has_decisions:
        return "DECISION_REPLAY", missing
    return "REPORT_ONLY", missing


def _finalize_zip(
    files: Mapping[str, bytes],
    *,
    manifest_name: str = "MANIFEST.json",
    progress_callback: Callable[[int, int, str], None] | None = None,
    progress_offset: int = 0,
    progress_total: int | None = None,
) -> bytes:
    clean_files = {str(name): bytes(data) for name, data in files.items()}
    hashes = {
        name: {"sha256": _sha256(data), "bytes": len(data)}
        for name, data in sorted(clean_files.items())
        if name != manifest_name
    }
    if manifest_name in clean_files:
        try:
            manifest = json.loads(clean_files[manifest_name].decode("utf-8"))
        except Exception:
            manifest = {}
        # A manifest cannot contain a stable hash of itself. It records every
        # payload file, while SHA256SUMS records the finalized manifest too.
        manifest["files"] = hashes
        clean_files[manifest_name] = _json_bytes(manifest)
        hashes[manifest_name] = {"sha256": _sha256(clean_files[manifest_name]), "bytes": len(clean_files[manifest_name])}
    clean_files["SHA256SUMS.txt"] = ("\n".join(f"{row['sha256']}  {name}" for name, row in sorted(hashes.items())) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    ordered_files = sorted(clean_files.items())
    total_units = max(1, int(progress_total or (progress_offset + len(ordered_files) + 1)))
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for index, (name, data) in enumerate(ordered_files, start=1):
            archive.writestr(name, data)
            if progress_callback:
                progress_callback(progress_offset + index, total_units, f"Komprimerer: {name}")
    payload = buffer.getvalue()
    if progress_callback:
        progress_callback(min(total_units - 1, progress_offset + len(ordered_files) + 1), total_units, "Kontrollerer ZIP-integritet")
    with zipfile.ZipFile(io.BytesIO(payload), "r") as verify_archive:
        if verify_archive.testzip() is not None or not verify_archive.namelist():
            raise RuntimeError("ZIP-integritetskontrollen feilet")
    return payload


def build_single_report_package(
    run: Mapping[str, Any], *, archive_entry: Mapping[str, Any] | None = None, pdf_bytes: bytes | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    from report_export_audit import canonical_public_run, validate_artifacts, validate_zip
    if progress_callback:
        progress_callback(0, 12, "Canonicaliserer rapportdata")
    canonical_run = canonical_public_run(run)
    clean_run = sanitize_for_export(canonical_run)
    identity = _report_identity(clean_run, archive_entry)
    replay_level, missing = classify_replay_case(clean_run)
    report_dir = "report"
    if progress_callback:
        progress_callback(1, 12, "Bygger replay- og beslutningsspor")
    try:
        from replay_engine import replay_report
        replay_result = sanitize_for_export(replay_report(clean_run))
    except Exception as exc:
        replay_result = {"report_id": identity["report_id"], "status": "ERROR", "reason": str(exc), "results": []}
    report_json = _json_bytes(clean_run)
    if progress_callback:
        progress_callback(2, 12, "Bygger JSON fra canonical rapport")
    report_txt = _build_text(clean_run).encode("utf-8")
    if progress_callback:
        progress_callback(3, 12, "Bygger TXT fra canonical rapport")
    files: dict[str, bytes] = {
        f"{report_dir}/report.json": report_json,
        f"{report_dir}/report.txt": report_txt,
        f"{report_dir}/input_snapshot.json": _json_bytes(_input_snapshot(clean_run)),
        f"{report_dir}/decision_trace.json": _json_bytes(_candidate_trace(clean_run)),
        f"{report_dir}/replay_result_rc16.json": _json_bytes(replay_result),
        f"{report_dir}/source_manifest.json": _json_bytes(sanitize_for_export({
            "source_health": clean_run.get("source_health") or {},
            "evidence_search_summary": clean_run.get("evidence_search_summary") or {},
            "source_audit": clean_run.get("source_audit") or [],
        })),
    }
    # Always rebuild from clean_run. Reusing an archived/UI PDF can silently
    # mix an older identity or ranking with the current TXT/JSON contract.
    if progress_callback:
        progress_callback(4, 12, "Bygger PDF med Noto Sans og bokmerker")
    pdf = _build_canonical_pdf(clean_run)
    files[f"{report_dir}/report.pdf"] = pdf
    if missing and any(item in {"report.pdf", "report.txt", "report.json"} for item in missing):
        raise RuntimeError("Rapportpakken mangler obligatoriske artefakter: " + ", ".join(sorted(set(missing))))
    if progress_callback:
        progress_callback(6, 12, "Kjører Report Consistency Audit")
    audit = validate_artifacts(run=clean_run, pdf=bytes(pdf or b""), txt=report_txt, json_bytes=report_json)
    if not audit.get("ok"):
        raise RuntimeError("Report Consistency Audit feilet: " + "; ".join(audit.get("errors") or []))
    files["REPORT_CONSISTENCY_AUDIT.json"] = _json_bytes(audit)
    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_type": "SINGLE_REPORT_PACKAGE",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "exporter_version": APP_VERSION,
        "identity": identity,
        "replay_level": replay_level,
        "missing": sorted(set(missing)),
        "read_only": True,
        "network_calls": False,
        "notifications_sent": False,
        "production_data_mutated": False,
    }
    files["MANIFEST.json"] = _json_bytes(manifest)
    if progress_callback:
        progress_callback(7, 12, "Komprimerer rapportpakken")
    payload = _finalize_zip(files)
    if progress_callback:
        progress_callback(10, 12, "Kontrollerer ferdig ZIP")
    zip_audit = validate_zip(payload)
    if not zip_audit.get("ok"):
        raise RuntimeError("Ferdig ZIP feilet sluttkontroll: " + "; ".join(zip_audit.get("errors") or []))
    if progress_callback:
        progress_callback(12, 12, "Rapportpakken er ferdig og verifisert")
    return payload, manifest


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except Exception:
        return None


def _within_range(created: Any, date_from: datetime | None, date_to: datetime | None) -> bool:
    stamp = _parse_datetime(created)
    if stamp is None:
        return date_from is None and date_to is None
    if date_from and stamp < date_from.astimezone(timezone.utc):
        return False
    if date_to and stamp > date_to.astimezone(timezone.utc):
        return False
    return True


def _read_json_path(path: Any, default: Any) -> Any:
    try:
        target = Path(str(path))
        if target.is_file():
            return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _collect_runtime_exports() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        import market_intelligence as mi
        out.update({
            "jobs/job_profiles.json": [asdict(job) if is_dataclass(job) else sanitize_for_export(job) for job in mi.load_jobs()],
            "jobs/job_history.json": mi.load_job_history(limit=100000),
            "jobs/scheduler_health.json": mi.scheduler_health_snapshot(persist=False),
            "candidates/candidate_history.json": mi._read(mi.HISTORY_PATH, []),
            "audit/report_notifications.json": mi._read(mi.NOTIFICATIONS_PATH, []),
        })
    except Exception as exc:
        out["audit/market_intelligence_export_error.json"] = {"error": str(exc)}
    try:
        import autonomous_portfolio as ap
        out.update({
            "autonomy_portfolio/parameters.json": asdict(ap.load_parameters()),
            "autonomy_portfolio/portfolio.json": ap.load_portfolio(),
            "autonomy_portfolio/trades.json": ap._read(ap.TRADES_PATH, []),
            "autonomy_portfolio/decisions.json": ap._read(ap.DECISIONS_PATH, []),
            "autonomy_portfolio/equity_history.json": ap._read(ap.EQUITY_HISTORY_PATH, []),
            "autonomy_portfolio/performance.json": ap._read(ap.PERFORMANCE_PATH, {}),
            "learning_portfolio/portfolio.json": ap.load_learning_portfolio(),
            "learning_portfolio/trades.json": ap._read(ap.LEARNING_TRADES_PATH, []),
            "learning_portfolio/decisions.json": ap._read(ap.LEARNING_DECISIONS_PATH, []),
            "learning_portfolio/equity_history.json": ap._read(ap.LEARNING_EQUITY_HISTORY_PATH, []),
            "learning_portfolio/performance.json": ap._read(ap.LEARNING_PERFORMANCE_PATH, {}),
        })
    except Exception as exc:
        out["audit/autonomy_export_error.json"] = {"error": str(exc)}
    # Optional controlled-learning/orchestrator state is included when packaged modules expose paths.
    optional_modules = (
        "controlled_learning", "controlled_learning_runtime", "autonomous_orchestrator",
        "autonomy_orchestrator", "historical_learning",
    )
    for module_name in optional_modules:
        try:
            module = __import__(module_name)
        except Exception:
            continue
        for attr in dir(module):
            if not attr.endswith("_PATH"):
                continue
            path = getattr(module, attr, None)
            if not isinstance(path, Path) or not path.is_file():
                continue
            rel = f"runtime_optional/{_safe_component(module_name)}/{_safe_component(attr.lower())}.json"
            out[rel] = _read_json_path(path, [])
    return sanitize_for_export(out)


def _learning_summary(runtime: Mapping[str, Any]) -> dict[str, Any]:
    auto = runtime.get("autonomy_portfolio/portfolio.json") if isinstance(runtime.get("autonomy_portfolio/portfolio.json"), Mapping) else {}
    learn = runtime.get("learning_portfolio/portfolio.json") if isinstance(runtime.get("learning_portfolio/portfolio.json"), Mapping) else {}
    trades = runtime.get("autonomy_portfolio/trades.json") if isinstance(runtime.get("autonomy_portfolio/trades.json"), list) else []
    learning_trades = runtime.get("learning_portfolio/trades.json") if isinstance(runtime.get("learning_portfolio/trades.json"), list) else []
    return {
        "autonomy_open_positions": len(auto.get("positions") or {}),
        "autonomy_closed_positions": len(auto.get("closed_positions") or []),
        "autonomy_trade_events": len(trades),
        "learning_open_positions": len(learn.get("positions") or {}),
        "learning_closed_positions": len(learn.get("closed_positions") or []),
        "learning_trade_events": len(learning_trades),
        "learning_maturity_warning": "Åpne posisjoner er observasjoner, ikke dokumentert læring, før minst ett resultatmålepunkt finnes.",
    }


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> bytes:
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=list(fieldnames), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fieldnames})
    return text.getvalue().encode("utf-8-sig")


def build_complete_replay_export(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    versions: Sequence[str] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Build one read-only ZIP from every still-available report and learning store."""
    import market_intelligence as mi
    from report_export_audit import canonical_public_run, validate_artifacts

    version_filter = {str(item).strip() for item in (versions or []) if str(item).strip()}
    archive_rows = [dict(item) for item in mi._load_report_archive() if isinstance(item, Mapping)]
    selected = []
    for entry in archive_rows:
        created = entry.get("created_at") or entry.get("generated_at")
        version = str(entry.get("app_version") or entry.get("version") or "")
        if not _within_range(created, date_from, date_to):
            continue
        if version_filter and version not in version_filter:
            continue
        selected.append(entry)

    files: dict[str, bytes] = {}
    duplicates: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen_identity: dict[str, str] = {}
    seen_content: dict[str, str] = {}
    replay_counts = {"FULL_REPLAY": 0, "DECISION_REPLAY": 0, "REPORT_ONLY": 0}
    report_records: list[dict[str, Any]] = []
    replay_reports: list[dict[str, Any]] = []
    report_units = max(1, len(selected))
    base_units = 5 + report_units
    # The final total is refined after all payload files have been collected.
    total = base_units
    completed_units = 0
    if progress_callback:
        progress_callback(completed_units, total, "Samler rapportarkiv")
    completed_units += 1

    for index, entry in enumerate(selected, start=1):
        run = mi.load_archived_run(entry)
        if not run:
            run = dict(entry)
        identity = _report_identity(run, entry)
        identity_key = identity["report_id"] or identity["run_id"]
        content_hash = _sha256(_json_bytes(sanitize_for_export(run)))
        if identity_key in seen_identity:
            duplicates.append({"identity": identity_key, "kept": seen_identity[identity_key], "skipped_run_id": identity["run_id"], "reason": "DUPLICATE_IDENTITY"})
            completed_units += 1
            if progress_callback:
                progress_callback(completed_units, total, f"Pakker rapport ferdig (duplikat): {identity_key}")
            continue
        if content_hash in seen_content:
            duplicates.append({"identity": identity_key, "kept": seen_content[content_hash], "skipped_run_id": identity["run_id"], "reason": "DUPLICATE_CONTENT"})
            completed_units += 1
            if progress_callback:
                progress_callback(completed_units, total, f"Pakker rapport ferdig (duplikat): {identity_key}")
            continue
        seen_identity[identity_key] = identity["run_id"]
        seen_content[content_hash] = identity["run_id"]
        if progress_callback:
            progress_callback(completed_units, total, f"Pakker rapport: {identity_key}")
        folder = f"reports/{_safe_component(identity_key)}"
        try:
            canonical_run = canonical_public_run(run)
            clean_run = sanitize_for_export(canonical_run)
            replay_level, missing = classify_replay_case(clean_run)
            report_json = _json_bytes(clean_run)
            report_txt = _build_text(clean_run).encode("utf-8")
            report_pdf = _build_canonical_pdf(clean_run)
            audit = validate_artifacts(
                run=clean_run,
                pdf=report_pdf,
                txt=report_txt,
                json_bytes=report_json,
            )
            if not audit.get("ok"):
                raise RuntimeError(
                    "Report Consistency Audit feilet: " + "; ".join(audit.get("errors") or [])
                )
        except Exception as exc:
            quarantine_record = {
                **identity,
                "status": "QUARANTINED",
                "reason_code": "LEGACY_REPORT_FAILED_PUBLIC_EXPORT_GATE",
                "reason": str(exc),
                "public_pdf_txt_json_generated": False,
                "content_sha256": content_hash,
            }
            quarantined.append(quarantine_record)
            quarantine_folder = f"{folder}/quarantine"
            files.update({
                f"{quarantine_folder}/QUARANTINE_AUDIT.json": _json_bytes(quarantine_record),
                f"{quarantine_folder}/report_raw_sanitized.json": _json_bytes(sanitize_for_export(run)),
                f"{quarantine_folder}/archive_entry.json": _json_bytes(sanitize_for_export(entry)),
                f"{quarantine_folder}/README.txt": (
                    "Denne historiske rapporten besto ikke dagens harde offentlige eksportport.\n"
                    "Det er derfor ikke opprettet PDF, TXT eller offentlig report.json for rapporten.\n"
                    "Den saniterte originalen bevares kun som et kontrollert karantenevedlegg.\n\n"
                    f"Årsak: {exc}\n"
                ).encode("utf-8"),
            })
            completed_units += 1
            if progress_callback:
                progress_callback(completed_units, total, f"Pakker rapport ferdig (karantene): {identity_key}")
            continue

        replay_counts[replay_level] += 1
        report_files = {
            f"{folder}/report.json": report_json,
            f"{folder}/report.txt": report_txt,
            f"{folder}/report.pdf": report_pdf,
            f"{folder}/REPORT_CONSISTENCY_AUDIT.json": _json_bytes(audit),
            f"{folder}/input_snapshot.json": _json_bytes(_input_snapshot(clean_run)),
            f"{folder}/decision_trace.json": _json_bytes(_candidate_trace(clean_run)),
            f"{folder}/archive_entry.json": _json_bytes(sanitize_for_export(entry)),
            f"{folder}/source_manifest.json": _json_bytes(sanitize_for_export({
                "source_health": clean_run.get("source_health") or {},
                "evidence_search_summary": clean_run.get("evidence_search_summary") or {},
                "source_audit": clean_run.get("source_audit") or [],
            })),
        }
        try:
            from replay_engine import replay_report
            replay_result = sanitize_for_export(replay_report(clean_run))
        except Exception as exc:
            replay_result = {"report_id": identity_key, "status": "ERROR", "reason": str(exc), "results": []}
        replay_reports.append(replay_result)
        report_files[f"{folder}/replay_result_rc16.json"] = _json_bytes(replay_result)
        files.update(report_files)
        if missing:
            incomplete.append({"report_id": identity_key, "run_id": identity["run_id"], "replay_level": replay_level, "missing": sorted(set(missing))})
        if str(clean_run.get("report_id") or identity_key) != identity_key:
            conflicts.append({"report_id": identity_key, "field": "report_id", "run_value": clean_run.get("report_id")})
        report_records.append({**identity, "replay_level": replay_level, "missing": sorted(set(missing)), "content_sha256": content_hash})
        completed_units += 1
        if progress_callback:
            progress_callback(completed_units, total, f"Pakker rapport ferdig: {identity_key}")

    try:
        from replay_engine import summarize_replays
        replay_summary = sanitize_for_export(summarize_replays(replay_reports))
    except Exception as exc:
        replay_summary = {"error": str(exc), "reports_total": len(replay_reports), "unresolved": []}
    replay_rows = [row for report in replay_reports for row in (report.get("results") or []) if isinstance(row, Mapping)]
    files["replay/REPLAY_CANDIDATE_DIFFS.json"] = _json_bytes(replay_rows)
    files["replay/REPLAY_DECISION_FUNNEL.json"] = _json_bytes(replay_summary)
    files["replay/REPLAY_RC15_VS_RC16_RESULTS.csv"] = _csv_bytes(
        replay_rows,
        ("report_id", "run_id", "ticker", "market", "investment_score", "original_action", "rc16_action", "changed", "first_blocker_code", "reason"),
    )
    unresolved_rows = replay_summary.get("unresolved") if isinstance(replay_summary.get("unresolved"), list) else []
    files["replay/REPLAY_UNRESOLVED_CASES.csv"] = _csv_bytes(
        unresolved_rows,
        ("report_id", "run_id", "ticker", "market", "investment_score", "original_action", "rc16_action", "first_blocker_code", "reason"),
    )

    if progress_callback:
        progress_callback(completed_units, total, "Legger til runtime-data")
    runtime = _collect_runtime_exports()
    for name, payload in runtime.items():
        files[name] = _json_bytes(payload)
    completed_units += 1
    learning_summary = _learning_summary(runtime)
    files["learning_portfolio/LEARNING_SUMMARY.json"] = _json_bytes(learning_summary)
    files["replay/REPLAY_LEARNING_SUMMARY.md"] = (
        "# RC16 replay- og læringssammendrag\n\n"
        f"- Eksporterte rapporter: {len(report_records)}\n"
        f"- Replayede kandidater: {replay_summary.get('candidates_replayed', 0)}\n"
        f"- Endrede beslutninger: {replay_summary.get('changed_decisions', 0)}\n"
        f"- Uavklarte replaytilfeller: {replay_summary.get('unresolved_count', 0)}\n"
        f"- Åpne Autonomi-posisjoner: {learning_summary.get('autonomy_open_positions', 0)}\n"
        f"- Åpne læringsposisjoner: {learning_summary.get('learning_open_positions', 0)}\n\n"
        "Åpne posisjoner regnes som observasjoner, ikke dokumentert læring, før resultatmålepunkter finnes.\n"
    ).encode("utf-8")
    files["audit/duplicates.json"] = _json_bytes(duplicates)
    files["audit/missing_files.json"] = _json_bytes(missing_files)
    files["audit/incomplete_replay_cases.json"] = _json_bytes(incomplete)
    files["audit/conflicts.json"] = _json_bytes(conflicts)
    files["audit/quarantined_reports.json"] = _json_bytes(quarantined)

    summary = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_type": "COMPLETE_REPLAY_ARCHIVE",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "exporter_version": APP_VERSION,
        "archive_entries_found": len(archive_rows),
        "archive_entries_selected": len(selected),
        "unique_reports_exported": len(report_records),
        "reports_quarantined": len(quarantined),
        "reports_accounted_for": len(report_records) + len(quarantined),
        "duplicates": len(duplicates),
        "missing_files": len(missing_files),
        "incomplete_replay_cases": len(incomplete),
        "identity_conflicts": len(conflicts),
        "replay_levels": replay_counts,
        "filters": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "versions": sorted(version_filter),
        },
        "learning_summary": learning_summary,
        "replay_summary": {key: value for key, value in replay_summary.items() if key != "unresolved"},
        "read_only": True,
        "network_calls": False,
        "notifications_sent": False,
        "production_data_mutated": False,
    }
    files["EXPORT_SUMMARY.json"] = _json_bytes(summary)
    files["REPLAY_DATASET_MANIFEST.json"] = _json_bytes({"summary": summary, "reports": report_records, "quarantined_reports": quarantined})
    files["MANIFEST.json"] = _json_bytes({
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_type": "COMPLETE_REPLAY_ARCHIVE",
        "exported_at": summary["exported_at"],
        "exporter_version": APP_VERSION,
        "summary_file": "EXPORT_SUMMARY.json",
        "dataset_manifest": "REPLAY_DATASET_MANIFEST.json",
        "read_only": True,
    })
    completed_units += 1
    file_count = len(files) + 2  # SHA256SUMS plus potential finalized manifest rewrite
    final_total = max(completed_units + file_count + 2, total)
    if progress_callback:
        progress_callback(completed_units, final_total, "Ferdigstiller manifest og kontrollsummer")
    payload = _finalize_zip(
        files,
        progress_callback=progress_callback,
        progress_offset=completed_units,
        progress_total=final_total,
    )
    if progress_callback:
        progress_callback(final_total, final_total, "Kontrollerer ferdig ZIP og klargjør nedlasting")
    return payload, summary


def complete_export_filename() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    return f"AI_Aksje_Analyzer_Replay_Export_{stamp}.zip"


def single_report_package_filename(run: Mapping[str, Any]) -> str:
    identity = _report_identity(run)
    return f"REPORT_PACKAGE_{_safe_component(identity['report_id'])}.zip"
