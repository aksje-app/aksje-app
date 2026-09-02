"""Scheduled Market Intelligence & PDF Reports v19.16.0.

Job profiles combine multiple markets, schedules, pipeline modules and notification
rules. Jobs can run manually, when the Streamlit app is active, or from cron via
``python market_intelligence.py --run-due``. Analysis only: no trades are executed.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import traceback
import threading
import uuid
import time as time_module
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from html import escape as html_escape
from urllib.parse import quote
from typing import Any, Mapping, Sequence, Callable

from investment_pipeline import PipelineConfig, _load_candidate_rows_from_app, infer_market_from_ticker, normalize_candidate_identity, run_pipeline
from market_universe import (
    BASE_MARKET_SCOPES, CORE_MARKET_SCOPES, EXTENDED_NORDIC_MARKET_SCOPES,
    CORE_MARKET_SCOPE_LABEL, EXTENDED_NORDIC_SCOPE_LABEL, NORDIC_MARKET_SCOPE_LABEL,
    FULL_MARKET_SCOPE_LABEL, MARKET_PROFILE_CORE, MARKET_PROFILE_FULL, expand_market_scope,
    infer_market_profile, market_profile_contract, profile_market_selections,
)
from storage_architecture import runtime_data_path, runtime_log_path
from persistent_config_store import read_persistent_json, write_persistent_json
from durable_runtime import append_event, read_events, read_json as durable_read_json, write_json as durable_write_json
from execution_control import ExecutionCancelled
from local_time import (DEFAULT_TIMEZONE, SUPPORTED_TIMEZONES, as_local, browser_timezone,
                        install_browser_timezone_bootstrap, local_compact_stamp, local_display,
                        local_run_id, valid_timezone)
from report_delivery import PUBLIC_REPORT_DIR, publish_pdf, public_report_url
from app_version import APP_VERSION, REPORT_SCHEMA_VERSION
from navigation_state import pin_autonomy_workspace_route_v19220_rc11
from report_integrity import (
    apply_report_integrity,
    canonical_report_view,
    compact_candidate_reference,
    validate_pdf_semantics,
    validate_report_integrity,
)
from report_contracts import (
    build_report_identity as build_report_identity_contract,
    ensure_report_document,
    resolve_report_identity as resolve_report_identity_contract,
    section_payload,
)
from norwegian_report_language import (
    component_label, decision_color, decision_label, decision_text_color, label_for,
    model_role_label, quality_status, score_status, sector_label, translate_list,
    translate_report_text, USER_FACING_ENGLISH_BLOCKLIST, status_dot,
)

VERSION = APP_VERSION
# Compatibility/audit anchor for the former hard blocker: Sentral konfigurasjon er endret.
# RC12 migrates the mission contract instead of asking the operator to recreate the job.


def _rerun_reports_v19220_rc11(st, *, execution_id: str = "") -> None:
    """Keep Rapporter active without mutating an instantiated workspace widget."""
    bound_execution_id = str(
        execution_id or st.session_state.get("mi_active_execution_v1924") or ""
    )
    pin_autonomy_workspace_route_v19220_rc11(
        st, workspace_slug="reports", public_nav="reports",
        execution_id=bound_execution_id,
    )
    st.rerun()


def _rerun_reports_v19220_rc13(st, *, execution_id: str = "") -> None:
    """RC13 alias retaining the established safe pending-route contract."""
    _rerun_reports_v19220_rc11(st, execution_id=execution_id)


def _rerun_reports_v19220_rc12(st, *, execution_id: str = "") -> None:
    """Backward-compatible alias for the RC13 report rerun contract."""
    _rerun_reports_v19220_rc11(st, execution_id=execution_id)


def _rerun_reports_v19220_rc9(st, *, execution_id: str = "") -> None:
    """Backward-compatible alias for the RC13 report rerun contract."""
    _rerun_reports_v19220_rc11(st, execution_id=execution_id)


ROOT = runtime_data_path("market_intelligence")
JOBS_PATH = ROOT / "jobs.json"
RUNS_DIR = ROOT / "runs"
SUMMARIES_DIR = ROOT / "summaries"
HISTORY_PATH = ROOT / "candidate_history.json"
NOTIFICATIONS_PATH = ROOT / "notifications.json"
LATEST_PATH = ROOT / "latest_run.json"
AUDIT_PATH = ROOT / "audit.jsonl"
REPORT_ARCHIVE_PATH = ROOT / "report_archive.json"
REPORT_ARCHIVE_SETTINGS_PATH = ROOT / "report_archive_settings.json"
REPORT_NOTIFICATION_RECEIPTS_PATH = ROOT / "report_notification_receipts.json"
JOB_HISTORY_PATH = ROOT / "job_history.json"
SCHEDULER_HEALTH_PATH = ROOT / "scheduler_health.json"
DRAFT_STORAGE_KEY = "market_intelligence/draft_job.json"
DRAFT_JOB_ID = "MI-DRAFT-AUTOSAVE"
RECENT_DRAFT_REUSE_MINUTES = 30
_ARCHIVE_LOCK = threading.RLock()
REPORT_FAILURES_DIR = runtime_log_path("report_failures")
_REPORT_LOGGER = logging.getLogger("ai_aksje_analyzer.report")


class ReportStageError(RuntimeError):
    """REPORT-stage failure with user-visible and machine-readable context."""

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.context = dict(context or {})


def report_storage_preflight(run_id: str, report_path: Path | None = None) -> dict[str, Any]:
    """Create and verify every local directory required by REPORT.

    The probe runs before PDF generation. A mounted disk with wrong permissions
    therefore fails immediately with the exact path instead of after another
    long run with an opaque 93 percent failure.
    """
    directories = [ROOT, RUNS_DIR, SUMMARIES_DIR]
    if report_path is not None:
        directories.append(Path(report_path).parent)
    checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    safe_id = "".join(ch for ch in str(run_id or "unknown") if ch.isalnum() or ch in "-_")[:80] or "unknown"
    for directory in directories:
        directory = Path(directory)
        key = str(directory.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        probe = directory / f".report_write_probe_{safe_id}_{uuid.uuid4().hex[:8]}.tmp"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            payload = f"report-write-check:{safe_id}"
            with probe.open("x", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if probe.read_text(encoding="utf-8") != payload:
                raise OSError("skrivekontrollen kunne ikke leses tilbake")
            checks.append({"path": str(directory), "writable": True})
        except Exception as exc:
            raise PermissionError(f"REPORT-lagring er ikke skrivbar: {directory} ({type(exc).__name__}: {exc})") from exc
        finally:
            try:
                probe.unlink(missing_ok=True)
            except Exception:
                pass
    return {
        "ok": True,
        "run_id": str(run_id or ""),
        "app_runtime_root": str(os.getenv("APP_RUNTIME_ROOT", ".app_runtime") or ".app_runtime"),
        "storage_mode": str(os.getenv("STORAGE_MODE", "auto") or "auto"),
        "report_path": str(report_path or ""),
        "checks": checks,
    }


def record_report_failure(run_id: str, report_path: Path | None, exc: BaseException, *, stage: str = "REPORT") -> dict[str, Any]:
    """Log and persist a complete REPORT failure without masking the original error."""
    trace = traceback.format_exc()
    payload: dict[str, Any] = {
        "at": _now_iso(),
        "app_version": APP_VERSION,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_id": str(run_id or ""),
        "stage": str(stage or "REPORT"),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "report_path": str(report_path or ""),
        "app_runtime_root": str(os.getenv("APP_RUNTIME_ROOT", ".app_runtime") or ".app_runtime"),
        "storage_mode": str(os.getenv("STORAGE_MODE", "auto") or "auto"),
        "database_url_configured": bool(str(os.getenv("DATABASE_URL", "") or "").strip()),
        "traceback": trace,
    }
    _REPORT_LOGGER.error("REPORT_STAGE_FAILED %s", json.dumps(payload, ensure_ascii=False, default=str), exc_info=True)
    diagnostic_path = REPORT_FAILURES_DIR / f"{str(run_id or 'unknown')}_report_failure.json"
    try:
        diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostic_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        payload["diagnostic_path"] = str(diagnostic_path)
    except Exception as diagnostic_exc:
        payload["diagnostic_write_error"] = f"{type(diagnostic_exc).__name__}: {diagnostic_exc}"
    try:
        _audit("REPORT_STAGE_FAILED", {key: value for key, value in payload.items() if key != "traceback"})
    except Exception:
        pass
    return payload


def should_suppress_notifications(trigger: str, send_notifications: bool) -> bool:
    """Fail closed for test runs unless a test notification is explicit.

    A trigger containing TEST is silent by default.  Only the dedicated
    TEST_NOTIFICATION trigger may send, and only when send_notifications is
    also true.  Normal production/manual triggers keep their existing policy.
    """
    trigger_name = str(trigger or "").upper()
    is_test = "TEST" in trigger_name
    explicit_test_notification = "TEST_NOTIFICATION" in trigger_name
    return (not bool(send_notifications)) or (is_test and not explicit_test_notification)

MODULE_OPTIONS = [
    "Market Scanner", "AI Discovery", "AI Research Assistant", "Strategy Match",
    "Backtesting Validation", "Portfolio Optimizer", "Learning Advisor", "Insider Intelligence", "News & Sentiment Intelligence",
]
MODULE_LABELS_NO = {
    "Market Scanner": "Markedsskanner",
    "AI Discovery": "AI-funn",
    "AI Research Assistant": "AI-analyseassistent",
    "Strategy Match": "Strategisjekk",
    "Backtesting Validation": "Historisk test",
    "Portfolio Optimizer": "Porteføljeoptimalisering",
    "Learning Advisor": "Læringsrådgiver",
    "Insider Intelligence": "Innsideranalyse",
    "News & Sentiment Intelligence": "Nyhets- og sentimentanalyse",
}
SCHEDULE_OPTIONS = ["Ved appstart", "08:00", "12:00", "14:00", "15:00", "22:00"]
GLOBAL_ALERT_SCORE_KEY = "market_intelligence/global_alert_score.json"
DEFAULT_GLOBAL_ALERT_SCORE = 80.0
LEGACY_SCHEDULE_MIGRATION = {"08:30": "08:00", "16:30": "14:00", "22:30": "22:00"}


def normalize_schedule_value(value: Any) -> str:
    raw = str(value or "").strip()
    return LEGACY_SCHEDULE_MIGRATION.get(raw, raw)


def load_global_alert_score() -> float:
    raw = read_persistent_json(GLOBAL_ALERT_SCORE_KEY, default=DEFAULT_GLOBAL_ALERT_SCORE)
    try:
        return max(0.0, min(100.0, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_GLOBAL_ALERT_SCORE


def save_global_alert_score(value: float) -> float:
    score = max(0.0, min(100.0, float(value)))
    previous = load_global_alert_score()
    if score != previous:
        write_persistent_json(GLOBAL_ALERT_SCORE_KEY, score)
        _audit("GLOBAL_ALERT_SCORE_CHANGED", {"before": previous, "after": score})
    return score


def apply_execution_settings(job: "JobProfile") -> tuple["JobProfile", dict[str, Any]]:
    """Snapshot central settings once when a job starts.

    Manual and scheduled runs use the same current threshold. A running job
    keeps its snapshot even if an administrator changes the setting later.
    """
    score = load_global_alert_score()
    effective = replace(job, min_alert_score=score)
    return effective, {
        "global_alert_score": score,
        "applies_to": "MANUAL_AND_SCHEDULED_NEW_RUNS",
        "snapshot_at_start": True,
    }
DEFAULT_SCAN_WINDOWS = [{"start": "08:00", "end": "10:00", "interval_minutes": 30}]
WEEKDAY_NAMES = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
REQUIRED_REPORT_SPECS = (
    {"job_id": "MI-REQUIRED-MORNING", "name": "Obligatorisk morgenrapport", "schedule": "08:00", "token": "morgen"},
    {"job_id": "MI-REQUIRED-AFTERNOON", "name": "Obligatorisk ettermiddagsrapport", "schedule": "14:00", "token": "ettermiddag"},
    {"job_id": "MI-REQUIRED-EVENING", "name": "Obligatorisk kveldsrapport", "schedule": "22:00", "token": "kveld"},
)

_LEGACY_FIXED_REPORT_NAMES = {
    "morgen": {"morgenrapport", "morgenanalyse", "obligatorisk morgenrapport"},
    "ettermiddag": {
        "dagsrapport", "ettermiddagsrapport", "ettermiddagsanalyse",
        "obligatorisk ettermiddagsrapport",
    },
    "kveld": {"kveldsrapport", "kveldsanalyse", "obligatorisk kveldsrapport"},
}

SCAN_PROFILES = {
    "Rask (10)": 10, "Standard (20)": 20, "Normal (25)": 25,
    "Grundig (50)": 50, "Stor (100)": 100, "Maks (250)": 250,
    "Egendefinert (10–250)": None,
}


COMPANY_TICKER_ALIASES = {
    "GOOG": "ALPHABET", "GOOGL": "ALPHABET",
    "BRK-A": "BERKSHIRE_HATHAWAY", "BRK-B": "BERKSHIRE_HATHAWAY",
    "BRK.A": "BERKSHIRE_HATHAWAY", "BRK.B": "BERKSHIRE_HATHAWAY",
    "FOX": "FOX_CORP", "FOXA": "FOX_CORP",
    "NWS": "NEWS_CORP", "NWSA": "NEWS_CORP",
    "DISCA": "WARNER_BROS_DISCOVERY", "DISCB": "WARNER_BROS_DISCOVERY", "DISCK": "WARNER_BROS_DISCOVERY",
    "HEI": "HEICO", "HEI-A": "HEICO",
}

def company_identity(candidate: Mapping[str, Any]) -> str:
    """Return a stable company key so share classes do not occupy multiple medal/portfolio slots."""
    from issuer_identity import issuer_identity
    return issuer_identity(candidate)

def select_diverse_candidates(candidates: Sequence[Mapping[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    selected, seen = [], set()
    for item in candidates:
        key = company_identity(item)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(item))
        if len(selected) >= limit:
            break
    return selected

def executive_intelligence(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(candidates or [])
    scores = [float(x.get("investment_score", 0) or 0) for x in rows]
    markets = {str(x.get("market") or "Ukjent") for x in rows[:10]}
    companies = {company_identity(x) for x in rows}
    return {
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "highest_score": round(max(scores), 2) if scores else 0.0,
        "lowest_score": round(min(scores), 2) if scores else 0.0,
        "unique_companies": len(companies),
        "markets_in_top10": len(markets),
    }

def diversify_portfolio(proposal: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(proposal or {})
    key = "allocations" if isinstance(result.get("allocations"), list) else "positions"
    allocations = list(result.get(key) or [])
    kept, removed, seen = [], [], set()
    for allocation in allocations:
        company_key = company_identity(allocation)
        if company_key in seen:
            removed.append(dict(allocation))
            continue
        seen.add(company_key)
        kept.append(dict(allocation))
    result[key] = kept
    if key == "positions" and "allocations" in result:
        result["allocations"] = kept
    removed_weight = sum(float(x.get("weight_pct", x.get("weight", 0)) or 0) for x in removed)
    result["invested_pct"] = round(max(0.0, float(result.get("invested_pct", 0) or 0) - removed_weight), 2)
    result["cash_pct"] = round(min(100.0, float(result.get("cash_pct", 100) or 100) + removed_weight), 2)
    result["company_duplicates_removed"] = len(removed)
    result["company_diversity_applied"] = True
    return result

MARKET_CLOCKS = {
    "USA": ("America/New_York", time(9, 30), time(16, 0)),
    "Norge": ("Europe/Oslo", time(9, 0), time(16, 20)),
    "Sverige": ("Europe/Stockholm", time(9, 0), time(17, 30)),
    "Finland": ("Europe/Helsinki", time(10, 0), time(18, 30)),
    "Danmark": ("Europe/Copenhagen", time(9, 0), time(17, 0)),
    "Brasil": ("America/Sao_Paulo", time(10, 0), time(17, 55)),
}


def build_market_status(markets: Sequence[str], refresh: Mapping[str, Any] | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    """Return transparent exchange-clock status without pretending to know every holiday."""
    refresh = refresh or {}
    now = now or datetime.now(timezone.utc)
    dates = list(refresh.get("latest_trade_dates") or [])
    latest_date = max(dates) if dates else None
    rows = []
    for market in markets:
        tz_name, open_at, close_at = MARKET_CLOCKS.get(market, ("UTC", time(0, 0), time(0, 0)))
        local = now.astimezone(ZoneInfo(tz_name))
        reference_weekend = now.astimezone(timezone.utc).weekday() >= 5
        weekday_open = local.weekday() < 5 and not reference_weekend
        within_hours = open_at <= local.time().replace(tzinfo=None) <= close_at
        status = "ÅPEN" if weekday_open and within_hours else "STENGT"
        reason = "Innenfor ordinær åpningstid" if status == "ÅPEN" else ("Helg" if reference_weekend or not weekday_open else "Utenfor ordinær åpningstid")
        rows.append({"market": market, "status": status, "reason": reason, "local_time": local.strftime("%H:%M"), "timezone": tz_name, "latest_trade_date": latest_date})
    return rows


def build_data_quality(refresh: Mapping[str, Any], candidate_count: int,
                       market_diagnostics: Sequence[Mapping[str, Any]] | None = None,
                       planned_markets: Sequence[str] | None = None) -> dict[str, Any]:
    total = max(1, int(candidate_count or 0))
    success = int(refresh.get("live_count", 0))
    errors = int(refresh.get("error_count", 0))
    cache = int(refresh.get("cache_count", 0))
    coverage = max(0.0, min(100.0, 100.0 * (success + cache) / total))
    penalty = min(35.0, errors * 7.0 + (0 if refresh.get("latest_trade_dates") else 10.0))
    diagnostics = list(market_diagnostics or [])
    planned = list(planned_markets or [])
    failed_markets = [str(x.get("market") or "Ukjent") for x in diagnostics
                      if int(x.get("scanned") or 0) == 0 or str(x.get("status") or "").startswith("FEIL")]
    reported = {str(x.get("market") or "") for x in diagnostics}
    failed_markets.extend(x for x in planned if x not in reported)
    failed_markets = list(dict.fromkeys(failed_markets))
    market_penalty = (100.0 * len(failed_markets) / max(1, len(planned))) if planned else 0.0
    score = round(max(0.0, coverage - penalty - market_penalty), 1)
    label = "UTMERKET" if score >= 90 else "GODT" if score >= 75 else "BEGRENSET" if score >= 50 else "SVAKT"
    return {"score": score, "label": label, "candidate_count": candidate_count, "live": success, "cache": cache,
            "errors": errors, "failed_markets": failed_markets, "market_coverage": len(planned) - len(failed_markets),
            "planned_markets": len(planned), "latest_trade_dates": list(refresh.get("latest_trade_dates") or [])}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


# RC13: scheduler health must not call a slot "missed" when this web process
# started after the slot and no durable execution history exists. The slot was
# not observable by this process. Future slots and slots observed by a running
# process retain the existing missed-run detection.
SCHEDULER_OBSERVATION_STARTED_AT_UTC_V19220_RC13 = _now().astimezone(timezone.utc)


def _read(path: Path, default: Any) -> Any:
    key = _durable_key(path)
    if key:
        return durable_read_json(key, path, default)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    key = _durable_key(path)
    if key:
        durable_write_json(key, path, payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _audit(event: str, payload: Mapping[str, Any]) -> None:
    row = {
        "at": _now_iso(), "event": event,
        "app_version": APP_VERSION, "report_schema_version": REPORT_SCHEMA_VERSION,
        **dict(payload),
    }
    append_event("market_intelligence/audit.jsonl", AUDIT_PATH, row)


def _durable_key(path: Path) -> str | None:
    if path == LATEST_PATH: return "market_intelligence/latest_run.json"
    if path == HISTORY_PATH: return "market_intelligence/candidate_history.json"
    if path == REPORT_ARCHIVE_PATH: return "market_intelligence/report_archive.json"
    if path == REPORT_NOTIFICATION_RECEIPTS_PATH: return "market_intelligence/report_notification_receipts.json"
    if path == JOB_HISTORY_PATH: return "market_intelligence/job_history.json"
    if path == SCHEDULER_HEALTH_PATH: return "market_intelligence/scheduler_health.json"
    if path.parent == RUNS_DIR: return f"market_intelligence/runs/{path.name}"
    if path.parent == SUMMARIES_DIR and path.suffix.lower() == ".json": return f"market_intelligence/summaries/{path.name}"
    return None


def load_audit(limit: int = 1000) -> list[dict[str, Any]]:
    return read_events("market_intelligence/audit.jsonl", AUDIT_PATH, limit=limit)


def load_run(run_id: str) -> dict[str, Any]:
    value = _read(RUNS_DIR / f"{run_id}.json", {})
    return dict(value) if isinstance(value, Mapping) else {}


def normalize_markets(markets: Sequence[str]) -> list[str]:
    """Expand market groups while keeping the default 'Alle' intentionally small.

    v19.14.0 defines Alle/Kjernemarkeder as Norge, Sverige and USA.  The old
    six-market behaviour is available only through 'Alle markeder - full skanning'.
    """
    chosen = [str(x).strip() for x in markets if str(x).strip()]
    expanded: list[str] = []
    for scope in chosen:
        values = expand_market_scope(scope) or ([scope] if scope in BASE_MARKET_SCOPES else [])
        for market in values:
            if market not in expanded:
                expanded.append(market)
    return expanded or ["Norge"]


def canonical_market_profile_selections(markets: Sequence[str] | None) -> list[str]:
    """Return stable scheduler/UI selections for legacy and current market values.

    Older saved jobs used ``Alle`` for the six-market scan, while v19.14.x gives
    that label the safer core-market meaning.  Persisted explicit market lists are
    therefore canonicalised by their actual set: exact core, extended Nordic and
    full-market sets become one unambiguous profile label; mixed sets remain
    explicit single-market selections.
    """
    raw = [str(x).strip() for x in (markets or []) if str(x).strip()]
    if not raw:
        return [CORE_MARKET_SCOPE_LABEL]

    expanded = normalize_markets(raw)
    expanded_set = set(expanded)
    if expanded_set == set(BASE_MARKET_SCOPES):
        return [FULL_MARKET_SCOPE_LABEL]
    if expanded_set == set(CORE_MARKET_SCOPES):
        return [CORE_MARKET_SCOPE_LABEL]
    if expanded_set == set(EXTENDED_NORDIC_MARKET_SCOPES):
        return [EXTENDED_NORDIC_SCOPE_LABEL]

    # Return only valid individual markets, in deterministic product order.
    ordered = [market for market in BASE_MARKET_SCOPES if market in expanded_set]
    return ordered or [CORE_MARKET_SCOPE_LABEL]


def build_market_coverage_v19220_rc9(run: Mapping[str, Any]) -> dict[str, Any]:
    """Describe planned and actual country coverage without marketing aliases."""
    planned = [str(value) for value in (run.get("markets") or []) if str(value).strip()]
    scan = run.get("scan_configuration") if isinstance(run.get("scan_configuration"), Mapping) else {}
    actual_raw = scan.get("actual_by_market") if isinstance(scan.get("actual_by_market"), Mapping) else {}
    actual_by_market = {str(key): int(value or 0) for key, value in actual_raw.items()}
    diagnostics = [row for row in (run.get("market_diagnostics") or []) if isinstance(row, Mapping)]
    diagnostic_by_market = {str(row.get("market") or ""): row for row in diagnostics}
    completed: list[str] = []
    partial: list[str] = []
    failed: list[str] = []
    rows: list[dict[str, Any]] = []
    for market in planned:
        diag = diagnostic_by_market.get(market, {})
        scanned = int(actual_by_market.get(market, diag.get("scanned", 0)) or 0)
        status = str(diag.get("status") or ("OK" if scanned > 0 else "NOT_RUN")).upper()
        errors = int(diag.get("errors", 0) or 0) + int(diag.get("market_data_errors", 0) or 0)
        if scanned <= 0 or status in {"ERROR", "FAILED", "NOT_RUN", "SKIPPED"}:
            failed.append(market)
            coverage = "FAILED"
        elif errors > 0 or status not in {"OK", "PASS", "COMPLETED"}:
            partial.append(market)
            coverage = "PARTIAL"
        else:
            completed.append(market)
            coverage = "COMPLETED"
        rows.append({"market": market, "planned": True, "scanned": scanned, "status": coverage, "source_status": status})
    overall = "COMPLETE" if planned and len(completed) == len(planned) else ("PARTIAL" if completed or partial else "FAILED")
    return {
        "planned_markets": planned,
        "planned_country_text": ", ".join(planned),
        "actual_by_market": actual_by_market,
        "completed_markets": completed,
        "partial_markets": partial,
        "failed_or_skipped_markets": failed,
        "overall_status": overall,
        "complete": overall == "COMPLETE",
        "rows": rows,
    }


def _allocated_market_budget(total: int, market_index: int, market_count: int, *, minimum: int = 1) -> int:
    """Distribute a total analysis budget deterministically across markets."""
    total = max(0, int(total))
    market_count = max(1, int(market_count))
    market_index = max(1, min(int(market_index), market_count))
    base, remainder = divmod(total, market_count)
    return max(minimum, base + (1 if market_index <= remainder else 0))


MINIMUM_GLOBAL_CANDIDATE_SHORTLIST = 60
MINIMUM_GLOBAL_EVIDENCE_SHORTLIST = 20
MINIMUM_CANDIDATES_PER_SELECTED_MARKET = 10


def _full_score_budget(candidate_count: int) -> int:
    """Score every fetched candidate before any cross-market shortlist cut."""
    return max(1, int(candidate_count))


def _effective_global_shortlist_size(configured: int, available: int) -> int:
    """Protect candidate recall while retaining a bounded global result set.

    Legacy fixed jobs persisted ``deep_count=10``.  That value was divided
    across markets before scoring and silently discarded most candidates.  The
    configured value is still honoured when it is larger, while the recall
    floor upgrades old jobs without touching evidence or trading budgets.
    """
    available = max(0, int(available))
    if available == 0:
        return 0
    return min(available, max(MINIMUM_GLOBAL_CANDIDATE_SHORTLIST, int(configured or 0)))


def _effective_global_evidence_size(configured: int, available: int) -> int:
    """Upgrade legacy evidence budgets so the global Top 20 is always searched.

    Evidence is currently collected inside each market pipeline.  Searching the
    local Top N in every market guarantees that every member of the later
    global Top N has already been controlled, regardless of market mix.  Extra
    locally searched rows are retained as useful evidence rather than hidden.
    """
    available = max(0, int(available))
    if available == 0:
        return 0
    return min(available, max(MINIMUM_GLOBAL_EVIDENCE_SHORTLIST, int(configured or 0)))


def _balanced_global_shortlist(candidates: Sequence[Mapping[str, Any]], size: int,
                               markets: Sequence[str], minimum_per_market: int = MINIMUM_CANDIDATES_PER_SELECTED_MARKET) -> list[dict[str, Any]]:
    """Keep global quality ordering while guaranteeing meaningful market recall."""
    ranked = sorted((dict(row) for row in candidates), key=lambda row: float(row.get("investment_score", 0)), reverse=True)
    size = min(max(0, int(size)), len(ranked))
    if not size:
        return []
    selected = ranked[:size]
    selected_tickers = {str(row.get("ticker") or "").upper() for row in selected}
    for market in markets:
        available = [row for row in ranked if str(row.get("market") or "") == str(market)]
        target = min(int(minimum_per_market), len(available))
        present = sum(str(row.get("market") or "") == str(market) for row in selected)
        for addition in available:
            if present >= target:
                break
            ticker = str(addition.get("ticker") or "").upper()
            if ticker in selected_tickers:
                continue
            removable = next((row for row in reversed(selected) if sum(str(x.get("market") or "") == str(row.get("market") or "") for x in selected) > min(int(minimum_per_market), len([x for x in ranked if str(x.get("market") or "") == str(row.get("market") or "")]))) , None)
            if removable is None:
                break
            selected.remove(removable)
            selected_tickers.discard(str(removable.get("ticker") or "").upper())
            selected.append(addition)
            selected_tickers.add(ticker)
            present += 1
    represented_sectors = {str(row.get("sector") or "Ukjent") for row in selected}
    for sector in dict.fromkeys(str(row.get("sector") or "Ukjent") for row in ranked):
        if sector in represented_sectors:
            continue
        addition = next((row for row in ranked if str(row.get("sector") or "Ukjent") == sector and str(row.get("ticker") or "").upper() not in selected_tickers), None)
        if addition is None:
            continue
        removable = next((row for row in reversed(selected)
                          if sum(str(x.get("sector") or "Ukjent") == str(row.get("sector") or "Ukjent") for x in selected) > 1
                          and sum(str(x.get("market") or "") == str(row.get("market") or "") for x in selected) > min(int(minimum_per_market), len([x for x in ranked if str(x.get("market") or "") == str(row.get("market") or "")]))) , None)
        if removable is None:
            continue
        selected.remove(removable)
        selected_tickers.discard(str(removable.get("ticker") or "").upper())
        selected.append(addition)
        selected_tickers.add(str(addition.get("ticker") or "").upper())
        represented_sectors.add(sector)
    return sorted(selected, key=lambda row: float(row.get("investment_score", 0)), reverse=True)


def report_identity(trigger: str, job_name: str = "", job_id: str = "", *,
                    created_at: datetime | str | None = None,
                    timezone_name: str = DEFAULT_TIMEZONE) -> dict[str, str]:
    """Backward-compatible three-field view of the canonical report identity."""
    identity = build_report_identity_contract(
        trigger, job_name, job_id, created_at=created_at, timezone_name=timezone_name,
    )
    return {key: str(identity.get(key) or "") for key in ("type", "label", "slug")}


def resolve_report_identity(run: Mapping[str, Any]) -> dict[str, str]:
    """Backward-compatible identity view; the full contract lives in ReportDocument."""
    identity = resolve_report_identity_contract(run)
    return {key: str(identity.get(key) or "") for key in ("type", "label", "slug")}


def safe_report_filename(run: Mapping[str, Any], extension: str = "pdf") -> str:
    identity = resolve_report_identity(run)
    job_name = str(run.get("job_name") or "Analyse").strip().replace("–", "-")
    clean = "_".join(part for part in "".join(ch if ch.isalnum() or ch in " _-" else " " for ch in job_name).split())
    stamp = local_compact_stamp(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE))
    # A time-qualified draft already carries its report period. Keep the saved
    # job name in PDF metadata instead of duplicating/misleading in the filename.
    if str(identity.get("type") or "") == "UTKAST" and str(identity.get("slug") or "").startswith("UTKAST_"):
        return f"{identity.get('slug')}_{stamp}.{extension}"
    return f"{identity.get('slug','Rapport')}_{clean}_{stamp}.{extension}"


def job_fingerprint(job: "JobProfile") -> str:
    markets = normalize_markets(job.markets)
    return f"{job.market_profile}|{job.scan_limit}|{job.deep_count}|{job.evidence_analysis_count}|{job.proposal_count}|{','.join(markets)}|{','.join(job.modules)}|{job.user_mission_id}|{job.investment_mission_id}|{job.configuration_version}"


def explicit_job_name_v19220_rc12(
    name: Any,
    *,
    profile_id: Any = "",
    markets: Any = None,
    draft: bool = False,
) -> str:
    """Replace blank/legacy 'Uten navn' labels without changing job settings."""
    clean = str(name or "").strip()
    if clean and clean.casefold() != "uten navn":
        return clean
    profile = market_profile_contract(str(profile_id or ""), markets or [], name=clean)
    countries = [str(value) for value in list(profile.get("expanded_markets") or []) if str(value).strip()]
    scope = " + ".join(countries) if countries else "valgte markeder"
    return f"{'Utkast' if draft else 'Analyse'} – {scope}"


def activated_job_name_v19220_rc1631q(name: Any) -> str:
    """Never present an activated schedule as an autosaved draft."""
    clean = str(name or "").strip()
    if clean.casefold().startswith("utkast –"):
        return "Analyse –" + clean.split("–", 1)[1]
    if clean.casefold().startswith("utkast -"):
        return "Analyse -" + clean.split("-", 1)[1]
    return clean or "Analyse"


def deduplicated_display_name(value: Any) -> str:
    """Collapse repeated display-name segments without changing the stored job."""
    parts = [part.strip() for part in re.split(r"\s*[·|]\s*", str(value or "-")) if part.strip()]
    unique: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.casefold()
        if key not in seen:
            unique.append(part)
            seen.add(key)
    return " · ".join(unique) or "-"


@dataclass
class JobProfile:
    name: str
    markets: list[str] = field(default_factory=lambda: [CORE_MARKET_SCOPE_LABEL])
    market_profile: str = MARKET_PROFILE_CORE
    schedules: list[str] = field(default_factory=lambda: ["08:00", "22:00"])
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    modules: list[str] = field(default_factory=lambda: list(MODULE_OPTIONS))
    scan_limit: int = 25
    deep_count: int = 10
    evidence_analysis_count: int = 10
    proposal_count: int = 5
    coverage_profile_version: str = "3.0"
    min_alert_score: float = 80.0
    notify_pushover: bool = True
    notify_only_changes: bool = True
    notification_mode: str = ""
    include_report_link: bool = True
    include_top3_in_notification: bool = True
    allow_weekends: bool = False
    save_pdf: bool = True
    enabled: bool = True
    scan_windows: list[dict[str, Any]] = field(default_factory=list)
    run_autonomous_portfolio: bool = True
    run_controlled_learning: bool = True
    require_active_portfolio: bool = True
    user_mission_id: str = ""
    investment_mission_id: str = ""
    configuration_version: str = ""
    timezone_name: str = DEFAULT_TIMEZONE
    job_id: str = field(default_factory=lambda: f"MIJ-{uuid.uuid4().hex[:10].upper()}")
    created_at: str = field(default_factory=_now_iso)
    last_run_at: str = ""
    last_status: str = "ALDRI KJØRT"
    last_scheduled_at: str = ""
    last_attempted_at: str = ""
    last_completed_at: str = ""
    last_failed_at: str = ""
    last_notification_status: str = ""
    report_test_series_id: str = ""
    report_test_part: int = 0
    report_test_total: int = 0
    report_test_attempt: int = 0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "JobProfile":
        allowed = {x.name for x in cls.__dataclass_fields__.values()}
        data = {k: v for k, v in dict(value).items() if k in allowed}
        modules = list(data.get("modules") or MODULE_OPTIONS)
        if "Insider Intelligence" not in modules:
            modules.append("Insider Intelligence")
        if "News & Sentiment Intelligence" not in modules:
            modules.append("News & Sentiment Intelligence")
        data["modules"] = modules
        # Saved fixed jobs are authoritative.  Never silently replace their
        # markets or budgets while loading them.  New jobs use the bounded
        # three-market defaults declared by JobProfile and remain editable.
        profile_id = infer_market_profile(
            data.get("markets"), name=data.get("name"), explicit_profile=data.get("market_profile"),
        )
        data["market_profile"] = profile_id
        data["markets"] = profile_market_selections(profile_id, data.get("markets"))
        data["name"] = explicit_job_name_v19220_rc12(
            data.get("name"), profile_id=profile_id, markets=data.get("markets"),
            draft=str(data.get("job_id") or "") == DRAFT_JOB_ID,
        )
        if str(data.get("job_id") or "") != DRAFT_JOB_ID:
            data["name"] = activated_job_name_v19220_rc1631q(data.get("name"))
        data["schedules"] = [normalize_schedule_value(x) for x in list(data.get("schedules") or [])]
        data["timezone_name"] = valid_timezone(data.get("timezone_name"))
        return cls(**data)


def ensure_required_report_jobs(jobs: Sequence[JobProfile]) -> tuple[list[JobProfile], list[dict[str, Any]]]:
    """Repair the three fixed production reports without touching analysis rules."""
    repaired = list(jobs)
    changes: list[dict[str, Any]] = []
    claimed: set[str] = set()
    for spec in REQUIRED_REPORT_SPECS:
        match = next((job for job in repaired if job.job_id == spec["job_id"]), None)
        if match is None:
            known_names = _LEGACY_FIXED_REPORT_NAMES.get(spec["token"], set())
            match = next((
                job for job in repaired
                if job.job_id not in claimed and str(job.name or "").strip().casefold() in known_names
            ), None)
        if match is None:
            match = JobProfile(
                job_id=spec["job_id"], name=spec["name"],
                markets=[CORE_MARKET_SCOPE_LABEL], market_profile=MARKET_PROFILE_CORE,
                schedules=[spec["schedule"]], weekdays=[0, 1, 2, 3, 4],
                enabled=True, allow_weekends=False, notify_pushover=True,
                notify_only_changes=False, notification_mode="ALWAYS", save_pdf=True,
                scan_windows=[], report_test_series_id="", report_test_part=0,
                report_test_total=0, report_test_attempt=0,
            )
            repaired.append(match)
            changes.append({"job_id": match.job_id, "action": "CREATED", "schedule": spec["schedule"]})
            claimed.add(match.job_id)
            continue
        claimed.add(match.job_id)
        # Keep the operator's weekend choice and selected weekdays.  Earlier
        # repairs silently reset both fields on every load, so the visible
        # "Tillat helgekjøring" control could never affect a required report.
        weekdays = sorted(set(int(day) for day in (match.weekdays or [0, 1, 2, 3, 4]) if 0 <= int(day) <= 6))
        if match.allow_weekends:
            weekdays = sorted(set([*weekdays, 5, 6]))
        else:
            weekdays = [day for day in weekdays if day < 5] or [0, 1, 2, 3, 4]
        updated = replace(
            match, job_id=spec["job_id"], name=spec["name"],
            schedules=[spec["schedule"]], weekdays=weekdays,
            timezone_name="Europe/Oslo", enabled=True,
            notify_pushover=True, notify_only_changes=False,
            notification_mode="ALWAYS", include_report_link=True, save_pdf=True,
            scan_windows=[], report_test_series_id="", report_test_part=0,
            report_test_total=0, report_test_attempt=0,
        )
        index = repaired.index(match)
        if asdict(updated) != asdict(match):
            repaired[index] = updated
            changes.append({"job_id": updated.job_id, "action": "REPAIRED", "schedule": spec["schedule"]})

    # Once the stable mandatory identities exist, old fixed profiles must not
    # continue to run in parallel.  Keep them for audit/history, but disable
    # their scheduling.  User-created profiles with other names are untouched.
    required_ids = {spec["job_id"] for spec in REQUIRED_REPORT_SPECS}
    known_legacy_names = set().union(*_LEGACY_FIXED_REPORT_NAMES.values())
    for index, job in enumerate(list(repaired)):
        if job.job_id in required_ids or not job.enabled:
            continue
        if str(job.name or "").strip().casefold() not in known_legacy_names:
            continue
        repaired[index] = replace(job, enabled=False, schedules=[])
        changes.append({"job_id": job.job_id, "action": "DISABLED_DUPLICATE", "schedule": ""})
    return repaired, changes


def load_jobs() -> list[JobProfile]:
    data = read_persistent_json("market_intelligence/jobs.json", default=None)
    if data is None:
        data = _read(JOBS_PATH, [])
        if data:
            write_persistent_json("market_intelligence/jobs.json", data)
    jobs = [JobProfile.from_dict(x) for x in data if isinstance(x, Mapping)]
    # Report-test profiles are ephemeral execution inputs, never schedules.
    jobs = [
        job for job in jobs
        if str(job.job_id or "").upper() != "MI-AUTONOMY-REPORT-TEST"
        and "autonomi rapporttest" not in str(job.name or "").casefold()
    ]
    deduped: dict[str, JobProfile] = {}
    order: list[str] = []
    for job in jobs:
        key = job.name.strip().casefold()
        if key not in deduped:
            deduped[key] = job; order.append(key); continue
        current = deduped[key]
        if (job.enabled, str(job.last_run_at or "")) > (current.enabled, str(current.last_run_at or "")):
            deduped[key] = job
    cleaned = [deduped[key] for key in order]
    source_payload = [dict(x) for x in data if isinstance(x, Mapping)]
    schedules_migrated = any(
        any(str(value or "") in LEGACY_SCHEDULE_MIGRATION for value in list(item.get("schedules") or []))
        for item in source_payload
    )
    names_migrated = any(
        not str(item.get("name") or "").strip() or str(item.get("name") or "").strip().casefold() == "uten navn"
        for item in source_payload
    )
    cleaned, required_changes = ensure_required_report_jobs(cleaned)
    if len(cleaned) != len(jobs) or schedules_migrated or names_migrated or required_changes:
        save_jobs(cleaned)
        _audit("JOB_PROFILES_REPAIRED", {
            "before": len(jobs), "after": len(cleaned),
            "schedules_migrated": schedules_migrated, "names_migrated": names_migrated,
            "required_reports": required_changes,
        })
    return cleaned


def save_jobs(jobs: Sequence[JobProfile]) -> None:
    payload = [asdict(x) for x in jobs]
    _write(JOBS_PATH, payload)
    write_persistent_json("market_intelligence/jobs.json", payload)


def load_draft_job() -> JobProfile:
    """Return the latest auto-saved scheduler draft, or a safe default draft."""
    raw = read_persistent_json(DRAFT_STORAGE_KEY, default=None)
    if isinstance(raw, Mapping):
        try:
            draft = JobProfile.from_dict(raw)
            draft.job_id = DRAFT_JOB_ID
            draft.enabled = False
            normalized_name = explicit_job_name_v19220_rc12(
                draft.name, profile_id=draft.market_profile, markets=draft.markets, draft=True,
            )
            if normalized_name != draft.name:
                draft.name = normalized_name
                payload = asdict(draft); payload["enabled"] = False; payload["last_status"] = "UTKAST"
                write_persistent_json(DRAFT_STORAGE_KEY, payload)
                _audit("DRAFT_NAME_MIGRATED_RC12", {"name": normalized_name})
            return draft
        except Exception:
            pass
    return JobProfile(
        name="Normalanalyse – Norge + Sverige + USA",
        markets=[CORE_MARKET_SCOPE_LABEL],
        schedules=[],
        enabled=False,
        job_id=DRAFT_JOB_ID,
        last_status="UTKAST",
    )


def save_draft_job(job: JobProfile) -> None:
    """Persist editor values as a non-scheduled draft without activating a job."""
    payload = asdict(job)
    payload["job_id"] = DRAFT_JOB_ID
    payload["enabled"] = False
    payload["last_status"] = "UTKAST"
    previous = read_persistent_json(DRAFT_STORAGE_KEY, default={})
    if previous != payload:
        write_persistent_json(DRAFT_STORAGE_KEY, payload)
        _audit("JOB_DRAFT_AUTOSAVED", {"name": payload.get("name"), "markets": payload.get("markets")})


def upsert_job(job: JobProfile) -> None:
    jobs = [x for x in load_jobs() if x.job_id != job.job_id]
    jobs.append(job)
    save_jobs(jobs)
    _audit("JOB_SAVED", {"job_id": job.job_id, "name": job.name})


def delete_job(job_id: str) -> None:
    save_jobs([x for x in load_jobs() if x.job_id != job_id])
    _audit("JOB_DELETED", {"job_id": job_id})


def load_job_history(limit: int = 200) -> list[dict[str, Any]]:
    """Return durable per-job execution history used by the scheduler UI."""
    rows = _read(JOB_HISTORY_PATH, [])
    if not isinstance(rows, list):
        return []
    return [dict(x) for x in rows if isinstance(x, Mapping)][: max(0, int(limit))]


def required_report_delivery_ledger(now: datetime | None = None) -> dict[str, Any]:
    """Daily delivery truth for morning, afternoon and evening reports."""
    now_utc = (now or _now()).astimezone(timezone.utc)
    local_now = now_utc.astimezone(ZoneInfo("Europe/Oslo"))
    jobs = {job.job_id: job for job in load_jobs()}
    history = load_job_history(limit=2000)
    rows: list[dict[str, Any]] = []
    for spec in REQUIRED_REPORT_SPECS:
        job = jobs.get(spec["job_id"])
        hh, mm = (int(part) for part in spec["schedule"].split(":"))
        planned_local = datetime.combine(local_now.date(), time(hh, mm), tzinfo=ZoneInfo("Europe/Oslo"))
        planned_utc = planned_local.astimezone(timezone.utc)
        candidates: list[dict[str, Any]] = []
        for item in history:
            if str(item.get("job_id") or "") != spec["job_id"]:
                continue
            if str(item.get("type") or "").strip().casefold() == "test" or "TEST" in str(item.get("trigger") or "").upper():
                continue
            raw = str(item.get("planned_at") or "").strip()
            if not raw:
                continue
            try:
                item_planned = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                item_planned = item_planned.replace(tzinfo=item_planned.tzinfo or timezone.utc).astimezone(timezone.utc)
            except Exception:
                continue
            if abs((item_planned - planned_utc).total_seconds()) <= 60:
                candidates.append(dict(item))
        latest = candidates[0] if candidates else {}
        delivered_rows = [item for item in candidates if item.get("pushover_sent") is True]
        delivered = bool(delivered_rows)
        pdf_created = any(item.get("pdf") is True for item in candidates)
        stored_row = next((item for item in candidates if item.get("run_id")), latest)
        delivered_row = delivered_rows[0] if delivered_rows else stored_row
        grace_end = planned_utc + timedelta(minutes=30)
        if local_now.weekday() >= 5:
            status = "IKKE_PLANLAGT"
        elif delivered:
            status = "SENDT"
        elif now_utc < planned_utc:
            status = "VENTER"
        elif now_utc <= grace_end:
            status = "PÅGÅR"
        else:
            status = "FORSINKET"
        rows.append({
            "job_id": spec["job_id"], "name": spec["name"], "schedule": spec["schedule"],
            "planned_at": planned_utc.isoformat(timespec="seconds"), "status": status,
            "pdf_created": pdf_created, "stored": bool(stored_row.get("run_id")),
            "pushover_sent": delivered, "run_id": delivered_row.get("run_id") or "",
            "error": "" if delivered else str(latest.get("error") or latest.get("notification_detail") or "")[:500],
            "active": bool(job and job.enabled),
        })
    return {
        "date": local_now.date().isoformat(), "timezone": "Europe/Oslo",
        "complete": all(row["status"] in {"SENDT", "IKKE_PLANLAGT"} for row in rows),
        "rows": rows,
    }


def notify_overdue_required_reports(now: datetime | None = None) -> dict[str, Any]:
    """Send one independent operations warning per missed required report."""
    ledger = required_report_delivery_ledger(now)
    overdue = [row for row in ledger["rows"] if row["status"] == "FORSINKET"]
    receipt_key = "scheduler/required_report_missing_alerts.json"
    receipts = read_persistent_json(receipt_key, default={})
    receipts = dict(receipts) if isinstance(receipts, Mapping) else {}
    sent: list[str] = []
    for row in overdue:
        receipt_id = f"{ledger['date']}:{row['job_id']}"
        if receipts.get(receipt_id):
            continue
        try:
            from notifier import normalize_notification_result, send_pushover_alert
            ok, detail = normalize_notification_result(send_pushover_alert(
                "\n".join([
                    f"Obligatorisk rapport: {row['name']}",
                    f"Planlagt: {row['schedule']} (Europe/Oslo)",
                    "Status: Ikke levert innen 30 minutter",
                    f"PDF: {'opprettet' if row['pdf_created'] else 'ikke bekreftet'}",
                    f"Lagring: {'bekreftet' if row['stored'] else 'ikke bekreftet'}",
                    f"Feil: {row['error'] or 'ingen detalj registrert'}",
                    f"Programversjon: {APP_VERSION}",
                    f"Kjøretid: {__import__('runtime_identity').runtime_label('report_scheduler')}",
                ]),
                title=f"❌ MANGLENDE FAST RAPPORT · {row['name']}",
            ))
            if ok:
                receipts[receipt_id] = {"sent_at": _now_iso(), "job_id": row["job_id"], "detail": str(detail or "Sendt")}
                sent.append(row["job_id"])
        except Exception as exc:
            row["alert_error"] = str(exc)[:500]
    if sent:
        write_persistent_json(receipt_key, receipts)
    return {"ledger": ledger, "overdue": len(overdue), "alerts_sent": sent}


def retry_pending_required_report_deliveries(limit: int = 3) -> dict[str, Any]:
    """Retry PDF/Pushover delivery from stored runs without a new market scan."""
    jobs = {job.job_id: job for job in load_jobs() if job.job_id in {spec["job_id"] for spec in REQUIRED_REPORT_SPECS}}
    attempted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in load_job_history(limit=500):
        job_id = str(row.get("job_id") or "")
        run_id = str(row.get("run_id") or "")
        if job_id not in jobs or not run_id or run_id in seen or row.get("pushover_sent") is True:
            continue
        # Only a real fixed scheduled slot can require delivery repair.
        # Test, manual and revalidation runs reuse the same job profile but
        # must never enter the Pushover repair queue.
        row_type = str(row.get("type") or "").strip().casefold()
        row_trigger = str(row.get("trigger") or "").upper()
        if row_type and row_type != "planlagt":
            continue
        if row_trigger and row_trigger != "SCHEDULED":
            continue
        seen.add(run_id)
        run = load_run(run_id)
        if not run or not bool((run.get("persistence") or {}).get("ok")):
            continue
        run_trigger = str(run.get("trigger") or "").upper()
        if run.get("test_run") or run.get("suppress_notifications") or (run_trigger and run_trigger != "SCHEDULED"):
            continue
        pdf = run.get("pdf_delivery") if isinstance(run.get("pdf_delivery"), Mapping) else {}
        if not (pdf.get("generated") and pdf.get("validated") and pdf.get("published")):
            continue
        notification = run.get("notification") if isinstance(run.get("notification"), Mapping) else {}
        if notification.get("required") is False or notification.get("sent") is True or notification.get("terminal") is True:
            continue
        ok, detail = _notification(jobs[job_id], run)
        expired = str(detail or "").startswith("Varsel utløpt:")
        run["notification"] = {
            **dict(notification), "sent": bool(ok), "attempted": not expired,
            "detail": str(detail or ""),
            "status_label": "Sendt" if ok else ("Utløpt" if expired else "Feilet"),
            "terminal": bool(ok or expired),
            "terminal_reason": "EXPIRED_REPORT" if expired else ("SENT" if ok else ""),
            "delivery_retry": True, "delivery_retry_at": _now_iso(),
        }
        _write(RUNS_DIR / f"{run_id}.json", run)
        _append_job_history({
            "job_id": job_id, "job_name": jobs[job_id].name, "run_id": run_id,
            "type": "Leveringsretry", "started_at": _now_iso(), "completed_at": _now_iso(),
            "planned_at": str(row.get("planned_at") or ""),
            "status": "Fullført" if ok else ("Utløpt" if expired else "Feil"), "pdf": True,
            "pushover_attempted": not expired, "pushover_sent": bool(ok),
            "notification_detail": str(detail or ""),
        })
        attempted.append({"job_id": job_id, "run_id": run_id, "sent": bool(ok), "terminal": bool(ok or expired), "detail": str(detail or "")[:500]})
        if len(attempted) >= max(1, int(limit or 1)):
            break
    return {"attempted": attempted, "sent": sum(1 for row in attempted if row["sent"])}


def _append_job_history(row: Mapping[str, Any]) -> None:
    payload = dict(row)
    payload.setdefault("recorded_at", _now_iso())
    rows = [payload] + load_job_history(limit=999)
    _write(JOB_HISTORY_PATH, rows[:1000])


def _localized_slot(job: JobProfile, local_date: Any) -> list[datetime]:
    """Build scheduled local datetimes for one date, including scan windows."""
    slots: list[datetime] = []
    local_tz = ZoneInfo(valid_timezone(job.timezone_name))
    for slot in job.schedules or []:
        if slot == "Ved appstart":
            continue
        parsed = _parse_hhmm(slot)
        if parsed:
            slots.append(datetime.combine(local_date, time(*parsed), tzinfo=local_tz))
    required_ids = {spec["job_id"] for spec in REQUIRED_REPORT_SPECS}
    windows = [] if job.job_id in required_ids else (job.scan_windows or [])
    for window in windows:
        start_v, end_v = _parse_hhmm(window.get("start", "")), _parse_hhmm(window.get("end", ""))
        if not start_v or not end_v:
            continue
        start_dt = datetime.combine(local_date, time(*start_v), tzinfo=local_tz)
        end_dt = datetime.combine(local_date, time(*end_v), tzinfo=local_tz)
        if end_dt < start_dt:
            end_dt = end_dt + timedelta(days=1)
        interval = max(5, min(1440, int(window.get("interval_minutes", 30) or 30)))
        cursor = start_dt
        while cursor <= end_dt:
            slots.append(cursor)
            cursor += timedelta(minutes=interval)
    return sorted(set(slots))


def _scheduled_history_for_slot_v19220_rc13(job: JobProfile, planned_utc: datetime | None) -> dict[str, Any]:
    """Return the latest durable history row for one exact planned slot."""
    if planned_utc is None:
        return {}
    target = planned_utc.astimezone(timezone.utc)
    matches: list[dict[str, Any]] = []
    for row in load_job_history(limit=1000):
        if str(row.get("job_id") or "") != str(job.job_id or ""):
            continue
        row_type = str(row.get("type") or "").strip().casefold()
        row_trigger = str(row.get("trigger") or "").strip().upper()
        # Legacy scheduled rows predate explicit type/trigger fields.  They are
        # accepted only when both fields are absent; any explicit test,
        # revalidation, manual or repair identity is rejected.
        if (row_type or row_trigger) and (row_type != "planlagt" or row_trigger != "SCHEDULED"):
            continue
        raw = str(row.get("planned_at") or "").strip()
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            value = value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
        except Exception:
            continue
        if abs((value - target).total_seconds()) <= 1:
            matches.append(dict(row))
    return matches[0] if matches else {}


def _latest_scheduled_actual(job: JobProfile) -> datetime | None:
    """Return only a real fixed-slot completion, never test/revalidation time."""
    for row in load_job_history(limit=1000):
        if str(row.get("job_id") or "") != str(job.job_id or ""):
            continue
        row_type = str(row.get("type") or "").strip().casefold()
        row_trigger = str(row.get("trigger") or "").strip().upper()
        if (row_type or row_trigger) and (row_type != "planlagt" or row_trigger != "SCHEDULED"):
            continue
        raw = str(row.get("completed_at") or row.get("report_created_at") or row.get("started_at") or "").strip()
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def schedule_timeline(
    job: JobProfile,
    now: datetime | None = None,
    *,
    authoritative_unattended: bool = False,
) -> dict[str, Any]:
    """Return next/previous slot with restart-aware, durable run classification."""
    now_utc = (now or _now()).astimezone(timezone.utc)
    local_now = as_local(now_utc, job.timezone_name)
    past: list[datetime] = []
    future: list[datetime] = []
    for day_offset in range(-7, 15):
        d = (local_now + timedelta(days=day_offset)).date()
        if d.weekday() not in job.weekdays:
            continue
        if d.weekday() >= 5 and not job.allow_weekends:
            continue
        for slot in _localized_slot(job, d):
            if slot <= local_now:
                past.append(slot)
            else:
                future.append(slot)
    previous_slot = max(past) if past else None
    next_slot = min(future) if future else None
    previous_utc = previous_slot.astimezone(timezone.utc) if previous_slot else None
    latest_scheduled_utc = _latest_scheduled_actual(job)
    try:
        # ``last_run_at`` remains a compatibility fallback for installations
        # with no durable history yet.  As soon as scheduled history exists it
        # is authoritative and non-scheduled rows can no longer pollute health.
        last_run = (
            as_local(latest_scheduled_utc, job.timezone_name)
            if latest_scheduled_utc else
            (as_local(job.last_run_at, job.timezone_name) if job.last_run_at else None)
        )
    except Exception:
        last_run = None

    history = _scheduled_history_for_slot_v19220_rc13(job, previous_utc)
    history_status = str(history.get("status") or "").strip().casefold()
    history_completed = history_status.startswith("fullført")
    history_failed = history_status == "feil"
    completed = bool(
        previous_slot and (history_completed or (last_run and last_run >= previous_slot))
    )
    process_started_utc = SCHEDULER_OBSERVATION_STARTED_AT_UTC_V19220_RC13
    restart_unobserved = bool(
        job.enabled and previous_utc and not history and not completed
        and process_started_utc <= now_utc and previous_utc < process_started_utc
    )
    try:
        unattended_grace_minutes = max(5, int(os.getenv("REPORT_CRON_CATCHUP_MINUTES", "90") or 90))
    except (TypeError, ValueError):
        unattended_grace_minutes = 90
    unattended_slot_age_minutes = (
        max(0.0, (now_utc - previous_utc).total_seconds() / 60.0)
        if previous_utc else None
    )
    authoritative_slot_eligible = bool(
        authoritative_unattended
        and previous_utc
        and unattended_slot_age_minutes is not None
        and unattended_slot_age_minutes <= unattended_grace_minutes
    )
    # A one-shot Render Cron process is the observer by design. Its process
    # start must not make a slot from the same cron window "unobserved".
    unobserved_after_restart = bool(restart_unobserved and not authoritative_slot_eligible)
    grace_minutes = 5
    missed = bool(
        job.enabled and previous_slot and not completed and not history_failed
        and not unobserved_after_restart
        and local_now >= previous_slot + timedelta(minutes=grace_minutes)
    )
    if completed:
        status = "Fullført"
        reason_code = "DURABLE_HISTORY_OR_LAST_RUN"
    elif history_failed:
        status = "Feil"
        reason_code = "DURABLE_HISTORY_FAILED"
    elif unobserved_after_restart:
        status = "Ikke vurdert etter omstart"
        reason_code = "SCHEDULER_PROCESS_STARTED_AFTER_SLOT"
    elif missed:
        status = "Ikke startet"
        reason_code = "OBSERVED_SLOT_WITHOUT_RUN"
    else:
        status = "Venter"
        reason_code = "WITHIN_GRACE_OR_NO_PREVIOUS_SLOT"
    return {
        "job_id": job.job_id,
        "job_name": job.name,
        "enabled": bool(job.enabled),
        "timezone_name": valid_timezone(job.timezone_name),
        "local_now": local_now.isoformat(timespec="seconds"),
        "previous_planned_local": previous_slot.isoformat(timespec="seconds") if previous_slot else "",
        "previous_planned_utc": previous_utc.isoformat(timespec="seconds") if previous_utc else "",
        "next_planned_local": next_slot.isoformat(timespec="seconds") if next_slot else "",
        "next_planned_utc": next_slot.astimezone(timezone.utc).isoformat(timespec="seconds") if next_slot else "",
        "last_actual_local": last_run.isoformat(timespec="seconds") if last_run else "",
        "last_actual_utc": last_run.astimezone(timezone.utc).isoformat(timespec="seconds") if last_run else "",
        "last_planned_status": status,
        "missed": missed,
        "missed_grace_minutes": grace_minutes,
        "unobserved_after_restart": unobserved_after_restart,
        "scheduler_status_reason_code": reason_code,
        "durable_history_status": str(history.get("status") or ""),
        "scheduler_observation_started_at_utc": process_started_utc.isoformat(timespec="seconds"),
        "authoritative_unattended": bool(authoritative_unattended),
        "authoritative_slot_eligible": authoritative_slot_eligible,
        "unattended_slot_age_minutes": round(unattended_slot_age_minutes, 2) if unattended_slot_age_minutes is not None else None,
        "unattended_catchup_minutes": unattended_grace_minutes,
    }


def scheduler_health_snapshot(now: datetime | None = None, *, persist: bool = True, jobs: Sequence[JobProfile] | None = None) -> dict[str, Any]:
    """Human-readable health model for scheduled report execution.

    UI-only reads can disable persistence to avoid an unnecessary durable write
    on every Streamlit rerun. Scheduled/diagnostic callers retain the historical
    persisted snapshot by default.
    """
    jobs = list(jobs) if jobs is not None else load_jobs()
    timelines = [schedule_timeline(job, now) for job in jobs]
    missed = [row for row in timelines if row.get("missed")]
    unobserved = [row for row in timelines if row.get("unobserved_after_restart")]
    next_rows = [row for row in timelines if row.get("next_planned_utc")]
    next_row = min(next_rows, key=lambda r: str(r.get("next_planned_utc"))) if next_rows else {}
    required_ids = {spec["job_id"] for spec in REQUIRED_REPORT_SPECS}
    required_next = [
        row for row in timelines
        if row.get("job_id") in required_ids and row.get("next_planned_utc")
    ]
    required_next.sort(key=lambda row: str(row.get("next_planned_utc")))
    checked = (now or _now()).astimezone(timezone.utc).isoformat(timespec="seconds")
    snapshot = {
        "state": "MISTET_PLANLAGT_KJØRING" if missed else ("OPPSTART_ETTER_PLANLAGT_TID" if unobserved else "OK"),
        "checked_at": checked,
        "active_jobs": sum(1 for job in jobs if job.enabled),
        "jobs": timelines,
        "missed": missed,
        "unobserved_after_restart": unobserved,
        "next": next_row,
        "required_next": required_next,
        "history": load_job_history(limit=50),
    }
    if persist:
        _write(SCHEDULER_HEALTH_PATH, snapshot)
    return snapshot


def _localize_report_decimal_text(value: Any) -> str:
    """Use Norwegian decimal commas while preserving versions, IDs, paths and URLs."""
    return re.sub(
        r"(?<![A-Za-z0-9._/\-])(\d+)\.(\d+)(?!\.\d)(?![A-Za-z0-9_/\-])",
        r"\1,\2",
        str(value if value is not None else "-"),
    )


def build_text_report(run: Mapping[str, Any]) -> str:
    """Render the decision report and a compact technical appendix from ReportDocument."""
    document = ensure_report_document(run)
    metadata = document.get("metadata") or {}
    overview = section_payload(document, "decision_overview", {}) or {}
    confidence = section_payload(document, "confidence_profile", {}) or {}
    reliability = section_payload(document, "report_reliability", {}) or {}
    quality_dimensions = section_payload(document, "quality_dimensions", {}) or {}
    portfolio_intelligence = section_payload(document, "portfolio_intelligence", {}) or {}
    system_anomaly_watch = section_payload(document, "system_anomaly_watch", []) or []
    candidate_watch_queue = section_payload(document, "candidate_watch_queue", []) or []
    changes = section_payload(document, "changes", {}) or {}
    decision_diffs = section_payload(document, "decision_diffs", {}) or {}
    counter_hypotheses = section_payload(document, "counter_hypotheses", {}) or {}
    historical_evaluations = section_payload(document, "historical_evaluations", []) or []
    learning_guard = section_payload(document, "controlled_learning_guard", {}) or {}
    learning_summary = run.get("learning_portfolio_summary") if isinstance(run.get("learning_portfolio_summary"), Mapping) else {}
    candidates = section_payload(document, "candidate_decisions", []) or []
    rejected_control = section_payload(document, "rejected_control_appendix", []) or []
    tasks = section_payload(document, "next_run_tasks", []) or []
    events = section_payload(document, "events", []) or []
    summary_payload = section_payload(document, "executive_summary", {}) or {}
    summary = summary_payload.get("summary") if isinstance(summary_payload, Mapping) else {}
    summary = summary if isinstance(summary, Mapping) else {}
    quality = summary_payload.get("data_quality") if isinstance(summary_payload, Mapping) else {}
    quality = quality if isinstance(quality, Mapping) else {}
    decision_funnel = run.get("decision_funnel") if isinstance(run.get("decision_funnel"), Mapping) else {}
    analytical_buy_count = int(decision_funnel.get("analytical_buy_recommendations") or 0)
    executable_buy_count = int(decision_funnel.get("trade_executable") or decision_funnel.get("eligible") or 0)

    action_labels = {
        "BUY": "Kjøp", "HOLD": "Behold", "SELL": "Selg",
        "SKIP": "Ikke aktuell", "REVIEW": "Undersøk manuelt",
    }
    lines = [
        f"{metadata.get('report_label', 'Rapport')} – beslutningsrapport",
        f"Oppdrag: {metadata.get('mission_label') or '-'}",
        f"Mål: {metadata.get('mission_objective') or '-'}",
        f"Rapport-ID: {metadata.get('report_id') or metadata.get('run_id') or '-'}",
        f"Tid: {metadata.get('created_at_local') or '-'}",
        f"Markeder: {', '.join(summary_payload.get('markets') or [])}",
        f"Appversjon: {metadata.get('app_version') or APP_VERSION}",
        f"Rapportskjema: {metadata.get('report_schema_version') or REPORT_SCHEMA_VERSION}",
        "",
        "BESLUTNINGSSTATUS",
        f"- Beslutningsjustert markedsdatakvalitet: {quality_dimensions.get('market_data_quality', confidence.get('market_data_coverage', 0))}/100",
        f"- Rapportens tekniske dokumentasjonsgrad: {quality_dimensions.get('technical_documentation_coverage', confidence.get('documentation_coverage', confidence.get('data_coverage', 0)))}/100",
        f"- Kandidatenes evidensdekning: {quality_dimensions.get('candidate_evidence_ready_count', 0)} av {quality_dimensions.get('candidate_count', overview.get('candidate_count', len(candidates)))} ({quality_dimensions.get('candidate_evidence_coverage', 0)} %)",
        f"- Uavhengig kildedekning: {quality_dimensions.get('independent_source_coverage', confidence.get('source_confidence', 0))}/100",
        f"- Beslutningsstyrke på rapportnivå: {quality_dimensions.get('report_decision_strength', confidence.get('decision_confidence', 0))}/100",
        f"- Evidens- og dataklare kandidater: {overview.get('evidence_data_ready_count', 0)} av {overview.get('candidate_count', len(candidates))}",
        f"- Analytiske kjøpsanbefalinger: {analytical_buy_count}",
        f"- Gjennomførbare kjøp nå: {executable_buy_count}",
        f"- Produksjonsgodkjente kjøp: {overview.get('decision_ready_count', 0)} av {overview.get('candidate_count', len(candidates))}",
        f"- Konklusjon: {overview.get('conclusion') or '-'}",
        "",
        "RAPPORTENS FOKUS",
    ]
    for item in overview.get("focus") or []:
        lines.append(f"- {item}")

    lines.extend(["", "EKSISTERENDE PORTEFØLJE OG KAPITALBINDING"])
    lines.append(f"- Åpne posisjoner: {portfolio_intelligence.get('open_positions', 0)} av {portfolio_intelligence.get('maximum_open_positions', 20)}")
    lines.append(f"- Sidelengsposisjoner: {portfolio_intelligence.get('sideways_positions', 0)}")
    lines.append(f"- Svekket score: {portfolio_intelligence.get('weakened_positions', 0)}")
    lines.append(f"- Mulige utskiftingsvurderinger: {portfolio_intelligence.get('replacement_review_count', 0)}")
    for row in portfolio_intelligence.get("positions") or []:
        lines.append(
            f"- {row.get('ticker')}: ALLEREDE I PORTEFØLJEN – {row.get('capital_efficiency_status')} · "
            f"eiertid {row.get('holding_days')} dager · resultat {float(row.get('unrealized_pnl_pct') or 0):+.2f} % · "
            f"score {row.get('entry_score')} → {row.get('current_score')} · {row.get('addition_policy')}"
        )
    if system_anomaly_watch:
        lines.extend(["", "AUTOMATISK SYSTEMVAKT"])
        for alert in system_anomaly_watch:
            lines.append(f"- {alert.get('severity')}: {alert.get('message')} ({alert.get('code')})")
    lines.extend(["", "OBSERVASJONSKØ 68-73 – IKKE KJØPSANBEFALINGER"])
    for row in candidate_watch_queue:
        lines.append(f"- {row.get('ticker')}: score {row.get('score')} · {row.get('distance_to_production_threshold')} poeng til 73 · {', '.join(row.get('blocker_codes') or []) or 'ingen annen blokkering'}")

    lines.extend(["", "ENDRINGER SIDEN SIST"])
    if not changes.get("has_previous"):
        lines.append("- Ingen sammenlignbar tidligere rapport er tilgjengelig.")
    else:
        lines.append(f"- Ny i Top 3: {', '.join(changes.get('top3_added') or []) or 'Ingen'}")
        lines.append(f"- Ut av Top 3: {', '.join(changes.get('top3_removed') or []) or 'Ingen'}")
        best = changes.get("largest_improvement") or {}
        weak = changes.get("largest_weakening") or {}
        if best.get("ticker"):
            lines.append(f"- Største forbedring: {best.get('ticker')} {float(best.get('delta') or 0):+.2f}")
        if weak.get("ticker"):
            lines.append(f"- Største svekkelse: {weak.get('ticker')} {float(weak.get('delta') or 0):+.2f}")
        for item in changes.get("action_changes") or []:
            lines.append(f"- Endret handling: {item.get('ticker')} {decision_label(item.get('from'))} → {decision_label(item.get('to'))}")

    lines.extend(["", "DATA-, MODELL- OG BESLUTNINGSDIFF"])
    changed_diffs = [row for row in (decision_diffs.get("candidates") or []) if row.get("has_previous")]
    if changed_diffs:
        for row in changed_diffs[:5]:
            lines.append(f"- {row.get('ticker')}: {row.get('summary') or 'Ingen forklaring'}")
            for component in list(row.get("model_diff") or [])[:2]:
                lines.append(f"   Modell: {component.get('label')} {float(component.get('delta') or 0):+.2f}")
            for rule in list(row.get("decision_diff") or [])[:2]:
                lines.append(f"   Regel: {rule.get('label')} – {rule.get('effect')}")
    else:
        lines.append("- Ingen sammenlignbar beslutningsdiff er tilgjengelig.")

    lines.extend(["", "KANDIDATBESLUTNINGER"])
    # The text channel is part of the canonical report package.  It must never
    # silently truncate a longer public ranking: the real AU run contained 13
    # recommendations while this historic ``[:10]`` limit exported only ten.
    for recommendation_rank, candidate in enumerate(list(candidates), 1):
        raw_action = str(candidate.get("action") or candidate.get("status") or "REVIEW")
        action = decision_label(raw_action)
        display_label = str(candidate.get("decision_label") or candidate.get("status") or action)
        lines.append(f"#{recommendation_rank} {candidate.get('ticker') or '-'} · Beslutning: {display_label}")
        consensus = candidate.get("source_consensus") if isinstance(candidate.get("source_consensus"), Mapping) else {}
        profile = candidate.get("confidence") if isinstance(candidate.get("confidence"), Mapping) else {}
        validity = candidate.get("validity") if isinstance(candidate.get("validity"), Mapping) else {}
        lines.append(f"{recommendation_rank}. {candidate.get('ticker', '-')} ({candidate.get('market', '-')}) – score {candidate.get('score', '-')} – {display_label}")
        lines.append(f"   Kildekonsensus: {consensus.get('level', '-')} · Markedsdata {profile.get('market_data_coverage', 0)} · Dokumentasjon {profile.get('documentation_coverage', profile.get('data_coverage', 0))} · Kilder {profile.get('source_confidence', 0)} · Beslutning {profile.get('decision_confidence', 0)}")
        lines.append(f"   Gyldig til: {validity.get('valid_until') or '-'}")
        for blocker in list(candidate.get("blockers") or [])[:3]:
            lines.append(f"   Hindring: {blocker}")
        for condition in list(candidate.get("change_conditions") or [])[:3]:
            lines.append(f"   Kan endres når: {condition}")
        counter = candidate.get("counter_hypothesis") if isinstance(candidate.get("counter_hypothesis"), Mapping) else {}
        if counter.get("strongest_argument"):
            lines.append(f"   Sterkeste motargument: {counter.get('strongest_argument')}")
        assumptions = list(candidate.get("critical_assumptions") or [])
        if assumptions:
            held = sum(1 for item in assumptions if isinstance(item, Mapping) and item.get("holds"))
            lines.append(f"   Kritiske antakelser: {held}/{len(assumptions)} holder ved rapporttidspunktet")

    lines.extend(["", "KONTROLLVEDLEGG – AVVISTE AKSJER"])
    if rejected_control:
        for row in rejected_control:
            lines.append(f"- {row.get('ticker') or '-'} ({row.get('market') or '-'}) – {row.get('status') or 'Avvist'}: {str(row.get('reason') or '-')[:140]}")
    else:
        lines.append("- Ingen automatisk avviste aksjer.")

    lines.extend(["", "HISTORISK EVALUERING"])
    if historical_evaluations:
        for evaluation in historical_evaluations[:10]:
            return_text = "-" if evaluation.get("price_return_pct") is None else f"{float(evaluation.get('price_return_pct')):+.2f}%"
            outcome = {
                "UTGÅTT_ELLER_MANGLER_DATA": "Utløpt vurdering - resultatdata mangler",
                "EXPIRED_OR_MISSING_DATA": "Utløpt vurdering - resultatdata mangler",
            }.get(str(evaluation.get("outcome") or "").upper(), evaluation.get("outcome") or "-")
            lines.append(f"- {evaluation.get('ticker')}: {outcome} · score {evaluation.get('score_delta') if evaluation.get('score_delta') is not None else '-'} · kurs {return_text}")
    else:
        lines.append("- Ingen utløpte vurderinger kunne evalueres mot denne rapporten.")

    lines.extend(["", "KONTROLLERT LÆRINGSVERN"])
    lines.append(f"- Automatisk endring av produksjonsregler: {'Tillatt' if learning_guard.get('production_rules_auto_change_allowed') else 'Ikke tillatt'}")
    lines.append(f"- Eksplisitt brukergodkjenning: {'Påkrevd' if learning_guard.get('require_explicit_user_approval') else 'Ikke påkrevd'}")

    lines.extend(["", "KANONISKE LÆRINGSHANDLER I DENNE KJØRINGEN"])
    learning_fills = [row for row in learning_summary.get("learning_fills") or [] if isinstance(row, Mapping)]
    if learning_fills:
        for fill in learning_fills:
            action = str(fill.get("side") or fill.get("action") or "-").upper()
            price = _safe_float_v1917(fill.get("price", fill.get("fill_price")))
            quantity = _safe_float_v1917(fill.get("quantity"))
            score = _safe_float_v1917(fill.get("score", fill.get("autonomy_adjusted_investment_score", fill.get("investment_score"))))
            quantity_text = f"{quantity:.8f}".rstrip("0").rstrip(".") or "0"
            lines.append(
                f"- {fill.get('ticker') or '-'} · {action} · antall {quantity_text} · pris {price:.2f} · score {score:.2f}"
            )
    else:
        lines.append("- Ingen læringshandler i denne kjøringen.")

    lines.extend(["", "KRITISKE HENDELSER"])
    if events:
        for event in events[:10]:
            lines.append(f"- {event.get('event_at_local') or event.get('event_at') or '-'} · {event.get('ticker') or 'Marked'} · {event.get('title') or '-'} · {event.get('verification') or '-'}")
    else:
        lines.append("- Ingen kandidatrelaterte hendelser er registrert.")

    lines.extend(["", "OPPGAVER TIL NESTE KJØRING"])
    if tasks:
        for task in tasks[:15]:
            lines.append(f"- [{task.get('status', 'VENTER')}] {task.get('priority', 'NORMAL')} · {task.get('subject')}: {task.get('action')} ({task.get('reason')})")
    else:
        lines.append("- Ingen automatiske oppfølgingsoppgaver er registrert.")

    lines.extend(["", "KVALITETSAVVIK OG FORBEDRINGSPUNKTER"])
    for item in reliability.get("deductions") or []:
        lines.append(f"- −{item.get('points', 0)} poeng: {item.get('reason')}")
    if not reliability.get("deductions"):
        lines.append("- Ingen eksplisitte trekk er registrert.")

    technical = section_payload(document, "technical_status", {}) or {}
    notification = run.get("notification") if isinstance(run.get("notification"), Mapping) else {}
    notification_channels = run.get("notification_channels") if isinstance(run.get("notification_channels"), Mapping) else {}
    learning_notification = notification_channels.get("learning") if isinstance(notification_channels.get("learning"), Mapping) else {}
    lines.extend([
        "",
        "TEKNISK VEDLEGG – KORT STATUS",
        f"- Skannet: {summary.get('scanned', 0)}",
        f"- Grundig analysert: {summary.get('deep_analyzed', 0)}",
        f"- Foreløpige modellkandidater: {summary.get('proposals', 0)}",
        f"- Teknisk markedsdatadekning: {quality.get('score', '-')} {quality.get('label', '')}".strip(),
        f"- Pushover: {notification.get('status_label') or notification.get('detail') or 'Ikke registrert'}",
        f"- Pushover – læring: {learning_notification.get('status_label') or 'Ikke registrert'} ({int(learning_notification.get('sent_count') or 0)} sendt)",
    ])
    for error in technical.get("errors") or []:
        lines.append(f"- Feil: {error}")
    for warning in technical.get("warnings") or []:
        lines.append(f"- Advarsel: {warning}")
    lines.extend([
        "",
        "Datadekning, kildesikkerhet og beslutningssikkerhet er ikke sannsynlighet for gevinst.",
        "Rapporten er beslutningsstøtte og utfører ingen ekte handler automatisk.",
    ])
    return "\n".join(_localize_report_decimal_text(x) for x in lines)



def _safe_float_v1917(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except Exception:
        return default


def _notification_status_explanation(notification: Mapping[str, Any] | None) -> str:
    """Return one user-safe sentence explaining notification state."""
    row = dict(notification or {})
    detail = str(row.get("detail") or row.get("skipped_reason") or "").strip()
    if row.get("sent") is True or str(row.get("status") or "").upper() in {"SENT", "OK", "SUCCESS"}:
        return "Pushover sendt"
    if row.get("attempted"):
        return "Pushover forsøkt, men ikke sendt" + (f": {detail}" if detail else "")
    if row.get("test_run") is True or "test uten varsling" in detail.casefold():
        return "Ikke sendt – testkjøring med rapportvarsling deaktivert"
    if detail:
        return "Pushover ikke forsøkt: " + detail
    return "Pushover ikke forsøkt: Ingen varslingsbeslutning registrert"


def _news_score_v1917(candidate: Mapping[str, Any]) -> float:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    for key in ("news_score", "sentiment_score", "news_sentiment_score"):
        if key in raw:
            return _safe_float_v1917(raw.get(key), 0.0)
        if key in candidate:
            return _safe_float_v1917(candidate.get(key), 0.0)
    news = raw.get("news_intelligence") if isinstance(raw.get("news_intelligence"), Mapping) else {}
    for key in ("score", "sentiment_score", "confidence", "signal_score"):
        if key in news:
            return _safe_float_v1917(news.get(key), 0.0)
    return 0.0




def _has_verified_news_evidence(candidate: Mapping[str, Any]) -> bool:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    news = raw.get("news_intelligence") if isinstance(raw.get("news_intelligence"), Mapping) else {}
    readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
    status = str(readiness.get("news") or news.get("coverage") or news.get("status") or "").upper()
    events = [row for row in news.get("events") or [] if isinstance(row, Mapping)]
    verified_count = int(news.get("verified_fact_count") or news.get("verified_facts") or 0)
    return bool(events or verified_count > 0 or status == "VERIFIED_FACTS_FOUND")

def _candidate_blockers_v1917(candidate: Mapping[str, Any], *, threshold: float = 73.0) -> list[str]:
    blockers: list[str] = []
    score = _safe_float_v1917(candidate.get("investment_score"), 0.0)
    if score < threshold:
        blockers.append(f"score {score:.1f} er under terskel {threshold:.1f}")
    readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
    outcome = str(candidate.get("autonomy_outcome_code") or "").upper()
    allowed = str(readiness.get("allowed_action") or candidate.get("portfolio_action") or "").upper()
    if outcome and outcome != "KJØPSKANDIDAT":
        blockers.append(f"Autonomiutfallet er {decision_label(outcome).lower()}")
    elif allowed and allowed not in {"BUY", "KJØP"}:
        blockers.append("porteføljelaget kjøpsgodkjenner ikke kandidaten")
    validity = str((candidate.get("data_contract") or {}).get("validity") or "").upper()
    if validity and validity not in {"VALID", "GYLDIG"}:
        blockers.append("datakontrakten er ikke fullt gyldig")
    if str(readiness.get("news") or "").upper() not in {"", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}:
        blockers.append("nyhetsgrunnlaget er ikke ferdig verifisert")
    if str(readiness.get("insider") or "").upper() not in {"", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}:
        blockers.append("innsidergrunnlaget er ikke ferdig verifisert")
    if not blockers:
        blockers.append("samlet score, risiko eller porteføljeport var svakere enn Top 3-kandidatene")
    return blockers[:3]


def build_ranking_explanation(run: Mapping[str, Any]) -> dict[str, Any]:
    """Explain raw score, evidence shortlist and final decision ranking."""
    candidates = [dict(x) for x in (run.get("candidates") or []) if isinstance(x, Mapping)]
    raw_top3 = [dict(x) for x in (run.get("raw_top3") or []) if isinstance(x, Mapping)] or candidates[:3]
    evidence_top3 = [dict(x) for x in (run.get("evidence_ready_top3") or []) if isinstance(x, Mapping)]
    final_top3 = [dict(x) for x in (run.get("final_decision_top3") or run.get("decision_ready_top3") or []) if isinstance(x, Mapping)]
    verified_news = [row for row in candidates if _has_verified_news_evidence(row)]
    news_ranked = sorted(verified_news, key=_news_score_v1917, reverse=True)
    top_news = news_ranked[0] if news_ranked else {}
    evidence_tickers = {str(x.get("ticker") or "").upper() for x in evidence_top3}
    final_tickers = {str(x.get("ticker") or "").upper() for x in final_top3}
    threshold = _safe_float_v1917((run.get("portfolio_decisions") or {}).get("production_threshold"), 73.0)
    top_news_ticker = str(top_news.get("ticker") or "").upper()
    note = "Ingen verifiserte nyhetshendelser ga grunnlag for en egen nyhetsleder."
    blockers: list[str] = []
    if top_news and top_news_ticker not in evidence_tickers:
        blockers = _candidate_blockers_v1917(top_news, threshold=threshold)
        note = (
            f"{top_news_ticker} hadde høyest dokumenterte nyhetsbidrag ({_news_score_v1917(top_news):.1f}), "
            f"men er ikke i evidens- og dataklar kortliste fordi " + "; ".join(blockers) + "."
        )
    elif top_news and top_news_ticker not in final_tickers:
        note = (
            f"{top_news_ticker} hadde høyest dokumenterte nyhetsbidrag og bestod evidens- og dataporten, "
            "men er ikke kjøpsgodkjent av endelig portefølje- og risikoport."
        )
    elif top_news:
        note = f"{top_news_ticker} hadde høyest dokumenterte nyhetsbidrag og er kjøpsgodkjent i sluttlisten."
    return {
        "news_leader": top_news,
        "news_score": round(_news_score_v1917(top_news), 2) if top_news else 0,
        "raw_top3_count": min(3, len(raw_top3)),
        "evidence_top3_count": min(3, len(evidence_top3)),
        "decision_top3_count": min(3, len(final_top3)),
        "decision_top3_complete": len(final_top3) >= 3,
        "note": note,
        "blockers": blockers,
        "ranking_types": [
            {"name": "Prioritert vurderingsrekkefølge 1-3", "description": "Kandidatene som bør vurderes først. Rangeringen er ikke en kjøpsanbefaling og viser Autonomis konkrete utfall."},
            {"name": "Dokumentert nyhetsrangering", "description": "Nyhetsbidrag basert på verifiserte hendelser; nøytral modellbaseline regnes ikke som nyhetsleder."},
            {"name": "Rå rangering", "description": "Samlet score før alle data-, evidens-, portefølje- og risikoporter."},
            {"name": "Kjøpsgodkjent liste", "description": "Kun kandidater som har bestått data-, evidens-, portefølje- og risikoporten."},
        ],
    }


def build_autonomy_candidate_handoff(run: Mapping[str, Any], autonomous_chain: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Trace candidate counts from report to Autonomi.

    This is the diagnostic the UI lacked when Autonomi received zero candidates.
    """
    candidates = [dict(x) for x in (run.get("candidates") or []) if isinstance(x, Mapping)]
    proposals = [dict(x) for x in (run.get("proposals") or []) if isinstance(x, Mapping)]
    decision_ready = [dict(x) for x in (run.get("decision_ready_top3") or []) if isinstance(x, Mapping)]
    chain = dict(autonomous_chain or run.get("autonomous_chain") or {})
    stages = chain.get("stages") if isinstance(chain.get("stages"), list) else []
    market_stage = next((s for s in stages if s.get("name") == "MARKET_SCAN"), {})
    market_detail = market_stage.get("detail") if isinstance(market_stage.get("detail"), Mapping) else {}
    autonomous_stage = next((s for s in stages if s.get("name") == "AUTONOMOUS_PORTFOLIO"), {})
    autonomous_detail = autonomous_stage.get("detail") if isinstance(autonomous_stage.get("detail"), Mapping) else {}
    buy_candidates = [x for x in candidates if str(x.get("portfolio_action") or "").upper() == "BUY"]
    review_candidates = [x for x in candidates if str(x.get("autonomy_outcome_code") or "").upper() == "UNDERSØK_MANUELT"]
    received = int(market_detail.get("candidates") or 0)
    avvik = bool(candidates and received == 0)
    reason = str(autonomous_detail.get("reason") or "")
    learning_buys = int(autonomous_detail.get("learning_buys") or 0)
    theoretical_buys = int(autonomous_detail.get("buys") or 0)
    return {
        "version": APP_VERSION,
        "report_candidates": len(candidates),
        "report_proposals": len(proposals),
        "decision_ready_candidates": len(decision_ready),
        "buy_candidates": len(buy_candidates),
        "review_candidates": len(review_candidates),
        "sent_to_autonomy": received,
        "autonomy_stage_status": autonomous_stage.get("status") or "IKKE_KJØRT",
        "autonomy_reason": reason,
        "theoretical_buys": theoretical_buys,
        "learning_buys": learning_buys,
        "learning_probe_mode": bool(market_detail.get("learning_probe_mode") or (market_detail.get("handoff_input") or {}).get("learning_probe_mode")),
        "mismatch": avvik,
        "warning": (
            "Rapporten har kandidater, men Autonomi mottok 0. Kandidatoverlevering må kontrolleres."
            if avvik else "Kandidatoverlevering registrert."
        ),
    }

def safe_ascii_report_filename(run: Mapping[str, Any], extension: str = "txt") -> str:
    raw = safe_report_filename(run, extension)
    replacements = str.maketrans({"æ": "ae", "ø": "o", "å": "a", "Æ": "Ae", "Ø": "O", "Å": "A"})
    ascii_name = raw.translate(replacements)
    ascii_name = "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "._-")) else "_" for ch in ascii_name)
    while "__" in ascii_name:
        ascii_name = ascii_name.replace("__", "_")
    return ascii_name.strip("_") or f"rapport.{extension}"


def durable_json_download(run: Mapping[str, Any]) -> dict[str, Any]:
    """Materialise report JSON under Streamlit's static directory.

    ``st.download_button`` owns a session-bound media object which can vanish
    during report-progress reruns.  A static file survives those reruns and is
    streamed by the web service instead of being retained as another widget
    payload in browser/session memory.
    """
    # Compact encoding materially lowers both iPhone transfer size and the
    # transient duplicate-memory peak on the 2 GiB Render service.  The JSON
    # remains complete and standards-compliant; only cosmetic whitespace is
    # omitted.
    payload = json.dumps(run or {}, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    filename = safe_report_filename(run, "json")
    token = str(run.get("public_report_token") or "").strip()
    if len(token) < 32:
        import hashlib
        token = hashlib.sha256(payload).hexdigest()
    safe_token = "".join(ch for ch in token if ch.isalnum() or ch in "-_")
    stored_name = f"public_report_{safe_token}.json"
    target = PUBLIC_REPORT_DIR / stored_name
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return {
        "data": payload,
        "filename": filename,
        "url": f"/app/static/reports/{quote(stored_name)}",
        "size": len(payload),
    }


def render_durable_json_download(
    st, run: Mapping[str, Any], *, label: str = "{ } Last ned JSON", instance_key: str = "report",
) -> None:
    delivery = durable_json_download(run)
    from mobile_file_delivery import render_mobile_file_delivery
    render_mobile_file_delivery(
        st, url=str(delivery["url"]), filename=str(delivery["filename"]),
        label=label, mime="application/json", data=bytes(delivery["data"]),
        key=f"json_{str(run.get('run_id') or run.get('report_id') or 'report')}",
        instance_key=instance_key,
    )
    st.caption(f"Varig JSON-fil · {int(delivery['size']) / (1024 * 1024):.1f} MB")


def _candidate_map(run: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(x.get("ticker")): dict(x) for x in (run.get("candidates") or []) if x.get("ticker")}


def compare_runs(current: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    cur, prev = _candidate_map(current), _candidate_map(previous or {})
    new = [compact_candidate_reference(cur[t]) for t in cur.keys() - prev.keys()]
    dropped = [compact_candidate_reference(prev[t]) for t in prev.keys() - cur.keys()]
    improved, weakened, unchanged = [], [], []
    for ticker in cur.keys() & prev.keys():
        delta = round(float(cur[ticker].get("investment_score", 0)) - float(prev[ticker].get("investment_score", 0)), 2)
        component_labels = {
            "discovery_score": "AI Discovery", "fundamental_score": "Fundamentaler",
            "research_score": "Analyse", "validation_score": "Historisk test",
            "portfolio_fit_score": "Porteføljetilpasning", "risk_score": "Risiko",
        }
        drivers = []
        for key_name, label in component_labels.items():
            change = round(float(cur[ticker].get(key_name, 0) or 0) - float(prev[ticker].get(key_name, 0) or 0), 2)
            if abs(change) >= 0.5:
                drivers.append({"component": label, "delta": change})
        drivers.sort(key=lambda x: abs(float(x["delta"])), reverse=True)
        row = {**compact_candidate_reference(cur[ticker]), "score_delta": delta, "previous_rank": prev[ticker].get("rank"), "change_drivers": drivers[:4]}
        if delta >= 2:
            improved.append(row)
        elif delta <= -2:
            weakened.append(row)
        else:
            unchanged.append(row)
    key = lambda x: abs(float(x.get("score_delta", 0)))
    return {
        "new": sorted(new, key=lambda x: float(x.get("investment_score", 0)), reverse=True),
        "improved": sorted(improved, key=key, reverse=True),
        "weakened": sorted(weakened, key=key, reverse=True),
        "dropped": dropped,
        "unchanged_count": len(unchanged),
    }


def _update_history(run: Mapping[str, Any]) -> None:
    history = _read(HISTORY_PATH, {})
    stamp = run.get("created_at") or _now_iso()
    for row in run.get("candidates") or []:
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        item = history.setdefault(ticker, {"first_seen": stamp, "observations": []})
        item["last_seen"] = stamp
        item["observations"].append({"at": stamp, "rank": row.get("rank"), "score": row.get("investment_score"), "market": row.get("market")})
        item["observations"] = item["observations"][-250:]
        ranks = [x.get("rank") for x in item["observations"] if isinstance(x.get("rank"), int)]
        scores = [float(x.get("score", 0)) for x in item["observations"]]
        item["times_in_list"] = len(item["observations"])
        item["best_rank"] = min(ranks) if ranks else None
        item["average_score"] = round(sum(scores) / len(scores), 2) if scores else 0
    _write(HISTORY_PATH, history)


def _load_report_archive() -> list[dict[str, Any]]:
    # v19.2.0: PostgreSQL/repository is authoritative when configured.
    try:
        from repositories.application import get_repository_registry
        repo = get_repository_registry().reports
        if repo.storage.using_postgres():
            rows = repo.list()
            if rows:
                return [dict(x) for x in rows if isinstance(x, Mapping)]
    except Exception as exc:
        logging.warning("ReportRepository read failed; durable compatibility fallback used: %s", exc)
    rows = _read(REPORT_ARCHIVE_PATH, [])
    if not rows:
        legacy = read_persistent_json("market_intelligence/report_archive.json", default=[])
        if isinstance(legacy, list) and legacy:
            rows = legacy
            _write(REPORT_ARCHIVE_PATH, rows)
            _audit("REPORT_ARCHIVE_MIGRATED_TO_DURABLE_STORAGE", {"reports": len(rows)})
    # Promote legacy data to PostgreSQL without deleting the compatibility copy.
    try:
        from repositories.application import get_repository_registry
        repo = get_repository_registry().reports
        if repo.storage.using_postgres() and rows:
            repo.replace_all(rows)
    except Exception as exc:
        logging.warning("ReportRepository promotion failed: %s", exc)
    return [dict(x) for x in rows if isinstance(x, Mapping)]


def _save_report_archive(rows: Sequence[Mapping[str, Any]]) -> None:
    payload = [dict(x) for x in rows]
    repository_written = False
    try:
        from repositories.application import get_repository_registry
        repo = get_repository_registry().reports
        repository_written = bool(repo.replace_all(payload))
    except Exception as exc:
        logging.warning("ReportRepository write failed; compatibility storage used: %s", exc)
    # Compatibility mirror remains during the v19.2 transition. It is not the
    # production source of truth when PostgreSQL is available.
    _write(REPORT_ARCHIVE_PATH, payload)
    write_persistent_json("market_intelligence/report_archive.json", payload)


def _archive_entry(run: Mapping[str, Any]) -> dict[str, Any]:
    document = ensure_report_document(run)
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    candidates = list(run.get("candidates") or [])
    top = candidates[0] if candidates else {}
    identity = resolve_report_identity(run)
    report_status = run.get("report_status") if isinstance(run.get("report_status"), Mapping) else {}
    revision = run.get("report_revision") if isinstance(run.get("report_revision"), Mapping) else {}
    decision_overview = section_payload(document, "decision_overview", {}) or {}
    report_reliability = section_payload(document, "report_reliability", {}) or {}
    quality_dimensions = section_payload(document, "quality_dimensions", {}) or {}
    report_changes = section_payload(document, "changes", {}) or {}
    next_tasks = section_payload(document, "next_run_tasks", []) or []
    report_events = section_payload(document, "events", []) or []
    source_health = run.get("source_health") if isinstance(run.get("source_health"), Mapping) else {}
    source_rows = list(source_health.get("sources") or [])
    reserve_feed_used = any(bool(row.get("fallback_used")) for row in source_rows if isinstance(row, Mapping))
    source_error_count = sum(int(row.get("errors") or 0) for row in source_rows if isinstance(row, Mapping))
    return {
        "run_id": run.get("run_id"), "created_at": run.get("created_at"),
        "operations_trace_id": run.get("operations_trace_id") or "",
        "result_id": (run.get("canonical_result") or {}).get("result_id"),
        "created_at_local": local_display(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE)),
        "timezone_name": valid_timezone(run.get("timezone_name")), "job_name": run.get("job_name"),
        "trigger": str(run.get("trigger") or ""),
        "history_kind": "REVALIDATION" if str(run.get("trigger") or "").upper() == "REVALIDATION" else "REPORT",
        "report_type": identity.get("type"), "report_label": identity.get("label"),
        "report_id": metadata.get("report_id") or run.get("run_id"),
        "mission_code": metadata.get("mission_code") or identity.get("mission_code"),
        "mission_label": metadata.get("mission_label") or identity.get("mission_label"),
        "app_version": metadata.get("app_version") or APP_VERSION,
        "report_schema_version": metadata.get("report_schema_version") or REPORT_SCHEMA_VERSION,
        "report_contract_version": metadata.get("contract_version") or "1.0",
        "pdf_path": run.get("pdf_path"), "json_path": str(RUNS_DIR / f"{run.get('run_id')}.json"),
        "public_pdf_name": run.get("public_pdf_name"), "report_url": report_public_url(run),
        "technical_pdf_path": run.get("technical_pdf_path"),
        "technical_pdf_name": run.get("technical_pdf_name"),
        "technical_report_token": run.get("technical_report_token"),
        "technical_pdf_delivery": run.get("technical_pdf_delivery"),
        "markets": list(run.get("markets") or []), "recommended": int((run.get("summary") or {}).get("recommended", 0)),
        "top_ticker": top.get("ticker"), "top_score": top.get("investment_score"),
        "tickers": [str(x.get("ticker")) for x in candidates if x.get("ticker")],
        "favorite": False, "analysis_aborted": bool(run.get("analysis_aborted")),
        "report_state": report_status.get("state") or "LEGACY",
        "report_status_label": report_status.get("label") or "",
        "revalidation_required": bool(report_status.get("revalidation_required")),
        "report_series_id": revision.get("series_id") or "",
        "report_revision": revision.get("revision") or 1,
        "report_revision_label": revision.get("revision_label") or "R1",
        "supersedes_run_id": revision.get("supersedes_run_id") or "",
        "content_sha256": revision.get("content_sha256") or "",
        # Legacy compatibility values are retained in the archive payload but
        # not used as a user-facing single quality indicator in RC8.
        "report_reliability": int(report_reliability.get("score") or 0),
        "report_reliability_label": report_reliability.get("label") or "",
        "report_decision_strength": int(quality_dimensions.get("report_decision_strength") or 0),
        "candidate_evidence_coverage": float(quality_dimensions.get("candidate_evidence_coverage") or 0),
        "decision_ready_count": int(decision_overview.get("decision_ready_count") or 0),
        "candidate_count": int(decision_overview.get("candidate_count") or len(candidates)),
        "top3_changed": bool(report_changes.get("top3_changed")),
        "urgent_task_count": int(decision_overview.get("urgent_task_count") or 0),
        "next_task_count": len(next_tasks),
        "upcoming_event_count": len(report_events),
        "has_errors": bool(run.get("errors") or source_error_count),
        "error_count": len(run.get("errors") or []) + source_error_count,
        "reserve_feed_used": reserve_feed_used,
        "low_reliability": int(quality_dimensions.get("report_decision_strength") or 0) < 65,
    }


def archive_report(run: Mapping[str, Any]) -> None:
    with _ARCHIVE_LOCK:
        entry = _archive_entry(run)
        rows = [x for x in _load_report_archive() if x.get("run_id") != entry.get("run_id")]
        rows.insert(0, entry)
        # Compact searchable history. Canonical runs and protected decision /
        # portfolio ledgers remain in their dedicated stores.
        _save_report_archive(rows[:180])


def verify_report_persistence(run_id: str) -> dict[str, Any]:
    """Read-after-write proof used before a background job may claim success."""
    run_id = str(run_id or "")
    stored = load_run(run_id) if run_id else {}
    archived = next((dict(x) for x in _load_report_archive() if str(x.get("run_id") or "") == run_id), None)
    ok = bool(run_id and stored.get("run_id") == run_id and archived)
    return {
        "ok": ok, "run_id": run_id, "run_json_saved": bool(stored),
        "archive_saved": bool(archived), "archive_entry": archived or {},
        "error": "" if ok else "Rapporten kunne ikke bekreftes i både kjøringslager og rapportarkiv",
    }


def set_report_favorite(run_id: str, favorite: bool) -> None:
    rows = _load_report_archive()
    for row in rows:
        if row.get("run_id") == run_id:
            row["favorite"] = bool(favorite)
    _save_report_archive(rows)


def delete_archived_report(run_id: str) -> bool:
    rows = _load_report_archive()
    target = next((x for x in rows if x.get("run_id") == run_id), None)
    if not target:
        return False
    for key in ("pdf_path", "technical_pdf_path", "json_path"):
        raw = target.get(key)
        if raw:
            try:
                path = Path(str(raw))
                if path.exists() and ROOT in path.parents:
                    path.unlink()
            except Exception:
                pass
    _save_report_archive([x for x in rows if x.get("run_id") != run_id])
    _audit("REPORT_DELETED", {"run_id": run_id})
    return True


def report_public_url(run: Mapping[str, Any]) -> str:
    return public_report_url(run)


def restore_public_reports(limit: int = 25) -> int:
    """Restore unlisted static PDFs after a Render restart or deploy."""
    restored = 0
    for entry in _load_report_archive()[:max(0, int(limit))]:
        run_id = str(entry.get("run_id") or "")
        run = load_run(run_id) if run_id else {}
        if not run:
            continue
        name = str(run.get("public_pdf_name") or entry.get("public_pdf_name") or "").strip()
        if name:
            run["public_pdf_name"] = name
            target = PUBLIC_REPORT_DIR / Path(name).name
            if target.exists():
                continue
        try:
            source = Path(str(run.get("pdf_path") or ""))
            pdf_bytes = source.read_bytes() if source.is_file() else build_main_pdf(run)
            publish_pdf(run, pdf_bytes)
            _write(RUNS_DIR / f"{run_id}.json", run)
            restored += 1
        except Exception as exc:
            _audit("PUBLIC_REPORT_RESTORE_FAILED", {"run_id": run_id, "error": str(exc)})
    return restored


def _valid_pdf_bytes(value: bytes | bytearray | None) -> bool:
    """Reject empty/error payloads before exposing a PDF download."""
    return bool(value and len(value) >= 5 and bytes(value[:5]) == b"%PDF-")


def load_archived_run(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Recover the canonical run from durable storage or the archived JSON path."""
    archived = dict(entry or {})
    run_id = str(archived.get("run_id") or "")
    run = load_run(run_id) if run_id else {}
    if run:
        return dict(run)
    json_path = Path(str(archived.get("json_path") or ""))
    if json_path.is_file():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                return dict(payload)
        except Exception as exc:
            _audit("ARCHIVED_JSON_RECOVERY_FAILED", {"run_id": run_id, "error": str(exc)})
    return {}


def resolve_report_delivery(run: Mapping[str, Any], entry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a durable public PDF, regenerating it from the canonical JSON.

    Streamlit download endpoints are session-bound and can disappear on a
    rerun.  Archive downloads therefore prefer the static public copy and only
    fall back to a validated in-memory payload.
    """
    clean = dict(run or {})
    archived = dict(entry or {})
    if not clean:
        return {"ok": False, "error": "Rapportdata mangler og PDF-en kan ikke gjenopprettes."}
    name = str(clean.get("public_pdf_name") or archived.get("public_pdf_name") or "").strip()
    target = PUBLIC_REPORT_DIR / Path(name).name if name else None
    pdf_bytes: bytes | None = None
    if target and target.is_file():
        candidate = target.read_bytes()
        if _valid_pdf_bytes(candidate):
            pdf_bytes = candidate
    if pdf_bytes is None:
        source = Path(str(clean.get("pdf_path") or archived.get("pdf_path") or ""))
        if source.is_file():
            candidate = source.read_bytes()
            if _valid_pdf_bytes(candidate):
                pdf_bytes = candidate
    regenerated = False
    if pdf_bytes is None:
        try:
            candidate = build_main_pdf(clean)
            if not _valid_pdf_bytes(candidate):
                raise ValueError("PDF-generatoren returnerte ikke et gyldig PDF-dokument")
            pdf_bytes = candidate
            regenerated = True
        except Exception as exc:
            _audit("REPORT_REGENERATION_FAILED", {"run_id": clean.get("run_id"), "error": str(exc)})
            return {"ok": False, "error": f"Rapporten finnes ikke lokalt og kunne ikke regenereres: {exc}"}
    try:
        publish_pdf(clean, pdf_bytes)
        run_id = str(clean.get("run_id") or "")
        if run_id:
            _write(RUNS_DIR / f"{run_id}.json", clean)
        url = report_public_url(clean)
        if run_id:
            archive_rows = _load_report_archive()
            changed = False
            for row in archive_rows:
                if str(row.get("run_id") or "") == run_id:
                    row.update({
                        "pdf_path": clean.get("pdf_path"),
                        "public_pdf_name": clean.get("public_pdf_name"),
                        "report_url": url,
                        "pdf_validated": True,
                        "pdf_regenerated": regenerated,
                    })
                    changed = True
                    break
            if changed:
                _save_report_archive(archive_rows)
    except Exception as exc:
        url = ""
        _audit("PUBLIC_REPORT_PUBLISH_FAILED", {"run_id": clean.get("run_id"), "error": str(exc)})
    return {
        "ok": True, "url": url, "data": pdf_bytes,
        "filename": safe_report_filename(clean, "pdf"), "regenerated": regenerated,
        "validated": True,
    }


def resolve_technical_report_delivery(
    run: Mapping[str, Any], entry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete PDF with technical appendix across Render services."""
    clean = dict(run or {})
    archived = dict(entry or {})
    if not clean:
        return {"ok": False, "error": "Rapportdata mangler og det tekniske vedlegget kan ikke gjenopprettes."}
    from public_report_store import load_public_pdf, publish_durable_pdf
    token = str(clean.get("technical_report_token") or archived.get("technical_report_token") or "").strip()
    pdf_bytes: bytes | None = None
    if token:
        stored = load_public_pdf(token)
        candidate = stored.get("data") if isinstance(stored, Mapping) else None
        if _valid_pdf_bytes(candidate):
            pdf_bytes = bytes(candidate)
    if pdf_bytes is None:
        source = Path(str(clean.get("technical_pdf_path") or archived.get("technical_pdf_path") or ""))
        if source.is_file():
            candidate = source.read_bytes()
            if _valid_pdf_bytes(candidate):
                pdf_bytes = candidate
    regenerated = False
    if pdf_bytes is None:
        try:
            pdf_bytes = build_technical_pdf(clean)
            if not _valid_pdf_bytes(pdf_bytes):
                raise ValueError("PDF-generatoren returnerte ikke et gyldig teknisk dokument")
            regenerated = True
        except Exception as exc:
            _audit("TECHNICAL_REPORT_REGENERATION_FAILED", {"run_id": clean.get("run_id"), "error": str(exc)})
            return {"ok": False, "error": f"Det tekniske vedlegget kunne ikke regenereres: {exc}"}
    run_id = str(clean.get("run_id") or "")
    clean["technical_pdf_name"] = Path(str(
        clean.get("technical_pdf_name") or archived.get("technical_pdf_name")
        or f"{safe_report_filename(clean, 'pdf')[:-4]}_technical.pdf"
    )).name
    try:
        publish_durable_pdf(
            clean, pdf_bytes, token_field="technical_report_token",
            filename_field="technical_pdf_name", document_kind="technical",
        )
        clean["technical_pdf_delivery"] = {
            "generated": True, "validated": True, "durable": True,
            "regenerated": regenerated,
        }
        if run_id:
            _write(RUNS_DIR / f"{run_id}.json", clean)
            rows = _load_report_archive()
            for row in rows:
                if str(row.get("run_id") or "") == run_id:
                    row.update({key: clean.get(key) for key in (
                        "technical_pdf_path", "technical_pdf_name",
                        "technical_report_token", "technical_pdf_delivery",
                    )})
                    _save_report_archive(rows)
                    break
    except Exception as exc:
        _audit("TECHNICAL_REPORT_PUBLISH_FAILED", {"run_id": run_id, "error": str(exc)})
    return {
        "ok": True, "data": pdf_bytes, "filename": clean["technical_pdf_name"],
        "regenerated": regenerated, "validated": True,
    }


def _notification_mode(job: JobProfile) -> str:
    mode = str(getattr(job, "notification_mode", "") or "").strip().upper()
    if mode in {"ALWAYS", "CHANGES_ONLY", "ERRORS_ONLY"}:
        return mode
    if "morgen" in str(job.name or "").casefold():
        return "ALWAYS"
    normalized_name = str(job.name or "").casefold()
    if any(token in normalized_name for token in ("kveld", "evening")):
        return "ALWAYS"
    return "CHANGES_ONLY" if job.notify_only_changes else "ALWAYS"


def _scheduled_report_delivery_override(
    job: JobProfile, run: Mapping[str, Any], delivery_gate: Mapping[str, Any]
) -> dict[str, Any]:
    """Allow delivery of a valid fixed report with one explicit limitation.

    The acceptance series remains fail-closed.  This override affects delivery
    only; it never turns an incomplete Autonomy execution into a valid decision.
    """
    failed = {str(value) for value in delivery_gate.get("failed_stages") or []}
    test_series = run.get("report_test_series") if isinstance(run.get("report_test_series"), Mapping) else {}
    pdf = run.get("pdf_delivery") if isinstance(run.get("pdf_delivery"), Mapping) else {}
    persistence = run.get("persistence") if isinstance(run.get("persistence"), Mapping) else {}
    eligible = bool(
        str(run.get("trigger") or "").upper() == "SCHEDULED"
        and not test_series.get("series_id")
        and failed == {"THEORETICAL_DECISIONS"}
        and persistence.get("ok")
        and pdf.get("generated") and pdf.get("validated") and pdf.get("published")
    )
    return {
        "allowed": eligible,
        "code": "LIMITED_THEORETICAL_DECISIONS" if eligible else "",
        "failed_stages": sorted(failed),
        "message": (
            "Rapporten er levert med begrensning: teoretiske beslutninger ble ikke fullført. "
            "Rapporten er ikke beslutningsklar og skal ikke brukes som kjøpssignal."
            if eligible else ""
        ),
    }


def _format_summary_value_for_notice(value: Any, decimals: int = 1) -> str:
    try:
        number = float(value)
        text = f"{number:.{decimals}f}".rstrip("0").rstrip(".")
        return text.replace(".", ",")
    except (TypeError, ValueError):
        return str(value if value is not None else "-")


def _notification(job: JobProfile, run: Mapping[str, Any]) -> tuple[bool, str]:
    run_id = str(run.get("run_id") or "").strip()
    receipts = _read(REPORT_NOTIFICATION_RECEIPTS_PATH, {})
    receipts = dict(receipts) if isinstance(receipts, Mapping) else {}

    def record(sent: bool, detail: str, *, attempted: bool, skipped_reason: str = "") -> None:
        if not run_id:
            return
        identity = resolve_report_identity(run)
        now_iso = _now_iso()
        receipts[run_id] = {
            "notification_id": f"REPORT-{run_id}-PUSHOVER",
            "sent": bool(sent), "attempted": bool(attempted), "at": now_iso,
            "created_at": str(run.get("created_at") or now_iso),
            "scheduled_at": str(run.get("scheduled_for") or ""),
            "attempted_at": now_iso if attempted else "",
            "sent_at": now_iso if sent else "",
            "expires_at": str(run.get("notification_expires_at") or (datetime.now(timezone.utc) + timedelta(minutes=max(5, int(os.getenv("PUSHOVER_REPORT_MAX_AGE_MINUTES", "90") or 90)))).isoformat(timespec="seconds")),
            "status": "SENT" if sent else ("FAILED" if attempted else "SKIPPED"),
            "triggered_by": str(run.get("trigger") or "MANUAL").upper(),
            "channel": "PUSHOVER", "report_id": str(run.get("report_id") or run_id), "run_id": run_id,
            "job_id": job.job_id, "job_name": job.name,
            "report_type": identity.get("type"), "report_label": identity.get("label"),
            "detail": str(detail or ""), "skipped_reason": skipped_reason,
            "test_run": bool(run.get("test_run")), "scheduled_for": run.get("scheduled_for") or "",
            "report_url": report_public_url(run),
        }
        _write(REPORT_NOTIFICATION_RECEIPTS_PATH, dict(list(receipts.items())[-1000:]))

    previous_receipt = dict(receipts.get(run_id) or {}) if run_id else {}
    if previous_receipt.get("sent") is True:
        return True, "Allerede levert: eksisterende Pushover-kvittering bekrefter sending"
    created_raw = str(run.get("created_at") or "")
    if created_raw:
        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)).total_seconds() / 60.0
            max_age = max(5, int(os.getenv("PUSHOVER_REPORT_MAX_AGE_MINUTES", "90") or 90))
            if age_minutes > max_age:
                detail = f"Varsel utløpt: rapporten er {age_minutes:.0f} minutter gammel"
                record(False, detail, attempted=False, skipped_reason="EXPIRED_REPORT")
                return False, detail
        except Exception:
            pass
    if run.get("suppress_notifications"):
        detail = "Test uten varsling: Pushover ble ikke sendt"
        record(False, detail, attempted=False, skipped_reason="SUPPRESSED_TEST")
        _audit("REPORT_NOTIFICATION_SUPPRESSED", {"run_id": run_id, "job_id": job.job_id, "detail": detail})
        return False, detail

    changes = run.get("changes") or {}
    interesting = [x for x in changes.get("new", []) if float(x.get("investment_score", 0)) >= job.min_alert_score]
    interesting += [x for x in changes.get("improved", []) if float(x.get("investment_score", 0)) >= job.min_alert_score]
    integrity_change = bool((run.get("change_since_previous") or {}).get("material_change"))
    revision = run.get("report_revision") if isinstance(run.get("report_revision"), Mapping) else {}
    is_revised = bool(revision.get("supersedes_run_id"))
    mode = _notification_mode(job)
    if mode == "ERRORS_ONLY" and not list(run.get("errors") or []):
        detail = "Ingen feil; varsling er satt til kun feil"
        record(False, detail, attempted=False, skipped_reason="POLICY_ERRORS_ONLY")
        return False, detail
    if mode == "CHANGES_ONLY" and not interesting and not integrity_change and not is_revised:
        detail = "Ingen kvalifiserende endringer"
        record(False, detail, attempted=False, skipped_reason="POLICY_CHANGES_ONLY")
        return False, detail
    if not job.notify_pushover:
        detail = "Pushover er deaktivert for jobben"
        record(False, detail, attempted=False, skipped_reason="JOB_DISABLED")
        return False, detail
    try:
        from notifier import send_pushover_alert
        identity = resolve_report_identity(run)
        from report_channel_consistency import projection_from_run
        channel_projection = projection_from_run(run)
        is_test = bool(run.get("test_run")) or "TEST" in str(run.get("trigger") or "").upper()
        test_series = dict(run.get("report_test_series") or {}) if isinstance(run.get("report_test_series"), Mapping) else {}
        automatic_test = bool(
            str(job.job_id or "").upper() == "MI-AUTONOMY-REPORT-TEST"
            and test_series.get("automatic") and test_series.get("series_id")
        )
        test_part = int(test_series.get("part") or 0)
        test_total = int(test_series.get("total") or 0)
        origin = "Planlagt" if str(run.get("trigger") or "").upper() == "SCHEDULED" else ("Test" if is_test else "Manuell")
        top = (run.get("proposals") or run.get("candidates") or [{}])[0]
        lines: list[str] = []
        delivery_limitation = run.get("delivery_limitation") if isinstance(run.get("delivery_limitation"), Mapping) else {}
        if delivery_limitation.get("message"):
            lines.extend([
                "⚠️ BEGRENSET RAPPORT – IKKE BESLUTNINGSKLAR",
                str(delivery_limitation.get("message")),
            ])
        if is_test:
            if automatic_test:
                lines.extend([
                    f"🧪 AUTOMATISK RAPPORTTEST {test_part}/{test_total}",
                    f"Testserie-ID: {test_series.get('series_id')}",
                    f"Deltest: {test_part}/{test_total}",
                    f"Kjøringsforsøk: {int(test_series.get('attempt') or 0)} (inkluderer eventuelle retry)",
                ])
            else:
                lines.append("🧪 TESTVARSEL · MANUELL TEST - teller ikke i automatisk 1/4–4/4")
        if run.get("scheduled_for"):
            lines.append(
                "Planlagt tidspunkt: "
                + local_display(run.get("scheduled_for"), str(run.get("timezone_name") or DEFAULT_TIMEZONE))
            )
        report_summary_notice = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
        # One denominator for JSON, PDF, UI and Pushover.  Do not fall back to
        # an earlier scan/deep-analysis counter after portfolio-only positions
        # have been appended to the canonical report population.
        candidate_total_notice = int(
            report_summary_notice.get("coverage_candidate_total")
            or (run.get("production_coverage_contract") or {}).get("candidate_total")
            or report_summary_notice.get("deep_analyzed")
            or run.get("summary", {}).get("deep_analyzed", 0)
            or 0
        )
        channel_quality_notice = (
            channel_projection.get("quality")
            if isinstance(channel_projection.get("quality"), Mapping) else {}
        )
        candidate_total_notice = int(
            channel_quality_notice.get("candidate_total") or candidate_total_notice
        )
        evidence_ready_notice = int(
            channel_quality_notice.get("evidence_ready")
            or report_summary_notice.get("evidence_data_ready") or 0
        )
        market_quality_notice = int(channel_quality_notice.get("market_data_score") or 0)
        report_created_local = str(
            (run.get("report_document") or {}).get("metadata", {}).get("created_at_local")
            if isinstance(run.get("report_document"), Mapping) else ""
        ) or local_display(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE))
        lines.extend([
            f"Rapport: {identity.get('label') or 'Rapport'} · {origin}",
            f"Rapport-ID: {channel_projection.get('report_id') or run_id}",
            f"Programversjon: {APP_VERSION}",
            f"Kjøretid: {__import__('runtime_identity').runtime_label('report_scheduler')}",
            f"Rapporttid: {report_created_local}",
            f"Status: {(run.get('report_status') or {}).get('label', 'Eldre rapport')} · {revision.get('revision_label', 'R1')}",
            f"Jobb: {deduplicated_display_name(job.name)}", f"Markeder: {', '.join(run.get('markets', []))}",
            f"Analysert: {candidate_total_notice}",
            f"Konkrete kjøpsanbefalinger: {int(report_summary_notice.get('analytical_buy_recommendations') or 0)} "
            f"(strenge {int(report_summary_notice.get('buy_candidates') or 0)} · moderate {int(report_summary_notice.get('moderate_buy_recommendations') or 0)})",
            f"Nye: {len(changes.get('new', []))} | Forbedret: {len(changes.get('improved', []))}",
            f"Datastatus: markedsdata (beslutningsjustert) {market_quality_notice}/100 · "
            f"evidens {evidence_ready_notice}/{candidate_total_notice}",
        ])
        learning_acceptance = run.get("learning_acceptance") if isinstance(run.get("learning_acceptance"), Mapping) else {}
        plausibility = run.get("decision_plausibility") if isinstance(run.get("decision_plausibility"), Mapping) else {}
        if plausibility:
            lines.append(
                "Plausibilitet: " + str(plausibility.get("status") or "UKJENT")
                + f" · null-kjøpsrekke {int(plausibility.get('zero_buy_streak') or 0)}"
                + f" · læringsutfall {int(plausibility.get('learning_evidence_count') or 0)}"
            )
            for warning in list(plausibility.get("warnings") or [])[:2]:
                lines.append("⚠️ " + str(warning))
        if is_test and learning_acceptance:
            lines.append(
                "Læringstest: " + str(learning_acceptance.get("verdict") or "IKKE KJØRT")
                + f" · beslutninger {int(learning_acceptance.get('learning_decision_count') or 0)}"
                + f" · handler {int(learning_acceptance.get('learning_trade_count') or 0)}"
            )
        if job.include_top3_in_notification:
            medals = list(channel_projection.get("ranking") or [])[:3]
            for idx, item in enumerate(medals):
                score = item.get("score")
                score_text = "-" if score is None else _format_summary_value_for_notice(score, 2)
                lines.append(f"{('🥇','🥈','🥉')[idx]} {item.get('ticker','-')} {score_text} · {item.get('decision_label') or item.get('decision') or '-'}")
        else:
            lines.append(f"Topp: {top.get('ticker', '-')} ({_format_summary_value_for_notice(top.get('investment_score', '-'), 2)})")
        url = report_public_url(run) if job.include_report_link else ""
        if automatic_test:
            title_prefix = f"🧪 AUTOMATISK {test_part}/{test_total} · "
        elif is_test:
            title_prefix = "🧪 TESTVARSEL · MANUELL TEST · "
        else:
            title_prefix = ""
        ok, err = send_pushover_alert(
            "\n".join(lines), title=f"{title_prefix}{identity.get('label') or 'Rapport'} · AI Aksje Analyzer",
            url=url or None, url_title="Åpne rapport" if url else None,
        )
        record(bool(ok), str(err or "Sendt"), attempted=True)
        _audit("REPORT_NOTIFICATION_SENT" if ok else "REPORT_NOTIFICATION_FAILED", {
            "run_id": run_id, "job_id": job.job_id, "report_label": identity.get("label"),
            "detail": str(err or "Sendt"), "test_run": is_test,
        })
        if ok and job.include_report_link and not url:
            return True, "Sendt uten rapportlenke: offentlig rapportadresse mangler"
        return bool(ok), str(err or "Sendt")
    except Exception as exc:
        detail = str(exc)
        try:
            record(False, detail, attempted=True)
        except Exception:
            pass
        return False, detail


MARKET_CURRENCIES = {
    "USA": "USD", "Norge": "NOK", "Sverige": "SEK",
    "Finland": "EUR", "Danmark": "DKK", "Brasil": "BRL",
}


def market_currency(market: Any = "", ticker: Any = "", explicit: Any = "") -> str:
    """Resolve the transaction currency without converting the source value."""
    if str(explicit or "").strip():
        return str(explicit).strip().upper()
    normalized_market = infer_market_from_ticker(str(ticker or ""), str(market or ""))
    return MARKET_CURRENCIES.get(normalized_market, "")


def format_whole_currency(value: Any, currency: str = "") -> str:
    """Round to whole units and use Norwegian-style grouped thousands."""
    try:
        number = int(round(float(value or 0)))
        grouped = f"{abs(number):,}".replace(",", " ")
        text = f"-{grouped}" if number < 0 else grouped
    except (TypeError, ValueError):
        text = str(value if value is not None else "-")
    return f"{text} {currency}".strip()


def risk_level(value: Any) -> str:
    try:
        score = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return "UKJENT"
    return "LAV" if score < 30.0 else "MODERAT" if score < 65.0 else "HØY"


def format_risk(value: Any) -> str:
    try:
        score = f"{float(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    except (TypeError, ValueError):
        return str(value if value is not None else "-")
    return f"{score} - {risk_level(value)}"


def insider_coverage_by_market(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate actual insider attempts without treating NOT_SEARCHED as checked."""
    grouped: dict[str, dict[str, Any]] = {}
    error_statuses = {
        "ERROR", "SOURCE_ERROR", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED",
        "DAILY_QUOTA_EXCEEDED", "UNAVAILABLE", "STALE",
    }
    for candidate in candidates or []:
        market = str(candidate.get("market") or "Ukjent")
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        insider = raw.get("insider_intelligence") if isinstance(raw.get("insider_intelligence"), Mapping) else {}
        readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
        search_log = [row for row in (insider.get("search_log") or []) if isinstance(row, Mapping)]
        attempted = any(bool(row.get("attempted")) for row in search_log)
        # Actual source activity is authoritative. A stale readiness wrapper
        # must never turn an executed search into NOT_SEARCHED in the PDF.
        status = str(
            (insider.get("coverage") or insider.get("status")) if attempted
            else (readiness.get("insider") or insider.get("coverage") or insider.get("status") or "NOT_SEARCHED")
        ).upper()
        row = grouped.setdefault(market, {
            "market": market, "checked": 0, "verified": 0, "discovery": 0,
            "no_events": 0, "missing": 0, "not_searched": 0, "not_configured": 0,
            "source_errors": 0, "source": "",
        })
        if attempted or status in {"AVAILABLE", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "MISSING", "DISCOVERY_ONLY"} | error_statuses:
            row["checked"] += 1
        if status in {"AVAILABLE", "VERIFIED_FACTS_FOUND"}:
            row["verified"] += 1
        elif status == "DISCOVERY_ONLY":
            row["discovery"] += 1
        elif status == "CHECKED_NO_EVENTS" and attempted:
            row["no_events"] += 1
        elif status == "MISSING":
            row["missing"] += 1
            if attempted:
                row["no_events"] += 1
        elif status in {"NOT_CONFIGURED"}:
            row["not_configured"] += 1
        elif status in error_statuses:
            row["source_errors"] += 1
        else:
            row["not_searched"] += 1
        # A configured primary source is descriptive only; it is not evidence
        # that the primary source was directly checked.
        if insider.get("official_source"):
            row["source"] = str(insider.get("official_source"))
    return [grouped[key] for key in sorted(grouped)]


def short_coverage_by_market(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate short checks without presenting missing values as zero exposure."""
    from short_intelligence import normalize_short_snapshot
    grouped: dict[str, dict[str, Any]] = {}
    for candidate in candidates or []:
        market = str(candidate.get("market") or "Ukjent")
        snapshot = normalize_short_snapshot(candidate)
        coverage = str(snapshot.get("coverage") or snapshot.get("status") or "NOT_SEARCHED").upper()
        row = grouped.setdefault(market, {
            "market": market, "checked": 0, "verified": 0, "no_public_position": 0,
            "not_searched": 0, "not_supported": 0, "source_errors": 0,
        })
        if snapshot.get("verified"):
            row["checked"] += 1; row["verified"] += 1
        elif coverage == "CHECKED_NO_PUBLIC_POSITION":
            row["checked"] += 1; row["no_public_position"] += 1
        elif coverage in {"SOURCE_ERROR", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED", "UNAVAILABLE", "STALE"}:
            row["checked"] += 1; row["source_errors"] += 1
        elif coverage == "NOT_SUPPORTED":
            row["not_supported"] += 1
        else:
            row["not_searched"] += 1
    return [grouped[key] for key in sorted(grouped)]


def apply_evidence_coverage_policy(candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Make missing intelligence explicit and conservatively calibrate confidence."""
    penalties = {
        "AVAILABLE": 0.0, "CHECKED_NO_EVENTS": 0.0, "MISSING": 8.0,
        "DISCOVERY_ONLY": 7.0, "STALE": 8.0, "NOT_CONFIGURED": 10.0,
        "UNAVAILABLE": 10.0, "ERROR": 12.0, "NOT_SEARCHED": 15.0,
        "VERIFIED_FACTS_FOUND": 0.0, "SECONDARY_FACTS_FOUND": 9.0, "PARTIAL_SOURCE_FAILURE": 8.0,
        "RATE_LIMITED": 10.0, "DAILY_QUOTA_EXCEEDED": 10.0, "SOURCE_ERROR": 12.0,
    }
    summary = {
        "evaluated": 0, "reduced": 0, "decision_downgraded": 0,
        "manual_review_required": 0, "statuses": {}, "verified_facts": 0,
        "sources_attempted": 0, "search_statuses": {},
        "search_unknown_reason_count": 0,
    }
    for candidate in candidates:
        from evidence_contract import canonical_status, evidence_conflicts, normalize_search_payload, source_budget
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        records: dict[str, Any] = {}
        total_penalty = 0.0
        critical_failures = 0
        for label, key in (("insider", "insider_intelligence"), ("news", "news_intelligence")):
            payload = raw.get(key) if isinstance(raw.get(key), Mapping) else {}
            payload = normalize_search_payload(payload, area=label)
            if isinstance(raw, dict):
                raw[key] = payload
            evidence_rows = payload.get("evidence") if label == "insider" else payload.get("events")
            evidence_rows = list(evidence_rows or [])
            search_log = [dict(row) for row in (payload.get("search_log") or []) if isinstance(row, Mapping)]
            status = canonical_status(payload, evidence_rows)
            penalty = penalties.get(status, 12.0)
            # A completed search with no relevant events is a valid factual result.
            # It must not be treated as a source failure or reduce confidence.
            total_penalty += penalty
            if status in {"STALE", "NOT_CONFIGURED", "UNAVAILABLE", "ERROR", "NOT_SEARCHED",
                          "DISCOVERY_ONLY", "SECONDARY_FACTS_FOUND", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED",
                          "DAILY_QUOTA_EXCEEDED", "SOURCE_ERROR"}:
                critical_failures += 1
            conflicts = evidence_conflicts(evidence_rows)
            records[label] = {
                "status": status, "penalty": penalty,
                "source": payload.get("official_source") or payload.get("source") or "Ikke oppgitt",
                "fetched_at": payload.get("fetched_at"),
                "reason": payload.get("reason") or payload.get("summary") or "",
                "verified_facts": int(payload.get("verified_fact_count") or (len(evidence_rows) if label == "news" else 0)),
                "structured_facts": len(evidence_rows),
                "sources_attempted": sum(1 for row in search_log if row.get("attempted")),
                "search_log": search_log,
                "source_budget": source_budget(payload),
                "search_status": payload.get("search_status") or "NOT_SEARCHED_POLICY",
                "search_reason_counts": dict(payload.get("search_reason_counts") or {}),
                "search_unknown_reason_count": int(payload.get("search_unknown_reason_count") or 0),
                "conflicts": conflicts,
            }
            summary["verified_facts"] += int(records[label]["verified_facts"])
            summary["sources_attempted"] += records[label]["sources_attempted"]
            summary["statuses"][status] = int(summary["statuses"].get(status, 0)) + 1
            search_status = str(records[label].get("search_status") or "NOT_SEARCHED_POLICY")
            summary["search_statuses"][search_status] = int(summary["search_statuses"].get(search_status, 0)) + 1
            summary["search_unknown_reason_count"] += int(records[label].get("search_unknown_reason_count") or 0)
        before = float(candidate.get("confidence_score") or 0)
        insider_status = records["insider"]["status"]
        news_status = records["news"]["status"]
        valid_completed_states = {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS", "AVAILABLE"}
        cap = 100.0
        if news_status not in valid_completed_states and insider_status in {
            "STALE", "NOT_CONFIGURED", "UNAVAILABLE", "ERROR", "NOT_SEARCHED",
            "DISCOVERY_ONLY", "SECONDARY_FACTS_FOUND", "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED",
            "DAILY_QUOTA_EXCEEDED", "SOURCE_ERROR",
        }:
            cap = 60.0
        elif news_status not in valid_completed_states and insider_status not in valid_completed_states:
            cap = 68.0
        elif critical_failures:
            cap = 75.0
        after = min(cap, max(0.0, round(before - total_penalty, 2)))
        candidate["evidence_coverage"] = records
        from evidence_relevance import evidence_decision_assessment
        relevance = evidence_decision_assessment(candidate)
        review_required = bool(
            relevance["missing_required_areas"]
            or bool(records["insider"]["conflicts"] or records["news"]["conflicts"])
        )
        candidate["confidence_before_evidence_policy"] = before
        candidate["confidence_score"] = after
        candidate["evidence_decision_assessment"] = relevance
        candidate["evidence_confidence_penalty"] = total_penalty
        candidate["evidence_confidence_cap"] = cap
        candidate["evidence_review_required"] = review_required
        candidate["evidence_valid_for_decision"] = not review_required
        candidate["evidence_gate_status"] = "MANUAL_REVIEW" if review_required else "PASS"
        candidate["decision_readiness"] = {
            "status": "IKKE KOMPLETT" if review_required else "KOMPLETT – STRATEGIRELEVANT",
            "market_data": "AVVENTER DATAKONTRAKT",
            "news": news_status,
            "insider": insider_status,
            "conflicts": len(records["insider"]["conflicts"]) + len(records["news"]["conflicts"]),
            "required_evidence_areas": relevance["required_areas"],
            "neutralised_optional_areas": relevance["neutralised_optional_areas"],
            "confidence_before": before, "confidence_final": after,
            "allowed_action": "MANUELL VURDERING" if review_required else str(candidate.get("portfolio_action") or "REVIEW"),
        }
        summary["evaluated"] += 1
        if total_penalty:
            summary["reduced"] += 1
        if review_required:
            summary["manual_review_required"] += 1
        if review_required and str(candidate.get("status") or "") not in {"AVVIST AV RISIKOPORT", "UTILSTREKKELIGE DATA"}:
            candidate["status_before_evidence_policy"] = candidate.get("status")
            candidate["status"] = "KREVER MANUELL VURDERING – DOKUMENTASJON"
            summary["decision_downgraded"] += 1
    return summary


def combined_quality_summary(candidates: Sequence[Mapping[str, Any]],
                             data_contract: Mapping[str, Any],
                             evidence_summary: Mapping[str, Any]) -> dict[str, Any]:
    total = len(candidates)
    market_valid = int(data_contract.get("valid_for_decision") or 0)
    evidence_valid = sum(1 for row in candidates if row.get("evidence_valid_for_decision"))
    verified = int(evidence_summary.get("verified_facts") or 0)
    manual = int(evidence_summary.get("manual_review_required") or 0)
    overall_valid = sum(
        1 for row in candidates
        if row.get("valid_for_decision") and row.get("evidence_valid_for_decision")
    )
    if total == 0:
        status = "INGEN DATA"
    elif overall_valid == total:
        status = "FULLT BESLUTNINGSGRUNNLAG"
    elif overall_valid > 0:
        status = "DELVIS – AUTOMATISK REVALIDERING PÅKREVD"
    else:
        status = "UTILSTREKKELIG FOR AUTONOM BESLUTNING"
    return {
        "evaluated": total, "market_data_valid": market_valid,
        "evidence_valid": evidence_valid, "overall_valid": overall_valid,
        "manual_review_required": manual, "verified_evidence_facts": verified,
        "sources_attempted": int(evidence_summary.get("sources_attempted") or 0),
        "status": status,
        "green": bool(total and overall_valid == total),
        "news_verified": sum(
            1 for row in candidates
            if ((row.get("evidence_coverage") or {}).get("news") or {}).get("status") == "VERIFIED_FACTS_FOUND"
        ),
        "insider_verified": sum(
            1 for row in candidates
            if ((row.get("evidence_coverage") or {}).get("insider") or {}).get("status") == "VERIFIED_FACTS_FOUND"
        ),
        "news_rate_limited": sum(
            1 for row in candidates
            if ((row.get("evidence_coverage") or {}).get("news") or {}).get("status") == "RATE_LIMITED"
        ),
    }


def build_pdf(run: Mapping[str, Any], report_type: str | None = None, *, include_technical: bool = True) -> bytes:
    """Build the compact professional market-intelligence report.

    The v18.7.5 layout deliberately avoids decorative cover/disclaimer pages and
    per-proposal page breaks.  No report data is removed; dense sections are
    arranged horizontally and allowed to flow naturally across A4 pages.
    """
    from html import escape

    run = canonical_report_view(run)
    integrity = run.get("report_integrity") if isinstance(run.get("report_integrity"), Mapping) else {}
    if not integrity.get("ok", False):
        raise ValueError("Rapportintegritet feilet før PDF: " + "; ".join(integrity.get("errors") or []))

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    report_document = ensure_report_document(run)
    report_metadata = report_document.get("metadata") if isinstance(report_document.get("metadata"), Mapping) else {}
    identity = resolve_report_identity(run)
    report_type = report_type or f"Investor Edition · {report_metadata.get('report_label') or identity.get('label', 'Rapport')} – Markedsanalyse"
    # RC16.10 ships the exact font files used by the PDF renderer.  Do not
    # silently fall back to a host-dependent font: an exported report must be
    # visually reproducible on every deployment.
    font_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    regular_path = font_dir / "NotoSans-Regular.ttf"
    bold_path = font_dir / "NotoSans-Bold.ttf"
    if not regular_path.is_file() or not bold_path.is_file():
        raise RuntimeError("Medfølgende Noto Sans-fonter mangler; PDF kan ikke bygges reproducerbart")
    pdfmetrics.registerFont(TTFont("ReportSans", str(regular_path)))
    pdfmetrics.registerFont(TTFont("ReportSans-Bold", str(bold_path)))
    regular_font, bold_font = "ReportSans", "ReportSans-Bold"

    class ReportDocTemplate(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if not isinstance(flowable, Paragraph):
                return
            style_name = getattr(getattr(flowable, "style", None), "name", "")
            if style_name not in {"ReportTitle", "Section", "Subsection"}:
                return
            level = {"ReportTitle": 0, "Section": 0, "Subsection": 1}[style_name]
            title = flowable.getPlainText().strip()
            if not title:
                return
            keys = getattr(self, "_outline_keys", [])
            key = f"outline-{self.page}-{len(keys)}"
            self._outline_keys = keys + [key]
            self.canv.bookmarkPage(key)
            try:
                self.canv.addOutlineEntry(title, key, level=level, closed=False)
            except Exception:
                pass

    buf = io.BytesIO()
    doc = ReportDocTemplate(buf, pagesize=A4, rightMargin=13*mm, leftMargin=13*mm, topMargin=15*mm, bottomMargin=14*mm,
                            title=report_type, author="AI Aksje Analyzer Pro")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_LEFT, fontName=bold_font, fontSize=17, leading=20, textColor=colors.HexColor("#102A43"), spaceAfter=2*mm))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading1"], fontName=bold_font, fontSize=12, leading=14, textColor=colors.HexColor("#102A43"), spaceBefore=3*mm, spaceAfter=1.5*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="Subsection", parent=styles["Heading2"], fontName=bold_font, fontSize=9.5, leading=11, textColor=colors.HexColor("#243B53"), spaceBefore=2.2*mm, spaceAfter=1*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="BodyCompact", parent=styles["BodyText"], fontName=regular_font, fontSize=8, leading=10, spaceAfter=.8*mm))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName=regular_font, fontSize=7.2, leading=8.7, spaceAfter=.6*mm))
    styles.add(ParagraphStyle(name="MetricCard", parent=styles["BodyText"], fontName=regular_font, fontSize=7.1, leading=13.2, spaceAfter=0))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontName=regular_font, fontSize=6.4, leading=7.5))
    styles.add(ParagraphStyle(name="Footer", parent=styles["BodyText"], fontName=regular_font, fontSize=6.5, leading=8, textColor=colors.HexColor("#627D98")))

    header_bg = colors.HexColor("#D9EAF7")
    grid = colors.HexColor("#9FB3C8")
    stripe = colors.HexColor("#F5F8FA")
    SUMMARY_VALUE_FONT_SIZE = 8

    def _format_summary_value(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number.is_integer():
            return str(int(number))
        precision = 2 if abs(number * 10 - round(number * 10)) > 1e-8 else 1
        return f"{number:.{precision}f}".replace(".", ",")

    def _table_style(font_size: float = 7, *, header: bool = True, padding: float = 2.5) -> TableStyle:
        commands = [
            ("GRID", (0, 0), (-1, -1), .3, grid),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, -1), regular_font),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 1.3),
            ("LEFTPADDING", (0, 0), (-1, -1), padding),
            ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, stripe]),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), header_bg), ("FONTNAME", (0, 0), (-1, 0), bold_font)]
        return TableStyle(commands)

    def _p(value: Any, style: str = "Tiny") -> Paragraph:
        localized = _norwegian_decimal_text(_loc(value if value is not None else "-"))
        return Paragraph(escape(localized), styles[style])

    def _rawp(value: Any, style: str = "Tiny") -> Paragraph:
        """Render external titles, names, IDs and URLs without word translation."""
        return Paragraph(escape(str(value if value is not None else "-")), styles[style])

    def _fmt(value: Any, decimals: int = 2) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        try:
            return f"{float(value):.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")
        except (TypeError, ValueError):
            return value

    def _fmt_signed(value: Any, decimals: int = 2) -> str:
        try:
            number = float(value or 0)
            return (f"{number:+.{decimals}f}").replace(".", ",")
        except (TypeError, ValueError):
            return str(value if value is not None else "-")

    def _norwegian_decimal_text(value: Any) -> str:
        """Localise standalone decimal numbers without changing versions, IDs or URLs."""
        text = str(value if value is not None else "-")
        return re.sub(r"(?<![A-Za-z0-9._/\-])(\d+)\.(\d+)(?!\.\d)(?![A-Za-z0-9_/\-])", r"\1,\2", text)

    def _deduplicated_job_name(value: Any) -> str:
        return deduplicated_display_name(value)

    def _short(value: Any, limit: int = 165) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        clipped = text[: max(1, limit - 1)].rsplit(" ", 1)[0]
        return (clipped or text[: max(1, limit - 1)]) + "…"

    def _breakable(value: Any, limit: int = 180) -> str:
        text = _short(value, limit)
        for token in ("/", "?", "&", "=", "_", "-"):
            text = text.replace(token, token + " ")
        return " ".join(text.split())

    def _status_label(value: Any) -> str:
        return translate_report_text(label_for(value)).upper()

    def _loc(value: Any) -> str:
        return translate_report_text(value)

    def _clean_sentence(value: Any) -> str:
        text = " ".join(str(value or "").split())
        while ".." in text:
            text = text.replace("..", ".")
        text = text.replace(".;", ";").replace(";.", ";")
        text = text.replace(" .", ".").replace(" ;", ";")
        return text.strip(" ;")

    def _decision_label(value: Any) -> str:
        return decision_label(value)

    def _short_datetime(value: Any) -> str:
        text = str(value or "-")
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return _short(text, 24)

    def _short_date(value: Any) -> str:
        text = str(value or "-")
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return _short(text, 10)

    def _report_mission_labels() -> tuple[str, str]:
        report_kind = str(report_metadata.get("report_type") or identity.get("type") or "").upper()
        analysis_labels = {
            "MORGENRAPPORT": "Morgenanalyse",
            "DAGSRAPPORT": "Dagsanalyse",
            "KVELDSRAPPORT": "Kveldsanalyse",
            "NATTRAPPORT": "Nattanalyse",
            "UTKAST": "Utkastanalyse",
        }
        search_labels = {
            "MORGENRAPPORT": "Kandidater ved børsåpning",
            "DAGSRAPPORT": "Vesentlige endringer siden børsåpning",
            "KVELDSRAPPORT": "Kandidater til neste handelsdag",
            "NATTRAPPORT": "Globale signaler før neste handelsdag",
            "UTKAST": "Kandidater innenfor utkastets periodeoppdrag",
        }
        heading = analysis_labels.get(report_kind, "Markedsanalyse")
        search = search_labels.get(report_kind, "Investeringsmuligheter innenfor oppdraget")
        mission = str(report_metadata.get("mission_label") or "")
        objective = str(report_metadata.get("mission_objective") or "")
        return heading, f"{search}. {mission}. {objective}".strip()

    def _candidate_review_reasons(candidate: Mapping[str, Any]) -> list[str]:
        outcome_reason = str(candidate.get("autonomy_outcome_reason") or "").strip()
        tasks = [row for row in candidate.get("manual_tasks") or [] if isinstance(row, Mapping)]
        reasons = [outcome_reason] if outcome_reason else []
        reasons.extend(str(row.get("title") or "") for row in tasks if row.get("title"))
        if candidate.get("automatic_next_action"):
            reasons.append(str(candidate.get("automatic_next_action")))
        cleaned = [_clean_sentence(reason) for reason in reasons if _clean_sentence(reason)]
        return cleaned[:4] or ["Ingen manuell handling nødvendig; programmet følger kandidaten automatisk."]

    def _quality_score() -> int:
        quality = run.get("data_quality") if isinstance(run.get("data_quality"), Mapping) else {}
        combined = run.get("combined_quality") if isinstance(run.get("combined_quality"), Mapping) else {}
        market = float(quality.get("score") or 0)
        total = max(1, int(combined.get("evaluated") or len(run.get("candidates") or []) or 1))
        evidence = 100.0 * float(combined.get("overall_valid") or 0) / total
        if not combined:
            evidence = market
        return max(0, min(100, round((market + evidence) / 2)))

    def _metric_value(name: Any, value: Any) -> str:
        if isinstance(value, bool) or value is None:
            return _short(value, 100)
        try:
            number = float(value)
            if number == number:
                decimals = 2 if str(name or "").strip().lower() == "rsi" else 3
                return f"{number:.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")
        except (TypeError, ValueError):
            pass
        return _short(_loc(value), 100)

    def _source_log_rows(insider: Mapping[str, Any], news: Mapping[str, Any]) -> list[list[Any]]:
        rows: list[list[Any]] = [["Område", "Kilde", "Forsøkt", "Søkestatus", "Treff", "Kontrollert", "Årsak / adresse"]]
        from evidence_search_status import normalize_search_attempt
        for area, payload in (("Insider", insider), ("Nyheter", news)):
            for raw_item in payload.get("search_log") or []:
                if not isinstance(raw_item, Mapping):
                    continue
                item = normalize_search_attempt(raw_item)
                status = str(item.get("search_status") or "NOT_SEARCHED_POLICY").upper()
                reason_code = str(item.get("reason_code") or "UNKNOWN_REASON").upper()
                # Keep the PDF compact: the normalized search status already carries the
                # main outcome. Show the address when available, otherwise the concrete
                # reason/error. The machine-readable reason code remains in JSON and UI.
                detail_base = item.get("error") or item.get("url") or item.get("reason") or reason_code or "-"
                detail = _short(detail_base, 120)
                compact_search_label = {
                    "SEARCHED_RESULTS_FOUND": "SØKT - TREFF",
                    "SEARCHED_NO_RESULTS": "SØKT - INGEN TREFF",
                    "SEARCH_FAILED": "SØK FEILET",
                    "NOT_SEARCHED_BUDGET": "IKKE SØKT - BUDSJETT",
                    "NOT_SEARCHED_DISABLED": "IKKE SØKT - AV",
                    "NOT_SEARCHED_UNSUPPORTED": "IKKE SØKT - IKKE STØTTET",
                    "NOT_SEARCHED_POLICY": "IKKE SØKT - POLICY",
                    "NOT_APPLICABLE": "IKKE AKTUELT",
                }.get(status, _status_label(status))
                rows.append([
                    _p(area), _rawp(label_for(item.get("source") or item.get("source_type") or "-")),
                    _p("Ja" if item.get("attempted") else "Nei"),
                    _p(compact_search_label), _p(item.get("results", 0)),
                    _p(_short_datetime(item.get("checked_at") or item.get("retrieved_at") or "-")),
                    _rawp(_breakable(detail, 180)),
                ])
        if len(rows) == 1:
            rows.append(["Begge", "Ingen registrert søkelogg", "Nei", _status_label("NOT_SEARCHED_POLICY"), 0, "-", "UNKNOWN_REASON"])
        return rows

    def _candidate_evidence(candidate: Mapping[str, Any], next_candidate: Mapping[str, Any] | None = None) -> dict[str, str]:
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
        insider = raw.get("insider_intelligence") if isinstance(raw.get("insider_intelligence"), Mapping) else {}
        news = raw.get("news_intelligence") if isinstance(raw.get("news_intelligence"), Mapping) else {}
        components = [
            ("AI-funn", candidate.get("discovery_score")), ("Fundamentalt", candidate.get("fundamental_score")),
            ("Analyse", candidate.get("research_score")), ("Historisk test", candidate.get("validation_score")),
            ("porteføljetilpasning", candidate.get("portfolio_fit_score")),
            ("insider", raw.get("insider_score")) if str(insider.get("coverage") or "") == "AVAILABLE" else ("", None),
            ("nyheter", raw.get("news_score")) if str(news.get("coverage") or "") == "AVAILABLE" else ("", None),
        ]
        ranked = sorted(
            [(label, float(value)) for label, value in components if label and isinstance(value, (int, float))],
            key=lambda item: item[1], reverse=True,
        )[:3]
        drivers = ", ".join(f"{label} {score:.0f}" for label, score in ranked) or "Ingen sterke komponentbevis"
        cautions: list[str] = []
        coverage = str(insider.get("coverage") or "MISSING")
        if coverage != "AVAILABLE":
            cautions.append(f"innsiderdata: {_status_label(coverage).lower()}")
        elif float(insider.get("net_value") or 0) < 0:
            cautions.append("negativ netto insiderverdi")
        if str(news.get("coverage") or "") != "AVAILABLE":
            cautions.append("nyhetsdekning mangler")
        action = str(candidate.get("portfolio_action") or "REVIEW").upper()
        outcome_code = str(candidate.get("autonomy_outcome_code") or action).upper()
        if outcome_code != "KJØPSKANDIDAT":
            cautions.append(f"utfall {label_for(outcome_code).lower()}")
        validity = str((candidate.get("data_contract") or {}).get("validity") or "").upper()
        if validity and validity not in {"VALID", "GYLDIG"}:
            cautions.append(f"datagyldighet {_status_label(validity)}")
        score_gap = ""
        if next_candidate:
            score_gap = f"{_fmt(float(candidate.get('investment_score') or 0) - float(next_candidate.get('investment_score') or 0), 2)} poeng foran neste"
        return {
            "drivers": drivers,
            "cautions": ", ".join(cautions[:3]) or "Ingen kritiske forbehold registrert",
            "action": str(candidate.get("autonomy_outcome_label") or _decision_label(action)),
            "gap": score_gap,
            "insider": (
                f"{raw.get('insider_signal') or 'NØYTRAL'}; {int(insider.get('buy_count') or 0)} kjøp, "
                f"{int(insider.get('sell_count') or 0)} salg, "
                f"netto {format_whole_currency(insider.get('net_value', 0), market_currency(candidate.get('market'), candidate.get('ticker'), insider.get('currency')))}"
                if coverage == "AVAILABLE" else f"Ingen verifisert insiderinformasjon ({_status_label(coverage)})"
            ),
            "news": _short(news.get("summary") or "Ingen relevant nyhetsinformasjon", 115),
        }

    def _page(canvas: Any, document: Any) -> None:
        page_key = f"page-{document.page}"
        canvas.bookmarkPage(page_key)
        try:
            canvas.addOutlineEntry(f"Side {document.page}", page_key, level=0, closed=False)
            canvas.showOutline()
        except Exception:
            pass
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#BCCCDC"))
        canvas.setLineWidth(.35)
        canvas.line(13*mm, height-10*mm, width-13*mm, height-10*mm)
        canvas.setFont(regular_font, 6.5)
        canvas.setFillColor(colors.HexColor("#627D98"))
        canvas.drawString(13*mm, height-8*mm, f"AI Aksje Analyzer Pro · {APP_VERSION}")
        canvas.drawRightString(width-13*mm, height-8*mm, "Investor Edition · " + str(identity.get("label") or "Rapport"))
        canvas.line(13*mm, 9*mm, width-13*mm, 9*mm)
        revision = run.get("report_revision") if isinstance(run.get("report_revision"), Mapping) else {}
        canvas.drawString(
            13*mm, 6*mm,
            f"{run.get('run_id') or '-'} · {revision.get('revision_label') or 'R1'}",
        )
        canvas.drawRightString(width-13*mm, 6*mm, f"Side {document.page}")
        canvas.restoreState()

    markets_text = ", ".join(run.get("markets") or run.get("market_expansion") or [])
    report_status = run.get("report_status") if isinstance(run.get("report_status"), Mapping) else {}
    critical_gap_rows = [row for row in (report_status.get("critical_gaps") or []) if isinstance(row, Mapping)]
    critical_gaps_by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for gap_row in critical_gap_rows:
        critical_gaps_by_ticker.setdefault(str(gap_row.get("ticker") or "").upper(), []).append(gap_row)
    report_revision = run.get("report_revision") if isinstance(run.get("report_revision"), Mapping) else {}
    meta = Table([
        [_p("Rapporttype", "Small"), _p(identity.get("type", "-"), "Small"), _p("Jobb", "Small"), _p(_deduplicated_job_name(run.get("job_name", "-")), "Small")],
        [_p("Rapport-ID", "Small"), _rawp(report_metadata.get("report_id") or run.get("report_id") or run.get("run_id") or "-", "Small"), _p("Generert", "Small"),
         _p(local_display(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE)), "Small")],
        [_p("Markeder", "Small"), _p(markets_text, "Small"), "", ""],
        [_p("Rapportstatus", "Small"), _p(report_status.get("label") or "Eldre rapportformat", "Small"),
         _p("Revisjon", "Small"), _p(report_revision.get("revision_label") or "R1", "Small")],
        [_p("Kontrollsum", "Small"), _rawp(_breakable(str(report_metadata.get("content_sha256") or report_revision.get("content_sha256") or "-"), 80), "Tiny"),
         _p("Erstatter", "Small"), _p(report_revision.get("supersedes_run_id") or "-", "Small")],
        [_p("Analyse-ID", "Small"), _rawp(report_metadata.get("analysis_id") or run.get("analysis_id") or "-", "Small"),
         _p("Rapportskjema", "Small"), _p(report_metadata.get("report_schema_version") or REPORT_SCHEMA_VERSION, "Small")],
        [_p("Appversjon", "Small"), _p(report_metadata.get("app_version") or APP_VERSION, "Small"),
         _p("Kontrakt", "Small"), _p(report_metadata.get("contract_version") or "1.0", "Small")],
        [_p("Oppdrag", "Small"), _p(report_metadata.get("mission_label") or identity.get("mission_label") or "-", "Small"),
         _p("Status", "Small"), _p(report_status.get("label") or report_status.get("state") or "-", "Small")],
    ], colWidths=[22*mm, 64*mm, 24*mm, 74*mm])
    meta.setStyle(_table_style(7, header=False, padding=2.5))
    meta.setStyle(TableStyle([("SPAN", (1, 2), (3, 2)), ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"), ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F5F8FA"))]))

    # v19.0.21: a compact decision report is rendered first from the same
    # ReportDocument. The previous comprehensive report remains intact as a
    # technical appendix, so no evidence or audit detail is removed.
    decision_overview = section_payload(report_document, "decision_overview", {}) or {}
    decision_candidates = section_payload(report_document, "candidate_decisions", []) or []
    rejected_control = section_payload(report_document, "rejected_control_appendix", []) or []
    decision_changes = section_payload(report_document, "changes", {}) or {}
    decision_diffs = section_payload(report_document, "decision_diffs", {}) or {}
    decision_counter_hypotheses = section_payload(report_document, "counter_hypotheses", {}) or {}
    decision_historical = section_payload(report_document, "historical_evaluations", []) or []
    decision_learning_guard = section_payload(report_document, "controlled_learning_guard", {}) or {}
    decision_tasks = section_payload(report_document, "next_run_tasks", []) or []
    decision_events = section_payload(report_document, "events", []) or []
    decision_confidence = section_payload(report_document, "confidence_profile", {}) or {}
    decision_quality = section_payload(report_document, "quality_dimensions", {}) or {}
    decision_reliability = section_payload(report_document, "report_reliability", {}) or {}
    decision_portfolio = section_payload(report_document, "portfolio_intelligence", {}) or {}
    decision_anomalies = section_payload(report_document, "system_anomaly_watch", []) or []
    decision_watch_queue = section_payload(report_document, "candidate_watch_queue", []) or []

    full_checksum = str(report_metadata.get("content_sha256") or report_revision.get("content_sha256") or "-")
    checksum_display = full_checksum if full_checksum == "-" else (full_checksum[:32] + " " + full_checksum[32:])
    decision_meta = Table([
        [_p("Rapport", "Small"), _p(report_metadata.get("report_label") or identity.get("label") or "Rapport", "Small"),
         _p("Generert", "Small"), _p(report_metadata.get("created_at_local") or local_display(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE)), "Small")],
        [_p("Rapport-ID", "Small"), _rawp(report_metadata.get("report_id") or run.get("run_id") or "-", "Small"),
         _p("Analyse-ID", "Small"), _rawp(report_metadata.get("analysis_id") or run.get("analysis_id") or "-", "Small")],
        [_p("Program", "Small"), _p(report_metadata.get("app_version") or APP_VERSION, "Small"),
         _p("Skjema / revisjon", "Small"), _p(f"{report_metadata.get('report_schema_version') or REPORT_SCHEMA_VERSION} / {report_revision.get('revision_label') or 'R1'}", "Small")],
        [_p("Markeder", "Small"), _p(markets_text or "-", "Small"),
         _p("Status", "Small"), _p(report_status.get("label") or report_status.get("state") or "Eldre rapportformat", "Small")],
        [_p("Erstatter", "Small"), _rawp(report_revision.get("supersedes_run_id") or "-", "Small"),
         _p("Revisjonsserie", "Small"), _rawp(report_revision.get("series_id") or "-", "Small")],
        [_p("SHA-256", "Small"), _rawp(checksum_display, "Tiny"), "", ""],
    ], colWidths=[19*mm, 68*mm, 25*mm, 72*mm])
    decision_meta.setStyle(_table_style(6.1, header=False, padding=1.5))
    decision_meta.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F5F8FA")),
        ("SPAN", (1,5), (3,5)),
    ]))

    decision_state = "PASS" if int(decision_overview.get("decision_ready_count") or 0) else "REVIEW"
    documentation_score = int(decision_quality.get("technical_documentation_coverage") or decision_confidence.get("documentation_coverage") or decision_confidence.get("data_coverage") or 0)
    source_score = int(decision_quality.get("independent_source_coverage") or decision_confidence.get("source_confidence") or 0)
    decision_strength = int(decision_quality.get("report_decision_strength") or decision_confidence.get("decision_confidence") or 0)
    market_quality = int(decision_quality.get("market_data_quality") or decision_confidence.get("market_data_coverage") or 0)
    evidence_coverage = float(decision_quality.get("candidate_evidence_coverage") or 0)
    evidence_ready = int(decision_quality.get("candidate_evidence_ready_count") or 0)
    evidence_total = int(decision_quality.get("candidate_count") or decision_overview.get("candidate_count") or len(decision_candidates))
    decision_status = Table([[
        Paragraph(f"<b>Beslutningsjustert markedsdata</b><br/><font size='10'>{market_quality}/100</font>", styles["MetricCard"]),
        Paragraph(f"<b>Teknisk dokumentasjon</b><br/><font size='10'>{documentation_score}/100</font>", styles["MetricCard"]),
        Paragraph(f"<b>Kandidatenes evidens</b><br/><font size='10'>{evidence_ready}/{evidence_total} · {evidence_coverage:.0f}%</font>", styles["MetricCard"]),
        Paragraph(f"<b>Uavhengige kilder</b><br/><font size='10'>{source_score}/100</font>", styles["MetricCard"]),
        Paragraph(f"<b>Beslutningsstyrke rapport</b><br/><font size='10'>{decision_strength}/100</font>", styles["MetricCard"]),
    ]], colWidths=[36.8*mm]*5)
    decision_status.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), .35, grid),
        ("BACKGROUND", (0,0), (0,0), colors.HexColor(decision_color(quality_status(market_quality)))),
        ("BACKGROUND", (1,0), (1,0), colors.HexColor(decision_color(quality_status(documentation_score)))),
        ("BACKGROUND", (2,0), (2,0), colors.HexColor(decision_color(quality_status(evidence_coverage)))),
        ("BACKGROUND", (3,0), (3,0), colors.HexColor(decision_color(quality_status(source_score)))),
        ("BACKGROUND", (4,0), (4,0), colors.HexColor(decision_color(decision_state))),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 2), ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))

    focus_text = " | ".join(str(item) for item in (decision_overview.get("focus") or []))
    report_summary_early = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    executive_rows = [["Analysert", "Kjøpsgodkjent", "Overvåk", "Manuell vurdering", "Høyeste score"]]
    executive_rows.append([
        report_summary_early.get("deep_analyzed", len(run.get("candidates") or [])),
        report_summary_early.get("decision_ready", decision_overview.get("decision_ready_count", 0)),
        report_summary_early.get("automatic_watch", 0),
        report_summary_early.get("manual_review", 0),
        _fmt((run.get("executive_intelligence") or {}).get("highest_score", 0)),
    ])
    executive_table = Table(executive_rows, repeatRows=1, colWidths=[36.8*mm]*5)
    executive_table.setStyle(_table_style(6.2, padding=2))
    title_table = Table([[
        Paragraph("AI Aksje Analyzer Pro", styles["ReportTitle"]),
        Paragraph(f"<b>{escape(str(report_metadata.get('app_version') or APP_VERSION))}</b>", styles["Small"]),
    ]], colWidths=[145*mm, 39*mm])
    title_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,0), (1,0), "RIGHT"),
        ("BACKGROUND", (1,0), (1,0), colors.HexColor("#EAF2F8")),
        ("BOX", (1,0), (1,0), .4, grid),
        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 1), ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    coverage = run.get("market_coverage") if isinstance(run.get("market_coverage"), Mapping) else build_market_coverage_v19220_rc9(run)
    actual_text = "; ".join(
        f"{market}: {count}" for market, count in (coverage.get("actual_by_market") or {}).items()
    ) or "Ingen registrerte skannetall"
    coverage_status = {
        "COMPLETE": "Fullført for alle valgte land",
        "PARTIAL": "Delvis fullført",
        "FAILED": "Ikke fullført",
    }.get(str(coverage.get("overall_status") or "").upper(), "Ukjent")
    coverage_table = Table([
        [_p("Planlagte land", "Tiny"), _p(coverage.get("planned_country_text") or markets_text or "-", "Tiny"),
         _p("Dekningsstatus", "Tiny"), _p(coverage_status, "Tiny")],
        [_p("Faktisk skannet", "Tiny"), _p(actual_text, "Tiny"),
         _p("Feilet / hoppet over", "Tiny"), _p(", ".join(coverage.get("failed_or_skipped_markets") or []) or "Ingen", "Tiny")],
    ], colWidths=[24*mm, 66*mm, 30*mm, 64*mm])
    coverage_table.setStyle(_table_style(5.7, header=False, padding=1.3))
    universe_rows = [row for row in (run.get("universe_coverage") or []) if isinstance(row, Mapping)]
    universe_table = None
    if universe_rows:
        universe_data = [["Marked", "Kontrollunivers", "Skannet", "Sektorer", "Kontrollandel*", "Kilde"]]
        for row in universe_rows:
            universe_data.append([
                str(row.get("market") or "-"), str(row.get("configured_universe") or 0),
                str(row.get("rough_scanned") or 0), str(row.get("known_sector_coverage") or "-"),
                f"{float(row.get('coverage_pct') or 0):.0f}%",
                "Autoritativ" if row.get("source_authoritative_exchange_master") else "Kontrolliste",
            ])
        universe_table = Table(universe_data, repeatRows=1, colWidths=[24*mm, 24*mm, 26*mm, 24*mm, 20*mm, 38*mm])
        universe_table.setStyle(_table_style(6.0, padding=1.4))

    decision_story = [
        title_table,
        Paragraph(
            f"{escape(str(report_metadata.get('report_label') or identity.get('label') or 'Rapport'))} – Markedsanalyse – beslutningsside",
            styles["Section"],
        ),
        Paragraph(f"Type: {escape(str(report_metadata.get('report_type') or identity.get('type') or '-'))} · Jobb: {escape(_deduplicated_job_name(run.get('job_name') or '-'))}", styles["Small"]),
        Paragraph(
            "Denne investordelen er et kort beslutningsdokument. Komplett kilde-, modell-, oppgave- og integritetsspor "
            "ligger i rapportens separate tekniske vedlegg i Rapportsenteret.", styles["Small"],
        ),
        decision_meta,
        Paragraph("Markedsdekning", styles["Subsection"]),
        coverage_table,
        *([Paragraph("Univers- og sektordekning", styles["Subsection"]), universe_table,
           Paragraph(
               "* Kontrollandel måler kontrolluniversets andel av den konfigurerte markedslisten. "
               "Antall skannet kan være høyere fordi grovskannet også inkluderer dynamisk kildeoppdagede symboler. "
               "Kontrolluniverset er ikke en komplett offisiell børsliste.",
               styles["Tiny"],
           )] if universe_table is not None else []),
        Paragraph("Hovedkonklusjon", styles["Subsection"]),
        Paragraph(escape(str(decision_overview.get("conclusion") or "Ingen konklusjon registrert.")), styles["BodyCompact"]),
        executive_table,
        Paragraph("Rapportgrunnlag - separate mål", styles["Subsection"]),
        decision_status,
        Paragraph(
            "Målene beskriver ulike deler av beslutningsgrunnlaget og er ikke sannsynlighet for gevinst. "
            "Fravær av hendelser etter fullført kontroll regnes som et gyldig kontrollresultat, ikke som kildefeil.",
            styles["Small"],
        ),
    ]

    # The first-page 1-3 table is a transparent review order, not a buy list.
    # Hydrate its compact reduction rows from the canonical candidates so the
    # reasons, blockers and source coverage remain available in the PDF.
    review_candidates = list(run.get("priority_top3") or [])[:3]
    if not review_candidates:
        reduction_early = run.get("autonomous_decision_reduction") if isinstance(run.get("autonomous_decision_reduction"), Mapping) else {}
        review_candidates = list(reduction_early.get("priority_top3") or [])[:3]
    if not review_candidates:
        review_candidates = sorted(
            (dict(row) for row in (run.get("candidates") or []) if isinstance(row, Mapping)),
            key=lambda row: float(row.get("investment_score") or 0), reverse=True,
        )[:3]
    canonical_by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in (run.get("candidates") or []) if isinstance(row, Mapping)
    }
    candidate_rows = [["#", "Ticker", "Score / faktisk utfall", "Hovedgrunn", "Viktigste risiko", "Short / innsider / kilder"]]
    for index, compact_candidate in enumerate(review_candidates, 1):
        ticker = str(compact_candidate.get("ticker") or "").upper()
        candidate = {**dict(canonical_by_ticker.get(ticker, {})), **dict(compact_candidate)}
        profile = candidate.get("confidence") if isinstance(candidate.get("confidence"), Mapping) else {}
        if not profile and isinstance(candidate.get("confidence_profile"), Mapping):
            profile = candidate.get("confidence_profile")
        consensus = candidate.get("source_consensus") if isinstance(candidate.get("source_consensus"), Mapping) else {}
        blockers = [str(value) for value in (candidate.get("blockers") or []) if str(value).strip()]
        rationale = [str(value) for value in (candidate.get("rationale") or []) if str(value).strip()]
        counter = candidate.get("counter_hypothesis") if isinstance(candidate.get("counter_hypothesis"), Mapping) else {}
        main_reason = str(candidate.get("autonomy_outcome_reason") or "") or "; ".join(rationale[:2]) or str(candidate.get("status") or "Ingen hovedgrunn registrert")
        main_risk = str(counter.get("strongest_argument") or (blockers[0] if blockers else "Ingen kritisk risiko registrert"))
        from short_intelligence import normalize_short_snapshot
        short_snapshot = normalize_short_snapshot(candidate)
        short_pct = short_snapshot.get("short_interest_pct_float")
        if short_pct is None:
            short_pct = short_snapshot.get("short_interest_pct_outstanding")
        short_text = f"short {float(short_pct):.2f}%" if short_snapshot.get("verified") and short_pct is not None else "short UKJENT"
        from report_portfolio_intelligence import _nested_evidence
        insider = _nested_evidence(candidate, "insider_intelligence")
        insider_coverage = str(insider.get("coverage") or "NOT_SEARCHED").upper()
        insider_text = {
            "AVAILABLE": str(insider.get("signal") or "FUNNET"),
            "CHECKED_NO_EVENTS": "ingen hendelser", "DISCOVERY_ONLY": "kun kildetreff",
            "PARTIAL_SOURCE_FAILURE": "delvis kildefeil", "SOURCE_ERROR": "kildefeil",
            "NOT_CONFIGURED": "ikke konfigurert", "NOT_SEARCHED": "ikke søkt",
        }.get(insider_coverage, "utilstrekkelig dekning")
        source_text = (
            f"{short_text} · innsider {insider_text} · {consensus.get('independent_sources', 0)} uavh. · "
            f"dok. {profile.get('documentation_coverage', profile.get('data_coverage', 0))}/100"
        )
        candidate_rows.append([
            candidate.get("priority_rank") or index,
            _rawp(candidate.get("ticker") or "-", "Tiny"),
            _p(f"{_fmt(candidate.get('investment_score', candidate.get('score')))} · {candidate.get('autonomy_outcome_label') or _decision_label(candidate.get('portfolio_action') or candidate.get('action'))}", "Tiny"),
            _p(_short(main_reason, 115), "Tiny"),
            _p(_short(main_risk, 135), "Tiny"),
            _p(_short(source_text, 150), "Tiny"),
        ])
    if len(candidate_rows) == 1:
        candidate_rows.append(["-", "Ingen", "-", "Ingen kandidatdata", "-", "-"])
    candidate_table_decision = Table(
        candidate_rows,
        repeatRows=1,
        colWidths=[7*mm, 18*mm, 27*mm, 44*mm, 51*mm, 37*mm],
    )
    candidate_table_decision.setStyle(_table_style(5.2, padding=1.25))
    decision_story += [
        Paragraph("Prioritert vurderingsrekkefølge 1-3", styles["Section"]),
        candidate_table_decision,
        Paragraph(
            "Dette er de høyest rangerte analysene med faktisk utfall synlig. Bare rader som uttrykkelig "
            "er merket streng eller moderat kjøpsanbefaling er anbefalinger; øvrige rader er videre vurdering.",
            styles["Small"],
        ),
    ]
    if decision_candidates:
        recommendation_rows = [["Ticker", "Marked", "Score", "Anbefaling", "Handel"]]
        for row in decision_candidates:
            recommendation_rows.append([
                _rawp(row.get("ticker") or "-", "Tiny"),
                _p(row.get("market") or "-", "Tiny"),
                _p(_fmt(row.get("score")), "Tiny"),
                _p(row.get("status") or row.get("action") or "-", "Tiny"),
                _p("Ingen automatisk transaksjon", "Tiny"),
            ])
        recommendation_table = Table(
            recommendation_rows, repeatRows=1,
            colWidths=[26*mm, 27*mm, 18*mm, 55*mm, 58*mm],
        )
        recommendation_table.setStyle(_table_style(5.5, padding=1.3))
        decision_story += [
            Paragraph(f"Konkrete kjøpsanbefalinger ({len(decision_candidates)})", styles["Section"]),
            recommendation_table,
            Paragraph(
                "Anbefalingene er analyseresultater. Moderate anbefalinger kan ikke opprette ordre eller transaksjoner.",
                styles["Small"],
            ),
        ]
    compact_candidates = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    active_report_markets = {str(value) for value in (run.get("markets") or [])}

    def _market_scope_label(value: Any) -> str:
        market = str(value or "Ukjent")
        if active_report_markets and market not in active_report_markets:
            return f"{market} (eksisterende)"
        return market
    short_market_rows = {row["market"]: row for row in short_coverage_by_market(compact_candidates)}
    insider_market_rows = {row["market"]: row for row in insider_coverage_by_market(compact_candidates)}
    evidence_markets = sorted(set(short_market_rows) | set(insider_market_rows))
    if evidence_markets:
        evidence_rows = [["Marked", "Short kontrollert", "Short ukjent", "Innsider kontrollert", "Innsider ikke søkt", "Kildefeil"]]
        for market in evidence_markets:
            short_row = short_market_rows.get(market, {})
            insider_row = insider_market_rows.get(market, {})
            evidence_rows.append([
                _market_scope_label(market), str(short_row.get("checked", 0)),
                str(int(short_row.get("not_searched", 0)) + int(short_row.get("not_supported", 0))),
                str(insider_row.get("checked", 0)),
                str(int(insider_row.get("not_searched", 0)) + int(insider_row.get("not_configured", 0))),
                str(int(short_row.get("source_errors", 0)) + int(insider_row.get("source_errors", 0))),
            ])
        evidence_table = Table(evidence_rows, repeatRows=1, colWidths=[27*mm, 30*mm, 27*mm, 34*mm, 34*mm, 27*mm])
        evidence_table.setStyle(_table_style(5.2, padding=1.2))
        decision_story += [
            Paragraph("Short- og innsiderdekning", styles["Subsection"]), evidence_table,
            Paragraph(
                "UKJENT betyr at eksponering ikke er dokumentert og regnes aldri som null. "
                "Innsiderstatus skiller kontroll uten hendelser fra ikke søkt og kildefeil. "
                "Markeder merket «eksisterende» inngår ikke i den aktive kandidatskanningen.", styles["Small"],
            ),
        ]
    portfolio_rows = [["Ticker", "Antall", "Inngang", "Nå", "Kostpris", "Markedsverdi", "Vekt %"]]
    for row in list(decision_portfolio.get("positions") or []):
        portfolio_rows.append([
            _rawp(row.get("ticker") or "-", "Tiny"),
            _p(_fmt(row.get("quantity", 0)), "Tiny"),
            _p(_fmt(row.get("entry_price", 0)), "Tiny"),
            _p(_fmt(row.get("last_price", 0)), "Tiny"),
            _p(_fmt(row.get("cost_basis", 0)), "Tiny"),
            _p(_fmt(row.get("market_value", 0)), "Tiny"),
            _p(f"{float(row.get('portfolio_weight_pct') or 0):.2f}", "Tiny"),
        ])
    if len(portfolio_rows) == 1:
        portfolio_rows.append(["-", "Ingen åpne posisjoner", "-", "-", "-", "-", "-"])
    portfolio_table = Table(portfolio_rows, repeatRows=1, colWidths=[23*mm, 22*mm, 25*mm, 25*mm, 30*mm, 32*mm, 22*mm])
    portfolio_table.setStyle(_table_style(5.2, padding=1.2))
    portfolio_result_rows = [["Ticker", "Resultat", "Resultat %", "Eiertid", "Score inn/nå", "Short", "Innsider", "Kapitalstatus"]]
    for row in list(decision_portfolio.get("positions") or []):
        from short_intelligence import normalize_short_snapshot
        short = normalize_short_snapshot(row)
        short_pct = short.get("short_interest_pct_float")
        if short_pct is None:
            short_pct = short.get("short_interest_pct_outstanding")
        if short.get("verified") and short_pct is not None:
            short_label = f"{float(short_pct):.2f}%"
        elif short.get("coverage") == "CHECKED_NO_PUBLIC_POSITION":
            threshold = short.get("public_threshold_pct")
            short_label = f"Ingen offentlig ≥{float(threshold):.1f}%" if threshold is not None else "Ingen offentlige data"
        elif short.get("coverage") == "SOURCE_ERROR":
            short_label = "KILDEFEIL"
        elif short.get("coverage") == "NOT_SUPPORTED":
            short_label = "IKKE STØTTET"
        else:
            short_label = "IKKE SØKT"
        insider = row.get("insider_intelligence") if isinstance(row.get("insider_intelligence"), Mapping) else {}
        insider_coverage = str(insider.get("coverage") or "NOT_SEARCHED").upper()
        insider_label = str(insider.get("signal") or "").replace("STERKT ", "S.") if insider_coverage == "AVAILABLE" else {
            "CHECKED_NO_EVENTS": "INGEN HENDELSER", "DISCOVERY_ONLY": "IKKE STRUKTURERT",
            "PARTIAL_SOURCE_FAILURE": "DELVIS KILDEFEIL", "SOURCE_ERROR": "KILDEFEIL",
            "NOT_CONFIGURED": "IKKE KONFIG.", "NOT_SEARCHED": "IKKE SØKT",
        }.get(insider_coverage, "UTILSTR. DEKNING")
        portfolio_result_rows.append([
            _rawp(row.get("ticker") or "-", "Tiny"),
            _p(_fmt_signed(row.get("unrealized_pnl"), 2), "Tiny"),
            _p(f"{_fmt_signed(row.get('unrealized_pnl_pct'), 2)}%", "Tiny"),
            _p(f"{row.get('holding_days', 0)} dager", "Tiny"),
            _p(f"{float(row.get('entry_score') or 0):.1f} / {float(row.get('current_score') or 0):.1f}", "Tiny"),
            _p(short_label, "Tiny"),
            _p(insider_label, "Tiny"),
            _p("VURDER KAPITALBRUK" if str(row.get("capital_efficiency_status") or "").upper() == "KAPITALEFFEKTIVITETSVARSEL" else str(row.get("capital_efficiency_status") or "BEHOLD"), "Tiny"),
        ])
    if len(portfolio_result_rows) == 1:
        portfolio_result_rows.append(["-", "-", "-", "-", "-", "-", "-", "Ingen åpne posisjoner"])
    portfolio_result_table = Table(portfolio_result_rows, repeatRows=1, colWidths=[18*mm, 21*mm, 18*mm, 19*mm, 24*mm, 25*mm, 27*mm, 28*mm])
    portfolio_result_table.setStyle(_table_style(5.2, padding=1.2))
    accounting_rows = [
        [_p("Startkapital", "Tiny"), _p(_fmt(decision_portfolio.get("initial_capital", 0)), "Tiny"),
         _p("Porteføljeverdi", "Tiny"), _p(_fmt(decision_portfolio.get("portfolio_equity", 0)), "Tiny")],
        [_p("Investert", "Tiny"), _p(f"{_fmt(decision_portfolio.get('total_market_value', 0))} ({_fmt(decision_portfolio.get('invested_pct', 0))} %)", "Tiny"),
         _p("Kontanter", "Tiny"), _p(f"{_fmt(decision_portfolio.get('cash', 0))} ({_fmt(decision_portfolio.get('cash_pct', 0))} %)", "Tiny")],
        [_p("Ledig kjøpslimit", "Tiny"), _p(_fmt(decision_portfolio.get("available_purchase_limit", 0)), "Tiny"),
         _p("Påkrevd reserve", "Tiny"), _p(f"{_fmt(decision_portfolio.get('required_cash_reserve', 0))} ({_fmt(decision_portfolio.get('reserve_cash_pct', 0))} %)", "Tiny")],
        [_p("Realisert resultat", "Tiny"), _p(_fmt_signed(decision_portfolio.get("realized_pnl"), 2), "Tiny"),
         _p("Urealisert resultat", "Tiny"), _p(_fmt_signed(decision_portfolio.get("unrealized_pnl"), 2), "Tiny")],
        [_p("Samlet resultat", "Tiny"), _p(f"{_fmt_signed(decision_portfolio.get('total_result'), 2)} ({_fmt_signed(decision_portfolio.get('total_return_pct'), 2)} %)", "Tiny"),
         _p("Ledige posisjonsplasser", "Tiny"), _p(str(decision_portfolio.get("remaining_position_slots", 0)), "Tiny")],
    ]
    accounting_table = Table(accounting_rows, colWidths=[39*mm, 50*mm, 39*mm, 51*mm])
    accounting_table.setStyle(_table_style(5.4, padding=1.5))
    decision_story += [
        Paragraph("Eksisterende portefølje og kapitalbinding", styles["Section"]),
        Paragraph(
            f"Åpne posisjoner {decision_portfolio.get('open_positions', 0)}/{decision_portfolio.get('maximum_open_positions', 20)} · "
            f"sidelengs {decision_portfolio.get('sideways_positions', 0)} · svekket score {decision_portfolio.get('weakened_positions', 0)} · "
            f"utskiftingsvurdering {decision_portfolio.get('replacement_review_count', 0)}.", styles["BodyCompact"]),
        Paragraph(
            f"Autoritativt snapshot etter Autonomi · kjøring {escape(str(decision_portfolio.get('snapshot_run_id') or run.get('run_id') or '-'))} · "
            f"verdsettelse i {escape(str(decision_portfolio.get('valuation_unit') or 'SIMULERT KONTOENHET'))}.", styles["Small"]),
        accounting_table,
        Paragraph("Posisjoner, verdi og porteføljevekt", styles["Subsection"]),
        portfolio_table,
        Paragraph("Resultat, eiertid og kapitalstatus", styles["Subsection"]),
        portfolio_result_table,
        Paragraph("Alle eksisterende posisjoner er merket som allerede eid; tilleggskjøp er deaktivert. Kapitalstagnasjon utløser vurdering, mens salg og utskifting krever en eksplisitt exitbeslutning.", styles["Small"]),
    ]
    short_exposure = decision_portfolio.get("short_exposure") if isinstance(decision_portfolio.get("short_exposure"), Mapping) else {}
    if short_exposure:
        weighted_short = short_exposure.get("capital_weighted_short_interest_pct")
        weighted_label = f"{_fmt(weighted_short, 2)} %" if weighted_short is not None else "UKJENT"
        decision_story.append(Paragraph(
            f"Shortdekning for porteføljen: {_fmt(short_exposure.get('verified_short_coverage_pct'), 2)} % av markedsverdien · "
            f"kapitalvektet shortandel {weighted_label} · høy-short-eksponering {_fmt(short_exposure.get('high_short_exposure_pct'), 2)} %. "
            "UKJENT er ekskludert og erstattes aldri av volum/momentum.", styles["Small"]))
    active_exit = decision_portfolio.get("active_exit_policy") if isinstance(decision_portfolio.get("active_exit_policy"), Mapping) else {}
    if active_exit:
        exit_rows = [["Regelprofil", "Stop-loss", "Delvis gevinst", "Trailing", "Score-exit", "RSI", "Stagnasjon", "Byttemargin"] , [
            str(active_exit.get("policy_version") or "-"),
            f"-{_fmt(active_exit.get('stop_loss_pct'), 1)} %",
            f"+{_fmt(active_exit.get('take_profit_pct'), 1)} % / {_fmt(active_exit.get('partial_take_profit_pct'), 0)} % salg",
            f"-{_fmt(active_exit.get('trailing_stop_pct'), 1)} % fra topp",
            f"under {_fmt(active_exit.get('score_exit_threshold'), 1)}",
            f"{_fmt(active_exit.get('rsi_exit_level'), 0)} og faller",
            f"{int(active_exit.get('stagnation_days') or 0)} dager",
            f"+{_fmt(active_exit.get('replacement_score_advantage'), 1)} poeng",
        ]]
        exit_table = Table(exit_rows, repeatRows=1, colWidths=[20*mm, 21*mm, 34*mm, 27*mm, 24*mm, 22*mm, 21*mm, 25*mm])
        exit_table.setStyle(_table_style(5.0, padding=1.1))
        decision_story += [Paragraph("Aktiv salgs- og utskiftingsprofil", styles["Subsection"]), exit_table]
    if decision_anomalies:
        decision_story += [Paragraph("Automatisk systemvakt", styles["Section"])]
        for alert in decision_anomalies:
            decision_story.append(Paragraph(
                f"<b>{escape(label_for(alert.get('severity') or 'WARNING'))}</b> · {escape(str(alert.get('message') or '-'))} "
                "Ingen handel tillates før evidenskravet er oppfylt.", styles["BodyCompact"]))
    if decision_watch_queue:
        watch_rows = [["Ticker", "Marked", "Score", "Til 73", "Andre blokkeringer"]]
        for row in list(decision_watch_queue)[:15]:
            watch_rows.append([_rawp(row.get("ticker") or "-", "Tiny"), _p(row.get("market") or "-", "Tiny"),
                               _p(f"{float(row.get('score') or 0):.2f}", "Tiny"), _p(f"{float(row.get('distance_to_production_threshold') or 0):.2f}", "Tiny"),
                               _p(", ".join(label_for(value) for value in (row.get("blocker_codes") or [])) or "Ingen", "Tiny")])
        watch_table = Table(watch_rows, repeatRows=1, colWidths=[28*mm, 28*mm, 22*mm, 22*mm, 84*mm])
        watch_table.setStyle(_table_style(5.4, padding=1.2))
        decision_story += [Paragraph("Observasjonskø 68-73", styles["Section"]), watch_table,
                           Paragraph("Observasjonskøen er ikke en kjøpsanbefaling. Kandidatene vurderes automatisk på nytt.", styles["Small"])]
    rejected_rows = [["Ticker", "Marked", "Score", "Status / kort grunn"]]
    for row in rejected_control:
        rejected_rows.append([row.get("ticker") or "-", _market_scope_label(row.get("market") or "-"), _fmt(row.get("score")), _p(_short(row.get("reason") or row.get("status") or "Avvist", 120), "Tiny")])
    if len(rejected_rows) == 1:
        rejected_rows.append(["-", "-", "-", "Ingen automatisk avviste aksjer"] )
    rejected_table = Table(rejected_rows, repeatRows=1, colWidths=[25*mm, 25*mm, 18*mm, 116*mm])
    rejected_table.setStyle(_table_style(5.5, padding=1.3))
    decision_story += [Paragraph("Kontrollvedlegg – avviste aksjer", styles["Section"]), rejected_table]
    _summary_reconciled = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    decision_story += [Paragraph(
        f"Kandidatavstemming: {len(run.get('candidates') or [])} totalt | {int(_summary_reconciled.get('buy_candidates') or 0)} kjøpsgodkjent | "
        f"{int(_summary_reconciled.get('moderate_buy_recommendations') or 0)} moderat kjøpsanbefalt | "
        f"{int(_summary_reconciled.get('automatic_watch') or 0)} overvåkes | "
        f"{int(_summary_reconciled.get('manual_review') or 0)} undersøkes manuelt | "
        f"{int(_summary_reconciled.get('automatic_rejected') or 0)} avvist",
        styles["Footer"],
    )]
    decision_page_one_end_v1924 = len(decision_story)
    decision_story += [
        CondPageBreak(40*mm),
        Paragraph("Oppfølging, endringer og kontrollpunkter", styles["ReportTitle"]),
        Paragraph("Fokus: " + escape(focus_text or str(report_metadata.get("mission_objective") or "-")), styles["BodyCompact"]),
    ]


    change_rows = [["Endring", "Resultat"]]
    if decision_changes.get("has_previous"):
        change_rows.extend([
            ["Ny / ut av Top 3", _p((", ".join(decision_changes.get("top3_added") or []) or "Ingen") + " / " + (", ".join(decision_changes.get("top3_removed") or []) or "Ingen"), "Tiny")],
        ])
        best = decision_changes.get("largest_improvement") or {}
        weak = decision_changes.get("largest_weakening") or {}
        movement = []
        if best.get("ticker"):
            movement.append(f"{best.get('ticker')} {float(best.get('delta') or 0):+.2f}")
        if weak.get("ticker"):
            movement.append(f"{weak.get('ticker')} {float(weak.get('delta') or 0):+.2f}")
        material_movement = []
        for value in (best, weak):
            if value.get("ticker") and abs(float(value.get("delta") or 0)) >= 1.0:
                material_movement.append(f"{value.get('ticker')} {float(value.get('delta') or 0):+.2f}")
        change_rows.append([
            "Vesentlige scoreendringer (>= 1,00)",
            _p(" / ".join(material_movement) or "Ingen vesentlige scoreendringer", "Tiny"),
        ])
        action_rows = list(decision_changes.get("action_changes") or [])[:2]
        if action_rows:
            change_rows.append(["Endret handling", _p("; ".join(f"{row.get('ticker')}: {_decision_label(row.get('from'))} -> {_decision_label(row.get('to'))}" for row in action_rows), "Tiny")])
    else:
        change_rows.append(["Sammenligning", _p("Ingen sammenlignbar tidligere rapport", "Tiny")])
    change_table_decision = Table(change_rows, repeatRows=1, colWidths=[42*mm, 142*mm])
    change_table_decision.setStyle(_table_style(5.9, padding=1.4))
    decision_story += [Paragraph("Endringer siden forrige rapport", styles["Section"]), change_table_decision]

    diff_rows = [["Ticker", "Score", "Modell / regel", "Sterkeste motargument"]]
    diff_by_ticker = {str(row.get("ticker") or "").upper(): row for row in list(decision_diffs.get("candidates") or [])}
    for candidate in list(decision_candidates)[:3]:
        ticker = str(candidate.get("ticker") or "-").upper()
        row = diff_by_ticker.get(ticker, {})
        model = list(row.get("model_diff") or [])
        rule = list(row.get("decision_diff") or [])
        counter = candidate.get("counter_hypothesis") if isinstance(candidate.get("counter_hypothesis"), Mapping) else {}
        model_text = f"{model[0].get('label')} {float(model[0].get('delta') or 0):+.2f}" if model else "Ingen modellendring"
        if rule:
            model_text += f"; {rule[0].get('label')}: {rule[0].get('effect')}"
        diff_rows.append([
            _p(ticker, "Tiny"),
            _p(f"{float(row.get('net_score_delta') or 0):+.2f}" if row.get("has_previous") else "Ny", "Tiny"),
            _p(_short(model_text, 95), "Tiny"),
            _p(_short(counter.get("strongest_argument") or "Ikke tilgjengelig", 115), "Tiny"),
        ])
    if len(diff_rows) > 1:
        diff_table = Table(diff_rows, repeatRows=1, colWidths=[23*mm, 18*mm, 65*mm, 78*mm])
        diff_table.setStyle(_table_style(5.5, padding=1.3))
        decision_story += [Paragraph("Data-, modell- og beslutningsdiff / motargument", styles["Section"]), diff_table]

    event_lines = []
    for event in list(decision_events)[:2]:
        event_lines.append(f"{_short_datetime(event.get('event_at_local') or event.get('event_at') or '-')}: {event.get('ticker') or 'Marked'} - {_short(event.get('title') or '-', 70)}")
    task_lines = []
    for task in list(decision_tasks)[:3]:
        task_lines.append(f"{task.get('priority') or 'NORMAL'} {task.get('subject') or '-'}: {_short(task.get('action') or '-', 75)}")
    task_count_note = (
        f" Viser {len(task_lines)} av {len(decision_tasks)} oppgaver."
        if len(decision_tasks) > len(task_lines) else ""
    )
    task_rows = [["Prioritet / kandidat", "Automatisk oppfølging"]]
    if task_lines:
        for task in list(decision_tasks)[:3]:
            task_rows.append([
                _p(f"{task.get('priority') or 'NORMAL'} · {task.get('subject') or '-'}", "Tiny"),
                _p(_short(task.get('action') or '-', 130), "Tiny"),
            ])
    else:
        task_rows.append([_p("-", "Tiny"), _p("Ingen automatiske oppfølgingsoppgaver registrert.", "Tiny")])
    task_table_decision = Table(task_rows, repeatRows=1, colWidths=[48*mm, 136*mm])
    task_table_decision.setStyle(_table_style(5.8, padding=1.4))
    if event_lines:
        decision_story += [
            Paragraph("Kritiske hendelser", styles["Subsection"]),
            Paragraph(escape(" | ".join(event_lines)), styles["Small"]),
        ]
    decision_story += [
        Paragraph("Oppgaver til neste kjøring" + escape(task_count_note), styles["Subsection"]),
        task_table_decision,
    ]

    if decision_historical:
        historical_outcome_labels = {
            "UTGÅTT_ELLER_MANGLER_DATA": "Utløpt vurdering - resultatdata mangler",
            "EXPIRED_OR_MISSING_DATA": "Utløpt vurdering - resultatdata mangler",
        }
        historical_text = "; ".join(
            f"{row.get('ticker')}: {historical_outcome_labels.get(str(row.get('outcome') or '').upper(), _loc(row.get('outcome') or '-'))}"
            + (f" ({_fmt(float(row.get('price_return_pct')), 1)} %)" if row.get('price_return_pct') is not None else "")
            for row in list(decision_historical)[:2]
        )
    else:
        historical_text = "Ingen utløpte vurderinger kunne evalueres."
    guard_text = "Produksjonsregler kan ikke endres automatisk; eksplisitt godkjenning kreves."
    if decision_learning_guard.get("production_rules_auto_change_allowed"):
        guard_text = "ADVARSEL: automatisk produksjonsendring er rapportert som tillatt."
    deductions = list(decision_reliability.get("deductions") or [])[:2]
    deduction_text = "; ".join(
        f"−{abs(float(row.get('points') or 0)):g} poeng: {row.get('reason') or '-'}"
        for row in deductions
    ) or "Ingen eksplisitte trekk."
    decision_audit_story = [
        Paragraph("Historisk evaluering / læringsvern", styles["Subsection"]),
        Paragraph(escape(historical_text + " | " + guard_text), styles["Small"]),
        Paragraph("Kvalitetsavvik og forbedringspunkter", styles["Subsection"]),
        Paragraph(escape(_norwegian_decimal_text(deduction_text)), styles["Small"]),
    ]

    story = [Paragraph("AI Aksje Analyzer Pro", styles["ReportTitle"]), Paragraph(escape(report_type), styles["Section"]), meta, Spacer(1, 2*mm)]
    summary = run.get("summary") or {}
    report_summary = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    intelligence = run.get("executive_intelligence") or executive_intelligence(run.get("candidates") or [])
    portfolio_actions = dict((run.get("portfolio_decisions") or {}).get("actions") or {})
    reduction = run.get("autonomous_decision_reduction") if isinstance(run.get("autonomous_decision_reduction"), Mapping) else {}
    reduction_counts = dict(reduction.get("counts") or {})
    manual_review_count = int(report_summary.get("manual_review") or reduction.get("manual_candidates") or 0)
    proposal_summary = run.get("proposal_summary") if isinstance(run.get("proposal_summary"), Mapping) else {}
    learning_summary = run.get("learning_portfolio_summary") if isinstance(run.get("learning_portfolio_summary"), Mapping) else {}
    summary_items = [("Skannet", report_summary.get("scanned", summary.get("scanned", 0))),
                     ("Grundig analysert", report_summary.get("deep_analyzed", len(run.get("candidates") or []))),
                     ("Foreløpige modellkandidater", proposal_summary.get("preliminary_model_candidates", summary.get("proposals", 0))),
                     ("Undersøk manuelt", manual_review_count),
                     ("Overvåkes automatisk", report_summary.get("automatic_watch", reduction.get("automatic_watch", 0))),
                     ("Automatisk avvist", report_summary.get("automatic_rejected", reduction.get("automatic_rejected", 0))),
                     ("Evidens-/dataklare", report_summary.get("evidence_data_ready", 0)),
                     ("Kjøpsgodkjente", report_summary.get("decision_ready", 0)),
                     ("Unike selskaper", intelligence.get("unique_companies", 0)), ("Snittscore", intelligence.get("average_score", 0)),
                     ("Høyeste score", intelligence.get("highest_score", 0)), ("Markeder i Top 10", intelligence.get("markets_in_top10", 0)),
                     ("Produksjonskjøp", learning_summary.get("production_buys", portfolio_actions.get("BUY", 0))),
                     ("Simulerte læringsposisjoner", learning_summary.get("learning_buys", 0))]
    summary_grid = []
    for index in range(0, len(summary_items), 3):
        cells = []
        for label, value in summary_items[index:index+3]:
            cells.append(Paragraph(
                f"<b>{escape(label)}</b><br/><font size='{SUMMARY_VALUE_FONT_SIZE}'>{escape(_format_summary_value(value))}</font>",
                styles["Small"],
            ))
        while len(cells) < 3: cells.append("")
        summary_grid.append(cells)
    summary_table = Table(summary_grid, colWidths=[61.3*mm]*3)
    summary_table.setStyle(_table_style(7, header=False, padding=2))
    decision_conclusion = (
        f"Autonomiutfall: {int(reduction.get('buy_candidates') or 0)} kjøpskandidat(er), "
        f"{int(reduction.get('automatic_watch') or 0)} overvåkes automatisk, "
        f"{int(reduction.get('automatic_rejected') or 0)} automatisk avvist og "
        f"{int(reduction.get('manual_candidates') or 0)} anbefalt undersøkt manuelt. "
        f"Rapporten inneholder {int(reduction.get('manual_task_count') or 0)} konkret(e) manuell(e) oppgave(r)."
    )
    technical_report_ok = bool(integrity.get("ok"))
    technical_report_label = "Bestått" if technical_report_ok else "Feilet"
    decision_confidence_value = int(decision_confidence.get("decision_confidence") or 0)
    is_draft_report = str(identity.get("type") or "").upper() == "UTKAST"
    quick_report_status_v19143 = "Utkast – ikke endelig" if is_draft_report else ("Foreløpig" if report_status.get("state") == "PROVISIONAL" else "Endelig")
    quick_table = Table([[
        Paragraph("<b>Teknisk rapportkontroll</b>", styles["Tiny"]), _p(technical_report_label, "Tiny"),
        Paragraph("<b>Beslutningskonfidens</b>", styles["Tiny"]), _p(f"{decision_confidence_value}/100", "Tiny"),
        Paragraph("<b>Rapportstatus</b>", styles["Tiny"]), _p(quick_report_status_v19143, "Tiny"),
    ]], colWidths=[38*mm, 20*mm, 36*mm, 22*mm, 28*mm, 40*mm])
    quick_table.setStyle(_table_style(6.8, header=False, padding=2.5))
    report_state_raw = "DRAFT" if is_draft_report else ("PROVISIONAL" if report_status.get("state") == "PROVISIONAL" else "PASS")
    quality_state_raw = "PASS" if technical_report_ok else "ERROR"
    notification = run.get("notification") if isinstance(run.get("notification"), Mapping) else {}
    notification_channels = run.get("notification_channels") if isinstance(run.get("notification_channels"), Mapping) else {}
    learning_notification = notification_channels.get("learning") if isinstance(notification_channels.get("learning"), Mapping) else {}
    notification_raw = "PASS" if (notification.get("sent") is True or str(notification.get("status") or "").upper() in {"SENT", "OK", "SUCCESS"}) else ("ERROR" if notification.get("attempted") else "NOT_SEARCHED")
    combined_quality = run.get("combined_quality") if isinstance(run.get("combined_quality"), Mapping) else (run.get("combined_data_quality") if isinstance(run.get("combined_data_quality"), Mapping) else {})
    # The report, JSON and notification channels must use the same canonical
    # population.  ``combined_data_quality`` may have been calculated before
    # owned positions were appended, so its historical ``evaluated`` value is
    # provenance only and must never become the active report denominator.
    coverage_contract_pdf = (
        run.get("production_coverage_contract")
        if isinstance(run.get("production_coverage_contract"), Mapping)
        else {}
    )
    report_summary_pdf = (
        run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    )
    source_total = int(
        report_summary_pdf.get("coverage_candidate_total")
        or coverage_contract_pdf.get("candidate_total")
        or len(run.get("candidates") or [])
        or 0
    )
    source_valid = int(
        report_summary_pdf.get("evidence_data_ready")
        if report_summary_pdf.get("evidence_data_ready") is not None
        else coverage_contract_pdf.get("evidence_data_ready") or 0
    )
    source_raw = "PASS" if source_total and source_valid >= source_total else ("ERROR" if source_total and source_valid == 0 else "REVIEW")
    notification_text = _notification_status_explanation(notification)
    status_stripe = Table([[
        Paragraph(f"<font color='{decision_text_color(report_state_raw)}'>●</font> <b>Rapportstatus</b><br/>{'Utkast – ikke endelig' if is_draft_report else ('Foreløpig rapport – automatisk revalidering' if report_status.get('state') == 'PROVISIONAL' else 'Endelig rapport')}", styles["Small"]),
        Paragraph(f"<font color='{decision_text_color(quality_state_raw)}'>●</font> <b>Teknisk rapportkontroll</b><br/>{technical_report_label}", styles["Small"]),
        Paragraph(f"<font color='{decision_text_color(source_raw)}'>●</font> <b>Kilde-/evidenskontroll</b><br/>{source_valid}/{source_total} kandidater evidensklare" if source_total else "<b>Kildekontroll</b><br/>Ikke målt", styles["Small"]),
        Paragraph(
            f"<font color='{decision_text_color(notification_raw)}'>●</font> <b>Pushover – rapport</b><br/>{escape(_loc(notification_text))}"
            f"<br/><b>Pushover – læring</b>: {escape(str(learning_notification.get('status_label') or 'Ingen læringsvarsler'))}"
            f" ({int(learning_notification.get('sent_count') or 0)})",
            styles["Small"],
        ),
    ]], colWidths=[42*mm, 42*mm, 42*mm, 42*mm])
    status_stripe.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), .35, grid),
        ("BACKGROUND", (0,0), (0,0), colors.HexColor(decision_color(report_state_raw))),
        ("TEXTCOLOR", (0,0), (0,0), colors.HexColor(decision_text_color(report_state_raw))),
        ("BACKGROUND", (1,0), (1,0), colors.HexColor(decision_color(quality_state_raw))),
        ("TEXTCOLOR", (1,0), (1,0), colors.HexColor(decision_text_color(quality_state_raw))),
        ("BACKGROUND", (2,0), (2,0), colors.HexColor(decision_color(source_raw))),
        ("TEXTCOLOR", (2,0), (2,0), colors.HexColor(decision_text_color(source_raw))),
        ("BACKGROUND", (3,0), (3,0), colors.HexColor(decision_color(notification_raw))),
        ("TEXTCOLOR", (3,0), (3,0), colors.HexColor(decision_text_color(notification_raw))),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    learning_text = (
        f"Porteføljer holdes adskilt: {int(learning_summary.get('production_buys', portfolio_actions.get('BUY', 0)) or 0)} produksjonskjøp / "
        f"{int(learning_summary.get('learning_buys', 0) or 0)} simulerte læringsposisjoner; "
        f"{int(learning_summary.get('production_open_positions', 0) or 0)} produksjonsposisjoner / "
        f"{int(learning_summary.get('learning_open_positions', 0) or 0)} læringsposisjoner."
    )
    threshold_explanation = str(reduction.get("threshold_explanation") or "").strip()
    story += [Paragraph("Sammendrag", styles["Section"])]
    if is_draft_report:
        draft_banner = Table([[Paragraph(
            "<b>UTKAST – AVVENTER ENDELIG VALIDERING</b><br/>Rapporten kan inneholde analyser som ikke er søkt, ikke er tilgjengelige eller må revalideres. Den skal ikke behandles som en endelig investeringsrapport.",
            styles["BodyCompact"],
        )]], colWidths=[168*mm])
        draft_banner.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#FFF3CD")),
            ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#7A4B00")),
            ("BOX", (0,0), (-1,-1), .8, colors.HexColor("#D99A00")),
            ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story += [draft_banner, Spacer(1, 1.5*mm)]
    story += [status_stripe, Spacer(1, 1*mm), summary_table, quick_table,
              Paragraph(escape(decision_conclusion), styles["BodyCompact"]),
              Paragraph(escape(learning_text), styles["Small"])]
    learning_rows = []
    for decision in list(learning_summary.get("learning_fills") or []):
        if not isinstance(decision, Mapping):
            continue
        action = str(decision.get("side") or decision.get("action") or decision.get("decision") or "").upper()
        if action not in {"BUY", "SELL"}:
            continue
        reason_text = str(decision.get("reason") or "")
        display_action = "LUKKET VED PROMOTERING" if action == "SELL" and "promot" in reason_text.casefold() else action
        blockers = decision.get("production_blockers_at_entry") or decision.get("production_blockers") or decision.get("blockers") or []
        if isinstance(blockers, str):
            blockers = [blockers]
        learning_rows.append([
            _p(decision.get("ticker") or "-"), _p(display_action),
            _p(str(decision.get("quantity") or "-").replace(".", ",")),
            _p((f"{float(decision.get('price')):.2f}".replace(".", ",") if decision.get("price") is not None else "-")),
            _p(_format_summary_value(decision.get("score", decision.get("autonomy_adjusted_investment_score", decision.get("investment_score", 0))))),
            _p(", ".join(str(value) for value in list(blockers)[:2]) or "Ingen"),
        ])
    if learning_rows:
        learning_table = Table(
            [["Ticker", "Resultat", "Antall", "Pris", "Score", "Produksjonsblokkering"]] + learning_rows[:10],
            repeatRows=1, colWidths=[22*mm, 18*mm, 22*mm, 20*mm, 17*mm, 69*mm],
        )
        learning_table.setStyle(_table_style(6.3, padding=2))
        story += [Paragraph("Læringskontohandler i denne kjøringen", styles["Subsection"]), learning_table]
    if threshold_explanation:
        story += [Paragraph(escape(_norwegian_decimal_text(threshold_explanation)), styles["Small"])]
    candidate_minutes = int(report_status.get("candidate_validity_minutes") or 60)
    report_hours = int(report_status.get("revalidation_after_hours") or 6)
    story += [Paragraph(
        escape(f"Gyldighetsregler: Kandidatbeslutningen utløper etter {candidate_minutes} minutter. Hele rapporten revalideres senest etter {report_hours} timer. Dette er to separate kontrollgrenser."),
        styles["Small"],
    )]
    critique: list[str] = []
    if report_status.get("state") == "PROVISIONAL":
        critique.append("Kildekontrollen er ikke fullført")
    if int(reduction.get("manual_task_count") or 0):
        critique.append("Én eller flere kandidater har en konkret manuell undersøkelsesoppgave")
    if int((run.get("data_quality") or {}).get("errors") or 0):
        critique.append("Datainnhentingen inneholdt tekniske feil")
    if source_total and source_valid < source_total:
        critique.append(f"Kildegrunnlaget er bare samlet godkjent for {source_valid} av {source_total} kandidater")
    if int((run.get("quality_metrics") or {}).get("candidate_evidence_coverage_average") or 0) < 70:
        critique.append("Gjennomsnittlig evidensdekning er lav og begrenser beslutningsstyrken")
    if not critique:
        critique.append("Ingen kritiske tekniske avvik er registrert; investeringsrisiko og modellusikkerhet består")
    story += [KeepTogether([
        Paragraph("Metode og ansvarsfraskrivelse / rapportens egenkritikk", styles["Subsection"]),
        Paragraph(
            "Rapporten er automatisk beslutningsstøtte basert på tilgjengelige data. Den er ikke personlig investeringsrådgivning og utfører ingen handler. "
            "Programmet avslutter eller overvåker de fleste kandidater automatisk; bare uttrykkelig merkede oppgaver krever manuell kontroll. "
            + escape(". ".join(critique)) + ".",
            styles["Small"],
        ),
    ])]
    if source_total and source_valid == 0:
        invalid_table = Table([[Paragraph(
            "<b>Ingen kandidat bestod samlet kildekontroll</b><br/>"
            + f"Kildekontrollen viser 0/{source_total} gyldige kandidater. Topplister er derfor foreløpige og må ikke tolkes som kjøpsklare anbefalinger.",
            styles["BodyCompact"],
        )]], colWidths=[168*mm])
        invalid_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor(decision_color("ERROR"))), ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor(decision_text_color("ERROR"))), ("BOX", (0,0), (-1,-1), .5, colors.HexColor("#DC2626")), ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
        story += [invalid_table]
    if report_status.get("state") == "PROVISIONAL":
        gaps = ", ".join(
            f"{row.get('ticker')}/{row.get('area')}: {row.get('status')}"
            for row in list(report_status.get("critical_gaps") or [])[:8]
        )
        warning_table = Table([[Paragraph(
            "<b>Foreløpig rapport – automatisk revalidering pågår</b><br/>"
            + escape(_loc(gaps or "Vesentlig dokumentasjon mangler"))
            + ". Kandidater med mangler kan ikke behandles som kjøpsklare. Rapporten revalideres automatisk, og denne revisjonen beholdes.",
            styles["BodyCompact"],
        )]], colWidths=[168*mm])
        warning_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor(decision_color("REVIEW"))), ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor(decision_text_color("REVIEW"))), ("BOX", (0,0), (-1,-1), .5, colors.HexColor("#EAB308")), ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
        story += [warning_table]
    preflight = run.get("integrity_preflight") if isinstance(run.get("integrity_preflight"), Mapping) else {}
    if preflight:
        preflight_rows = [["Kontroll", "Status", "Detalj"]]
        for row in preflight.get("checks") or []:
            preflight_rows.append([_p(row.get("name")), _status_label(row.get("status")), _p(row.get("detail"))])
        preflight_table = Table(preflight_rows, repeatRows=1, colWidths=[40*mm, 24*mm, 104*mm])
        preflight_table.setStyle(_table_style(6.4, padding=2))
        story += [Paragraph("Forhåndskontroll før skanning", styles["Subsection"]), preflight_table]
    change_summary = run.get("change_since_previous") if isinstance(run.get("change_since_previous"), Mapping) else {}
    if change_summary:
        change_table = Table([
            ["Topp 3 endret", "Nye", "Forbedret", "Svekket", "Utgått", "Kildehelse Δ", "Vesentlig"],
            [
                "Ja" if change_summary.get("top3_changed") else "Nei",
                change_summary.get("new_candidates", 0),
                change_summary.get("improved_candidates", 0),
                change_summary.get("weakened_candidates", 0),
                change_summary.get("dropped_candidates", 0),
                change_summary.get("degraded_source_delta", 0),
                "Ja" if change_summary.get("material_change") else "Nei",
            ],
        ], colWidths=[26*mm, 20*mm, 24*mm, 22*mm, 20*mm, 28*mm, 24*mm])
        change_table.setStyle(_table_style(6.3, padding=2))
        story += [Paragraph("Hva har endret seg siden forrige rapport?", styles["Subsection"]), change_table]
    user_mission = run.get("user_mission") or {}
    mission_summary = run.get("mission_summary") or {}
    if user_mission:
        report_goal, report_search = _report_mission_labels()
        mission_table = Table([
            [_p("Mål"), _p(report_goal), _p("Tidshorisont"), _p(user_mission.get("horizon", "-"))],
            [_p("Leter etter"), _p(report_search), _p("Strategi"), _p(user_mission.get("strategy", "-"))],
            [_p("Risiko"), _p(user_mission.get("risk", "-")), _p("Risikogrense"), _p(mission_summary.get("risk_ceiling", "-"))],
            [_p("Porteføljebehov"), _p(user_mission.get("portfolio_need", "-")), _p("Minimum datakvalitet"), _p(user_mission.get("minimum_data_quality", "-"))],
            [_p("Bransjer"), _p(", ".join(user_mission.get("sectors") or []) or "Alle"), _p("Innenfor oppdrag"), _p(mission_summary.get("eligible", 0))],
            [_p("Eksklusjoner"), _p(", ".join(user_mission.get("exclusions") or []) or "Ingen"), _p("Kandidatantall"), _p(user_mission.get("candidate_count", "-"))],
            [_p("Utenfor oppdrag"), _p(mission_summary.get("excluded", 0)), _p("Oppdrags-ID"), _p(user_mission.get("mission_id", "-"))],
            [_p("Konfigurasjon"), _p(user_mission.get("configuration_version", "-")), "", ""],
        ], colWidths=[27*mm, 67*mm, 29*mm, 61*mm])
        mission_table.setStyle(_table_style(7, header=False, padding=2.5))
        mission_table.setStyle(TableStyle([("SPAN", (1, 7), (3, 7))]))
        story += [Paragraph("Autonomi-oppdrag", styles["Subsection"]), mission_table,
                  Paragraph("Kandidater utenfor valgt risiko eller bransje kan vises for sporbarhet, men går ikke videre til beslutningsdelen.", styles["Small"])]
    diagnostics = run.get("market_diagnostics") or []
    if diagnostics:
        diag_data = [["Marked", "Skannet", "Analysert", "Live", "Markedsdatafeil", "Hoppet over", "Feilhendelser", "Status"]]
        for item in diagnostics:
            status_text = item.get("status", "-")
            if item.get("error_detail"):
                status_text = f"{status_text}: {item.get('error_detail')}"
            diag_data.append([
                item.get("market"), item.get("scanned", 0), item.get("analyzed", 0), item.get("live", 0),
                item.get("market_data_errors", item.get("errors", 0)), item.get("skipped_candidate_count", 0),
                item.get("candidate_error_events", 0), _p(status_text),
            ])
        diag_table = Table(diag_data, repeatRows=1, colWidths=[22*mm, 18*mm, 20*mm, 13*mm, 24*mm, 20*mm, 22*mm, 29*mm])
        diag_table.setStyle(_table_style())
        story += [Paragraph("Analysefordeling per marked", styles["Subsection"]), diag_table]
    market_status = run.get("market_status") or []
    if market_status:
        ms_data = [["Marked", "Status", "Lokal tid", "Forklaring", "Siste handelsdato"]]
        for item in market_status:
            ms_data.append([item.get("market"), item.get("status"), item.get("local_time"), item.get("reason"), item.get("latest_trade_date") or "Ukjent"])
        ms_table = Table(ms_data, repeatRows=1, colWidths=[24*mm, 20*mm, 20*mm, 55*mm, 38*mm])
        ms_table.setStyle(_table_style())
        story += [Paragraph("Markedsstatus", styles["Subsection"]), ms_table]
    quality = run.get("data_quality") or {}
    if quality:
        quality_table = Table([["Markedsdata", f"{_fmt(quality.get('score', 0), 1)} %", "Vurdering", _loc(quality.get("label", "-")), "Live", quality.get("live", 0), "Cache", quality.get("cache", 0), "Feil", quality.get("errors", 0)]], colWidths=[18*mm,13*mm,18*mm,29*mm,10*mm,10*mm,11*mm,10*mm,10*mm,10*mm])
        quality_table.setStyle(_table_style(6.8, header=False, padding=2))
        quality_table.setStyle(TableStyle([("FONTNAME", (0,0), (-1,0), "Helvetica"), ("FONTNAME", (0,0), (0,0), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,0), "Helvetica-Bold"), ("FONTNAME", (4,0), (4,0), "Helvetica-Bold"), ("FONTNAME", (6,0), (6,0), "Helvetica-Bold"), ("FONTNAME", (8,0), (8,0), "Helvetica-Bold")]))
        story += [Paragraph("Teknisk fullstendighet og markedsdatadekning", styles["Subsection"]), quality_table,
                  Paragraph("Poengsummen over gjelder kurs- og markedsdata. Innsider-, nyhets-, analyse- og historisk test-dekning vurderes separat og kan redusere beslutningskonfidensen.", styles["Small"])]
        if quality.get("failed_markets"):
            story += [Paragraph("Datakvaliteten er redusert fordi valgte markeder feilet eller ga null kandidater: " +
                                escape(", ".join(quality.get("failed_markets") or [])) + ".", styles["Small"])]
    contract_summary = run.get("data_contract") or {}
    if contract_summary:
        actions = contract_summary.get("actions") or {}
        contract_table = Table([
            ["Kontrollert", contract_summary.get("evaluated", 0), "Gyldig for beslutning", contract_summary.get("valid_for_decision", 0),
             "Blokkert", len(contract_summary.get("blocked") or []), "Fallback", len(contract_summary.get("fallback") or [])],
            ["Fortsett", actions.get("FORTSETT", 0), "Hent på nytt", actions.get("HENT_PÅ_NYTT", 0),
             "Stopp beslutning", actions.get("STOPP_BESLUTNING", 0), "Fallback / redusert", actions.get("BRUK_FALLBACK", 0) + actions.get("REDUSER_KONFIDENS", 0)],
        ], colWidths=[26*mm, 18*mm]*4)
        contract_table.setStyle(_table_style(6.6, header=False, padding=2.2))
        story += [Paragraph("Datakontroll: aktualitet og gyldighet", styles["Subsection"]), contract_table,
                  Paragraph(escape(str(contract_summary.get("approval_rule") or "Ingen anbefaling på kritiske, foreldede data")), styles["Small"])]
    combined_quality = run.get("combined_data_quality") or {}
    if combined_quality:
        combined_table = Table([
            ["Samlet status", combined_quality.get("status", "-"), "Markedsdata gyldig", combined_quality.get("market_data_valid", 0)],
            ["Evidens gyldig", combined_quality.get("evidence_valid", 0), "Samlet gyldig", combined_quality.get("overall_valid", 0)],
            ["Verifiserte fakta", combined_quality.get("verified_evidence_facts", 0), "Kilder forsøkt", combined_quality.get("sources_attempted", 0)],
            ["Nyheter verifisert", combined_quality.get("news_verified", 0), "Insider verifisert", combined_quality.get("insider_verified", 0)],
            ["NewsAPI ratebegrenset", combined_quality.get("news_rate_limited", 0), "Samlet vurdering", combined_quality.get("status", "-")],
            ["Tekniske evidensavvik", combined_quality.get("manual_review_required", 0), "Konkrete manuelle oppgaver", int(reduction.get("manual_task_count") or 0)],
            ["Grønn samlet status", "JA" if combined_quality.get("green") else "NEI", "Automatisk oppfølging", int(reduction.get("automatic_watch") or 0)],
        ], colWidths=[31*mm, 61*mm, 37*mm, 39*mm])
        combined_table.setStyle(_table_style(6.5, header=False, padding=2.2))
        combined_table.setStyle(TableStyle([("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
                                            ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold")]))
        story += [
            Paragraph("Samlet datakvalitet og evidensgyldighet", styles["Subsection"]),
            combined_table,
            Paragraph("Grønn status krever både gyldige markedsdata og tilstrekkelig dokumentert evidens. Markedsdata alene kan ikke gi grønn beslutningsstatus.", styles["Small"]),
        ]
    source_health = run.get("source_health") if isinstance(run.get("source_health"), Mapping) else {}
    if source_health:
        source_rows = [["Kilde", "Område", "Forsøk", "OK", "Treff", "429", "Kvote", "Feil", "Siste status"]]
        for row in list(source_health.get("sources") or [])[:20]:
            source_rows.append([
                _p(row.get("source")), _p(", ".join(row.get("areas") or [])),
                row.get("attempts", 0), row.get("successes", 0), row.get("with_results", 0),
                row.get("rate_limited", 0), row.get("quota_exceeded", 0), row.get("errors", 0),
                _p(_status_label(row.get("last_status") or "-")),
            ])
        source_table = Table(
            source_rows, repeatRows=1,
            colWidths=[38*mm, 20*mm, 16*mm, 15*mm, 14*mm, 13*mm, 14*mm, 13*mm, 34*mm],
        )
        source_table.setStyle(_table_style(5.8, padding=1.6))
        budget = source_health.get("newsapi_budget") if isinstance(source_health.get("newsapi_budget"), Mapping) else {}
        budget_text = (
            f"NewsAPI {budget.get('plan') or '-'}: {budget.get('used_today', 0)} brukt, "
            f"{budget.get('remaining_today', 0)} igjen av lokalt døgnbudsjett {budget.get('daily_budget', 0)}. "
            f"Cachetreff {budget.get('cache_hits', 0)}. "
            + (f"Planen har oppgitt {budget.get('developer_delay_hours')} timers forsinkelse." if budget.get("developer_delay_hours") else "")
        )
        story += [Paragraph("Global kildehelse og API-budsjett", styles["Subsection"]),
                  Paragraph("Tabellen viser global systemhelse og kan inneholde kilder som ikke ble brukt i denne kjøringen. Kandidatbevis og søkelogger nedenfor er autoritative for denne rapporten.", styles["Small"]),
                  source_table, Paragraph(escape(budget_text), styles["Small"])]
    discovery = run.get("discovery_data") or {}
    if discovery:
        discovery_rows = [["Marked", "Valgt", "Dokumentert", "Nye", "Eksperimentelle", "Karantene", "Rotert"]]
        for item in discovery.get("markets") or []:
            actual = item.get("composition_actual") or {}
            discovery_rows.append([
                item.get("market"), item.get("selected", 0), actual.get("DOCUMENTED", 0),
                actual.get("NEW", 0), actual.get("EXPERIMENTAL", 0), item.get("quarantined", 0),
                "JA" if item.get("rotated_from_previous") else "BEGRENSET",
            ])
        if len(discovery_rows) > 1:
            discovery_table = Table(discovery_rows, repeatRows=1, colWidths=[25*mm, 18*mm, 25*mm, 18*mm, 27*mm, 22*mm, 24*mm])
            discovery_table.setStyle(_table_style(6.5, padding=2))
            story += [Paragraph("Kandidatfunn og datagrunnlag", styles["Subsection"]),
                      Paragraph("Målfordeling: 70 % dokumenterte, 20 % nye og 10 % eksperimentelle kandidater. Uendrede kildebevis merkes med analysekarantene.", styles["Small"]),
                      discovery_table]
    refresh = run.get("data_refresh") or {}
    refresh_table = Table([
                  ["Full ny analyse", "JA" if refresh.get("force_refresh_requested") else "NEI", "Cache-bypass", "JA" if refresh.get("cache_bypass_verified") else ("IKKE RELEVANT" if not refresh.get("force_refresh_requested") else "NEI"), "Live-forsøk", refresh.get("live_attempt_count", 0)],
                  ["Live OK", refresh.get("live_count", 0), "Cache", refresh.get("cache_count", 0), "Feil", refresh.get("error_count", 0)],
                  ["Handelsdato(er)", ", ".join(refresh.get("latest_trade_dates") or []) or "Ukjent", "Uendret", f"{refresh.get('unchanged_market_data_count', 0)} av {refresh.get('comparable_market_data_count', 0)}", "", ""],
                  ["Verifikasjon", refresh.get("verification_reason", "-"), "", "", "", ""],
              ], colWidths=[26*mm,35*mm,24*mm,38*mm,23*mm,23*mm])
    refresh_table.setStyle(_table_style(6.8, header=False, padding=2.3))
    refresh_table.setStyle(TableStyle([("SPAN", (3,2), (5,2)), ("SPAN", (1,3), (5,3)), ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,2), "Helvetica-Bold"), ("FONTNAME", (4,0), (4,1), "Helvetica-Bold")]))
    story += [Paragraph("Datainnhenting og cachekontroll", styles["Subsection"]), refresh_table,
              Spacer(1, 1*mm)]
    trace_rows = refresh.get("execution_trace") or []
    if trace_rows:
        trace_data = [["Ticker", "Marked / land", "Kursdatakilde", "Status", "Cache-bypass", "Siste handelsdato", "Endret"]]
        for item in trace_rows[:30]:
            changed = item.get("market_data_changed")
            trace_data.append([item.get("ticker"), infer_market_from_ticker(str(item.get("ticker") or ""), str(item.get("market") or "")), item.get("data_source"), item.get("data_fetch_status"),
                               "JA" if item.get("cache_bypass_applied") else "NEI", item.get("latest_trade_date") or "Ukjent",
                               "JA" if changed is True else ("NEI" if changed is False else "IKKE SAMMENLIGNBAR")])
        trace_table = Table(trace_data, repeatRows=1, colWidths=[19*mm, 23*mm, 26*mm, 18*mm, 22*mm, 31*mm, 27*mm])
        trace_table.setStyle(_table_style(6.2, padding=1.8))
        story += [Paragraph("Kjøringsbevis per ticker", styles["Subsection"]), trace_table]
    changes = run.get("changes") or {}
    changes_table = Table([["Nye", len(changes.get("new", [])), "Forbedret", len(changes.get("improved", [])), "Svekket", len(changes.get("weakened", [])), "Utgått", len(changes.get("dropped", []))]], colWidths=[23*mm,15*mm]*4)
    changes_table.setStyle(_table_style(7, header=False, padding=2.5))
    changes_table.setStyle(TableStyle([("FONTNAME", (0,0), (-1,0), "Helvetica"), ("FONTNAME", (0,0), (0,0), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,0), "Helvetica-Bold"), ("FONTNAME", (4,0), (4,0), "Helvetica-Bold"), ("FONTNAME", (6,0), (6,0), "Helvetica-Bold")]))
    story += [Paragraph("Endringer siden forrige kjøring", styles["Subsection"]), changes_table]
    candidates = run.get("candidates") or []
    candidate_by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in candidates if isinstance(row, Mapping)
    }

    def _candidate_outcome_label(ticker: Any, fallback: Any = "-") -> str:
        candidate = candidate_by_ticker.get(str(ticker or "").upper(), {})
        return str(candidate.get("autonomy_outcome_label") or _decision_label(candidate.get("autonomy_outcome_code") or fallback))

    def _clean_legacy_portfolio_reason(value: Any) -> str:
        text = _loc(str(value or ""))
        text = text.replace("Porteføljelaget ga Undersøk manuelt", "Porteføljelaget kjøpsgodkjente ikke kandidaten")
        text = text.replace("Handlingsporten står i Undersøk manuelt", "Handlingsporten kjøpsgodkjenner ikke kandidaten")
        return text

    insider_coverage = insider_coverage_by_market(candidates)
    if insider_coverage:
        coverage_data = [["Marked", "Kontrollert", "Verifisert", "Kilder funnet", "Ingen hendelser", "Ikke søkt", "Ikke konfig.", "Kildefeil", "Konfigurert primærkilde"]]
        for item in insider_coverage:
            coverage_data.append([
                item.get("market"), item.get("checked", 0), item.get("verified", 0),
                item.get("discovery", 0), item.get("no_events", 0), item.get("not_searched", 0),
                item.get("not_configured", 0), item.get("source_errors", 0),
                _p(item.get("source") or "Ikke tilgjengelig"),
            ])
        coverage_table = Table(coverage_data, repeatRows=1, colWidths=[17*mm, 17*mm, 16*mm, 17*mm, 20*mm, 16*mm, 17*mm, 15*mm, 43*mm])
        coverage_table.setStyle(_table_style(6.3, padding=1.8))
        story += [Paragraph("Insiderdekning per marked", styles["Section"]),
                  Paragraph("Status skiller mellom verifiserte transaksjoner, kildetreff, kontroll uten hendelser, ikke søkt, manglende konfigurasjon og kildefeil. En konfigurert primærkilde regnes ikke som kontrollert før den faktisk er forsøkt. Bare verifiserte transaksjoner er dokumentert evidens.", styles["Small"]),
                  coverage_table]
    insider_rows = []
    for candidate in candidates:
        raw = candidate.get("raw") or {}
        insider = raw.get("insider_intelligence") or {}
        if str(insider.get("coverage") or "") == "AVAILABLE":
            insider_rows.append(candidate)
    if insider_rows:
        insider_rows.sort(key=lambda x: float((x.get("raw") or {}).get("insider_score", 50) or 50), reverse=True)
        idata = [["Ticker", "Marked", "Signal", "Score", "Kjøp", "Salg", "Nettoverdi"]]
        for item in insider_rows[:10]:
            raw = item.get("raw") or {}; ins = raw.get("insider_intelligence") or {}
            currency = market_currency(item.get("market"), item.get("ticker"), ins.get("currency"))
            idata.append([item.get("ticker"), item.get("market"), _loc(raw.get("insider_signal")), _fmt(raw.get("insider_score")), ins.get("buy_count", 0), ins.get("sell_count", 0), format_whole_currency(ins.get("net_value", 0), currency)])
        itable = Table(idata, repeatRows=1, colWidths=[24*mm, 24*mm, 31*mm, 17*mm, 17*mm, 17*mm, 32*mm])
        itable.setStyle(_table_style())
        story += [Paragraph("Innsideranalyse", styles["Section"]), Paragraph("Offentlig registrerte insidertransaksjoner. Manglende dekning gir nøytral score og skal ikke tolkes som fravær av handler.", styles["Small"]), itable]
    news_rows = []
    for candidate in candidates:
        raw = candidate.get("raw") or {}
        news = raw.get("news_intelligence") or {}
        if str(news.get("coverage") or "") == "AVAILABLE":
            news_rows.append(candidate)
    if news_rows:
        news_rows.sort(key=lambda x: float((x.get("raw") or {}).get("news_score", 50) or 50), reverse=True)
        ndata = [["Ticker", "Marked", "Sentiment", "Score", "Saker", "Høy påvirkning", "Kort oppsummering"]]
        for item in news_rows[:10]:
            raw = item.get("raw") or {}; news = raw.get("news_intelligence") or {}
            ndata.append([item.get("ticker"), item.get("market"), _loc(raw.get("news_sentiment")), _fmt(raw.get("news_score")), news.get("article_count", 0), news.get("high_impact_count", 0), _p(_loc(_short(news.get("summary"), 180)))])
        ntable = Table(ndata, repeatRows=1, colWidths=[20*mm, 21*mm, 25*mm, 14*mm, 14*mm, 22*mm, 54*mm])
        ntable.setStyle(_table_style(6.4, padding=2))
        story += [Paragraph("Nyhets- og sentimentanalyse", styles["Section"]), Paragraph("Unike, ferske nyhetssaker vektes etter sentiment, kildekvalitet, aktualitet og hendelsespåvirkning. Manglende dekning gir nøytral score.", styles["Small"]), ntable]
    if run.get("analysis_aborted"):
        story += [Paragraph("Analyse avbrutt – utilstrekkelige data", styles["Section"]),
                  Paragraph("Alle tilgjengelige live-hentinger feilet. Rangering, medaljer, anbefalinger og teoretisk portefølje er derfor deaktivert for denne kjøringen.", styles["BodyCompact"])]
    elif candidates:
        final_candidates = list(run.get("final_decision_top3") or run.get("decision_ready_top3") or [])
        raw_candidates = []
        priority_candidates = list(final_candidates)
        # Priority rows are compact in persisted JSON. Hydrate them from the one
        # canonical full candidate list for evidence pages without reintroducing
        # duplicate raw payloads in the report model.
        full_by_ticker = {
            str(row.get("ticker") or "").upper(): row
            for row in candidates if isinstance(row, Mapping)
        }
        hydrated_priority: list[dict[str, Any]] = []
        for priority in priority_candidates:
            if not isinstance(priority, Mapping):
                continue
            ticker_key = str(priority.get("ticker") or "").upper()
            full = dict(full_by_ticker.get(ticker_key) or {})
            full.update(dict(priority))
            hydrated_priority.append(full)
        priority_candidates = hydrated_priority
        shortlist_mode = "BUY_RECOMMENDATIONS_ONLY"
        medal_candidates = priority_candidates
        shortlist_heading = f"Kjøpsgodkjente kandidater ({len(medal_candidates)})"
        shortlist_labels = [f"PRIORITET {index}" for index in range(1, len(medal_candidates) + 1)]
        shortlist_note = (
            "Rangeringen viser bare aksjer som er endelig kjøpsgodkjent av data-, evidens-, portefølje- og risikoportene. "
            "Avviste aksjer er ikke kandidater og vises kun kort i kontrollvedlegget."
        )

        story += [Paragraph(shortlist_note, styles["BodyCompact"])]
        medal_data = []
        for idx, r in enumerate(medal_candidates):
            evidence = _candidate_evidence(r, medal_candidates[idx + 1] if idx + 1 < len(medal_candidates) else None)
            display_name = str(r.get("name") or r.get("ticker") or "-")
            weight_text = f"Vekt {_fmt(r.get('proposed_position_pct', 0))} %" if str(r.get("portfolio_action") or "").upper() == "BUY" else "Ingen kjøpsvekt"
            profile = r.get("confidence_profile") if isinstance(r.get("confidence_profile"), Mapping) else {}
            market_coverage = profile.get("market_data_coverage", r.get("data_quality", "-"))
            documentation_coverage = profile.get("documentation_coverage", profile.get("data_coverage", "-"))
            medal_data.append([Paragraph(
                f"<b>{shortlist_labels[idx]}</b><br/><b>{escape(display_name)}</b><br/>{escape(str(r.get('ticker','-')))} · {escape(str(r.get('market','-')))}<br/>"
                f"Score {_fmt(r.get('investment_score',0))} · Modell {_fmt(profile.get('model_confidence', r.get('confidence_score',0)))} %<br/>"
                f"Markedsdata {_fmt(market_coverage)} % · Dokumentasjon {_fmt(documentation_coverage)} %<br/>"
                f"Beslutning {_fmt(profile.get('decision_confidence', r.get('confidence_score',0)))} % · Risiko {format_risk(r.get('risk_score',0))} · {weight_text}<br/>"
                f"<b>Driver:</b> {escape(evidence['drivers'])}<br/><b>Forbehold:</b> {escape(evidence['cautions'])}<br/>"
                f"<b>Handling:</b> {escape(evidence['action'])}", styles["Small"])])
        if not medal_data:
            medal_data = [[Paragraph("Ingen reelle kjøpsanbefalinger bestod alle beslutningsporter i denne kjøringen.", styles["Small"])]]
        medal_table = Table([medal_data], colWidths=[168*mm / max(1, len(medal_data))]*len(medal_data))
        medal_styles = [("BOX", (0,0), (-1,-1), .8, colors.grey), ("INNERGRID", (0,0), (-1,-1), .35, colors.lightgrey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]
        card_color = "#EAF2F8"
        for card_index in range(len(medal_data)):
            medal_styles.append(("BACKGROUND", (card_index,0), (card_index,-1), colors.HexColor(card_color)))
        medal_table.setStyle(TableStyle(medal_styles))
        evidence_rows = [["Ticker", "Insiderbevis", "Nyhetsbevis", "Plasseringsbevis"]]
        for idx, candidate in enumerate(medal_candidates):
            evidence = _candidate_evidence(candidate, medal_candidates[idx + 1] if idx + 1 < len(medal_candidates) else None)
            evidence_rows.append([
                candidate.get("ticker"), _p(evidence["insider"]), _p(evidence["news"]),
                _p(_loc("; ".join(x for x in [evidence["drivers"], evidence["gap"], evidence["cautions"]] if x))),
            ])
        evidence_table = Table(evidence_rows, repeatRows=1, colWidths=[18*mm, 51*mm, 51*mm, 54*mm])
        evidence_table.setStyle(_table_style(6.2, padding=2))
        ranking_explanation = build_ranking_explanation(run)
        ranking_rows = [["Rangeringstype", "Hva betyr den?"]] + [[item.get("name"), _p(item.get("description"), "Tiny")] for item in ranking_explanation.get("ranking_types") or []]
        ranking_table = Table(ranking_rows, repeatRows=1, colWidths=[48*mm, 118*mm])
        ranking_table.setStyle(_table_style(6.4, padding=2))
        ranking_note = ranking_explanation.get("note") or shortlist_note
        story += [Paragraph(shortlist_heading, styles["Section"]), medal_table,
                  Paragraph("Slik leses rangeringene", styles["Subsection"]), ranking_table,
                  Paragraph(escape(_norwegian_decimal_text(_loc(ranking_note))), styles["BodyCompact"]),
                  Paragraph("Konkret beslutningsbevis for den viste listen", styles["Subsection"]), evidence_table]
        # v19.0.6: the three leading candidates receive auditable evidence
        # pages.  Long tables may naturally continue on a following page.
        coverage_labels = {
            "AVAILABLE": "Data funnet", "MISSING": "Kontrollert – ingen hendelser funnet",
            "CHECKED_NO_EVENTS": "Kontrollert – ingen hendelser funnet",
            "SECONDARY_FACTS_FOUND": "Sekundære fakta – primærkilde ikke verifisert",
            "DISCOVERY_ONLY": "Kilder funnet – ikke strukturert/verifisert",
            "NOT_CONFIGURED": "Kilde ikke tilgjengelig", "UNAVAILABLE": "Kilde ikke tilgjengelig",
            "ERROR": "Kildefeil", "NOT_SEARCHED": "Ikke søkt", "STALE": "Foreldede data",
            "PARTIAL_SOURCE_FAILURE": "Delvis kildefeil", "RATE_LIMITED": "Kilde midlertidig begrenset",
            "DAILY_QUOTA_EXCEEDED": "Døgnbudsjett brukt", "SOURCE_ERROR": "Kildefeil",
        }
        for idx, candidate in enumerate(medal_candidates):
            candidate_ticker = escape(str(candidate.get("ticker") or "-"))
            raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
            insider = raw.get("insider_intelligence") if isinstance(raw.get("insider_intelligence"), Mapping) else {}
            news = raw.get("news_intelligence") if isinstance(raw.get("news_intelligence"), Mapping) else {}
            evidence = _candidate_evidence(candidate, medal_candidates[idx + 1] if idx + 1 < len(medal_candidates) else None)
            story += [PageBreak(), Paragraph(
                f"KANDIDAT {idx + 1}: {candidate_ticker} - detaljert investeringsanalyse",
                styles["ReportTitle"],
            )]
            decision = str(candidate.get("autonomy_outcome_code") or candidate.get("portfolio_action") or "REVIEW").upper()
            decision_label_text = str(candidate.get("autonomy_outcome_label") or _status_label(decision))
            decision_badge = Table([[Paragraph(f"<b>{escape(decision_label_text)}</b>", styles["Small"])]], colWidths=[70*mm])
            decision_badge.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor(decision_color(decision))),
                ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor(decision_text_color(decision))),
                ("BOX", (0,0), (-1,-1), .45, grid),
                ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
                ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ]))
            review_reasons = _candidate_review_reasons(candidate)
            ranking_sentence = _clean_sentence(
                f"Kandidaten er prioritet {idx + 1} fordi {_loc(evidence['drivers'])}. "
                + (f"{_loc(evidence['gap'])}. " if str(evidence.get('gap') or '').strip() else "")
            )
            story += [decision_badge, Paragraph(
                f"<b>AI-konklusjon:</b> {escape(ranking_sentence)} <b>Autonomiutfall:</b> {escape(decision_label_text)}. "
                f"<b>Forbehold:</b> {escape(_clean_sentence(_loc(evidence['cautions'])))}.",
                styles["BodyCompact"],
            ), Paragraph("<b>Hvorfor dette utfallet:</b> " + escape(_clean_sentence(_loc("; ".join(review_reasons)))), styles["BodyCompact"])]
            manual_tasks = [row for row in candidate.get("manual_tasks") or [] if isinstance(row, Mapping)]
            if manual_tasks:
                task_rows = [["Hva bør undersøkes", "Hvorfor", "Programmet forsøkte", "Hvorfor det stoppet", "Foreslått kilde", "Beslutningseffekt"]]
                for task in manual_tasks:
                    task_rows.append([
                        _p(task.get("title")), _p(task.get("why")), _p(task.get("program_attempts")),
                        _p(task.get("failure_reason")), _p(task.get("suggested_source")), _p(task.get("decision_impact")),
                    ])
                task_table = Table(task_rows, repeatRows=1, colWidths=[31*mm, 31*mm, 31*mm, 31*mm, 24*mm, 30*mm])
                task_table.setStyle(_table_style(5.7, padding=1.8))
                story += [Paragraph("Konkret manuell undersøkelse", styles["Subsection"]), task_table]
            else:
                story += [Paragraph("Ingen manuell handling nødvendig", styles["Subsection"]),
                          Paragraph(escape(str(candidate.get("automatic_next_action") or "Programmet følger kandidaten automatisk.")), styles["Small"])]
            readiness = candidate.get("decision_readiness") if isinstance(candidate.get("decision_readiness"), Mapping) else {}
            readiness_table = Table([
                ["Beslutningsgrunnlag", _status_label(readiness.get("status") or "-"), "Rå rangering", candidate.get("raw_rank") or candidate.get("rank") or "-"],
                ["Markedsdata", _status_label(readiness.get("market_data") or "-"), "Evidens-/datarangering", candidate.get("evidence_ready_rank") or "-"],
                ["Nyheter", _status_label(readiness.get("news") or "-"), "Innsider", _status_label(readiness.get("insider") or "-")],
                ["Kildekonflikter", readiness.get("conflicts", 0), "Evidensport", _status_label(readiness.get("evidence_gate_action") or readiness.get("allowed_action") or "-")],
                ["Analytisk vurdering", _p(candidate.get("analytical_recommendation_label") or "Ikke målt i eldre rapport"), "Handelsstatus", _p(candidate.get("trade_execution_label") or "Ikke målt i eldre rapport")],
                ["Autonomiutfall", _p(candidate.get("autonomy_outcome_label") or decision_label_text), "Automatisk neste steg", _p(candidate.get("automatic_next_action") or "-")],
            ], colWidths=[34*mm, 50*mm, 42*mm, 42*mm])
            readiness_table.setStyle(_table_style(6.4, header=False, padding=2.2))
            story += [Paragraph("Beslutningsstempel", styles["Section"]), readiness_table]
            profile = candidate.get("confidence_profile") if isinstance(candidate.get("confidence_profile"), Mapping) else {}
            confidence = round(float(candidate.get("decision_confidence") or profile.get("decision_confidence") or 0), 1)
            confidence_label = "Høy" if confidence >= 80 else "Middels" if confidence >= 60 else "Lav"
            confidence_factors = []
            if float(profile.get("documentation_coverage") or profile.get("data_coverage") or 0) < 70:
                confidence_factors.append("begrenset dokumentasjonsdekning")
            if float(profile.get("market_data_coverage") or 0) < 70:
                confidence_factors.append("begrenset markedsdatadekning")
            if str(readiness.get("news") or "").upper() not in {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}:
                confidence_factors.append("nyhetskontroll ikke endelig")
            if str(readiness.get("insider") or "").upper() not in {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}:
                confidence_factors.append("insiderkontroll ikke endelig")
            ticker_gaps = critical_gaps_by_ticker.get(str(candidate.get("ticker") or "").upper(), [])
            for gap_row in ticker_gaps:
                area = str(gap_row.get("area") or "dokumentasjon")
                status = _status_label(gap_row.get("status") or "UAVKLART").lower()
                confidence_factors.append(f"kritisk evidensgap i {area}: {status}")
            confidence_reason = "; ".join(dict.fromkeys(confidence_factors)) or "verifisert datagrunnlag uten registrerte kritiske evidenshull"
            next_event = raw.get("next_event") or raw.get("next_expected_event") or raw.get("earnings_date") or "Ingen bekreftet kommende hendelse i datasettet"
            change_conditions = []
            if float(candidate.get("investment_score") or 0) < 78:
                change_conditions.append("samlet score når kjøpsterskelen")
            if str(readiness.get("insider") or "").upper() not in {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}:
                change_conditions.append("insiderkontrollen fullføres")
            if str(readiness.get("news") or "").upper() not in {"VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}:
                change_conditions.append("nyhetskontrollen fullføres")
            if int(readiness.get("conflicts") or 0):
                change_conditions.append("kildekonflikter avklares")
            if not change_conditions:
                change_conditions.append("risiko- og porteføljeporten godkjenner kandidaten")
            insight_table = Table([
                ["Beslutningskonfidens", f"{_fmt(confidence, 1)} % ({confidence_label})", "Neste forventede hendelse", _p(_short(next_event, 120))],
                ["Konfidensforklaring", _p(confidence_reason), "Endring siden forrige", _p(candidate.get("score_change_reason") or candidate.get("change_reason") or "Ingen dokumentert vesentlig endring")],
                ["Hva kan endre beslutningen?", _p("; ".join(change_conditions)), "Dokumentasjonsdekning", f"{_fmt(profile.get('documentation_coverage', profile.get('data_coverage', 0)))} %"],
            ], colWidths=[34*mm, 50*mm, 42*mm, 42*mm])
            insight_table.setStyle(_table_style(6.3, header=False, padding=2.2))
            story += [Paragraph("Beslutningsforklaring og neste utløsere", styles["Subsection"]), insight_table]
            formula = raw.get("score_formula") if isinstance(raw.get("score_formula"), Mapping) else {}
            weights = formula.get("weights") if isinstance(formula.get("weights"), Mapping) else {}
            contributions = formula.get("weighted_contributions") if isinstance(formula.get("weighted_contributions"), Mapping) else {}
            score_parts = formula.get("parts") if isinstance(formula.get("parts"), Mapping) else {}
            contribution_semantics = formula.get("contribution_semantics") if isinstance(formula.get("contribution_semantics"), Mapping) else {}
            component_rows = [[f"{candidate.get('ticker') or '-'} · Analysemodul", "Råscore", "Vekt", "Bidrag"]]
            component_defaults = {
                "discovery": candidate.get("discovery_score"), "fundamental": candidate.get("fundamental_score"),
                "research": candidate.get("research_score"), "validation": candidate.get("validation_score"),
                "portfolio_fit": candidate.get("portfolio_fit_score"), "insider": raw.get("insider_score"),
                "news": raw.get("news_score"), "risk": candidate.get("risk_score"),
            }
            for key in sorted(set(component_defaults) | set(score_parts) | set(weights) | set(contributions)):
                module_label = component_label(key.replace("_", " ").title())
                contribution_value: Any = _fmt(contributions.get(key))
                semantic = contribution_semantics.get(key) if isinstance(contribution_semantics.get(key), Mapping) else {}
                if key in {"insider", "news"} and semantic.get("evidence_backed") is False:
                    module_label += " (modellbaseline)"
                    contribution_value = _p(f"{_fmt(contributions.get(key))} - ikke dokumentert evidens")
                component_rows.append([
                    _p(module_label), _fmt(score_parts.get(key, component_defaults.get(key))),
                    _fmt(weights.get(key)), contribution_value,
                ])
            component_table = Table(component_rows, repeatRows=1, colWidths=[58*mm, 36*mm, 36*mm, 36*mm])
            component_table.setStyle(_table_style(6.8, padding=2.2))
            story += [Paragraph("Poengberegning, vekter og modulbidrag", styles["Section"]), component_table]

            technical = raw.get("technical") if isinstance(raw.get("technical"), Mapping) else {}
            fundamental = raw.get("fundamental") if isinstance(raw.get("fundamental"), Mapping) else {}
            if not technical:
                technical = {k: raw.get(k) for k in ("rsi", "momentum", "trend", "ma20", "ma50", "volatility") if raw.get(k) is not None}
            if not fundamental:
                fundamental = {k: raw.get(k) for k in ("pe", "forward_pe", "pb", "roe", "growth", "debt", "dividend_yield") if raw.get(k) is not None}
            metric_rows = [[f"{candidate.get('ticker') or '-'} · Tekniske nøkkeltall / signaler", "Verdi", "Fundamentale nøkkeltall", "Verdi"]]
            tech_items, fund_items = list(technical.items()), list(fundamental.items())
            for pos in range(max(1, len(tech_items), len(fund_items))):
                t = tech_items[pos] if pos < len(tech_items) else ("Ingen registrerte tekniske detaljdata", "-")
                f = fund_items[pos] if pos < len(fund_items) else ("Ingen registrerte fundamentaldetaljer", "-")
                metric_rows.append([_p(t[0]), _p(_metric_value(t[0], t[1])), _p(f[0]), _p(_metric_value(f[0], f[1]))])
            metric_table = Table(metric_rows, repeatRows=1, colWidths=[50*mm, 34*mm, 50*mm, 34*mm])
            metric_table.setStyle(_table_style(6.5, padding=2))
            story += [Paragraph(f"{candidate_ticker} - teknisk og fundamental dokumentasjon", styles["Section"]), metric_table]

            insider_code = str(insider.get("coverage") or "NOT_SEARCHED").upper()
            if insider_code == "AVAILABLE" and not list(insider.get("evidence") or []):
                insider_code = "CHECKED_NO_EVENTS"
            insider_status = coverage_labels.get(insider_code, insider_code)
            insider_rows = [[f"{candidate.get('ticker') or '-'} · Navn / rolle", "Handling", "Dato", "Antall", "Verdi", "Kilde / dokument"]]
            for tx in list(insider.get("evidence") or [])[:20]:
                role_labels = {
                    "DIRECTOR": "Direktør", "OFFICER": "Ledende ansatt",
                    "CHIEF EXECUTIVE": "Administrerende direktør", "CHIEF": "Leder",
                }
                role_raw = str(tx.get("role") or "Ukjent rolle")
                role_display = role_labels.get(role_raw.upper(), role_raw)
                verification_display = label_for(tx.get("verification") or "UNVERIFIED")
                insider_rows.append([
                    _rawp(f"{tx.get('insider','Ukjent')} / {role_display}"),
                    _decision_label(tx.get("type") or "-").upper(), _short_date(tx.get("date") or "-"), _fmt(tx.get("shares")),
                    format_whole_currency(tx.get("value", 0), market_currency(candidate.get("market"), candidate.get("ticker"), insider.get("currency"))),
                    _rawp(_short(
                        f"{label_for(tx.get('source') or insider.get('official_source') or insider.get('source') or 'Ukjent')}; "
                        f"{verification_display}; {tx.get('document_id') or '-'}; "
                        f"{tx.get('source_url') or '-'}", 220
                    )),
                ])
            if len(insider_rows) == 1:
                insider_rows.append([_p(insider_status), "-", "-", "-", "-", _p(insider.get("reason") or "Ingen dokumentasjon")])
            insider_table = Table(insider_rows, repeatRows=1, colWidths=[43*mm, 19*mm, 22*mm, 20*mm, 28*mm, 36*mm])
            insider_table.setStyle(_table_style(6.2, padding=1.8))
            story += [Paragraph(f"{candidate_ticker} - insiderbevis - {escape(insider_status)}", styles["Section"]), insider_table]

            news_code = str(news.get("coverage") or "NOT_SEARCHED").upper()
            if news_code == "AVAILABLE" and not list(news.get("events") or []):
                news_code = "CHECKED_NO_EVENTS"
            news_status = coverage_labels.get(news_code, news_code)
            news_rows_detail = [[f"{candidate.get('ticker') or '-'} · Overskrift", "Dato", "Kilde", "Tema", "Sentiment", "Påvirkning"]]
            for article in list(news.get("events") or [])[:12]:
                news_rows_detail.append([
                    _rawp(_short(article.get("title"), 130)), _p(_short_datetime(article.get("published_at") or article.get("date") or "-")),
                    _rawp(_short(article.get("source") or article.get("publisher") or "-", 55)), _p(translate_list(article.get("topics") or news.get("topics") or [])),
                    _fmt(article.get("sentiment_score")), label_for(article.get("impact") or "-"),
                ])
            if len(news_rows_detail) == 1:
                news_rows_detail.append([_p(news_status), "-", _rawp(news.get("source") or "-"), "-", "-", _p(news.get("summary") or "Ingen dokumentasjon")])
            news_table = Table(news_rows_detail, repeatRows=1, colWidths=[52*mm, 31*mm, 31*mm, 20*mm, 16*mm, 18*mm])
            news_table.setStyle(_table_style(6.1, padding=1.8))
            story += [Paragraph(f"{candidate_ticker} - nyhetsbevis - {escape(news_status)}", styles["Section"]), news_table]

            provenance_rows = [[f"{candidate.get('ticker') or '-'} · Type", "Fakta-ID / dokument", "Verifikasjon", "Publisert", "Hentet", "Direkte kilde"]]
            for tx in list(insider.get("evidence") or [])[:20]:
                provenance_rows.append([
                    "Insider", _rawp(tx.get("document_id") or tx.get("fact_id") or "-"),
                    _p(label_for(tx.get("verification") or "-")), _p(_short_date(tx.get("published_at") or tx.get("date") or "-")),
                    _p(_short_datetime(tx.get("retrieved_at") or insider.get("fetched_at") or "-")),
                    _rawp(_short(tx.get("source_url") or "-", 190)),
                ])
            for article in list(news.get("events") or [])[:12]:
                provenance_rows.append([
                    "Nyhet", _rawp(article.get("fact_id") or "-"), _p(label_for(article.get("verification") or "-")),
                    _p(_short_datetime(article.get("published_at") or article.get("date") or "-")),
                    _p(_short_datetime(article.get("retrieved_at") or news.get("fetched_at") or "-")),
                    _rawp(_short(article.get("source_url") or article.get("url") or "-", 190)),
                ])
            if len(provenance_rows) == 1:
                provenance_rows.append(["-", "Ingen verifiserte fakta", "-", "-", "-", "-"])
            provenance_table = Table(provenance_rows, repeatRows=1, colWidths=[16*mm, 31*mm, 24*mm, 25*mm, 25*mm, 47*mm])
            provenance_table.setStyle(_table_style(5.9, padding=1.6))
            source_log_table = Table(_source_log_rows(insider, news), repeatRows=1,
                                     colWidths=[15*mm, 29*mm, 13*mm, 30*mm, 12*mm, 27*mm, 42*mm])
            source_log_table.setStyle(_table_style(5.8, padding=1.6))
            confidence_table = Table([
                ["Konfidens før evidens", "Straff", "Tak", "Endelig", "Evidensport", "Manuell kontroll"],
                [_fmt(candidate.get("confidence_before_evidence_policy")), _fmt(candidate.get("evidence_confidence_penalty")),
                 _fmt(candidate.get("evidence_confidence_cap")), _fmt(candidate.get("confidence_score")),
                 _status_label("MANUAL_REVIEW" if candidate.get("manual_review_required") else ("PASS" if candidate.get("evidence_data_ready") else "AUTO_CLOSED")), "Ja" if candidate.get("evidence_review_required") else "Nei"],
            ], colWidths=[29*mm, 22*mm, 22*mm, 22*mm, 39*mm, 34*mm])
            confidence_table.setStyle(_table_style(6.2, padding=2))
            profile = candidate.get("confidence_profile") if isinstance(candidate.get("confidence_profile"), Mapping) else {}
            profile_table = Table([
                ["Modell", "Markedsdata", "Dokumentasjon", "Kilder", "Beslutning", "Endrer handelsregler"],
                [
                    _fmt(profile.get("model_confidence")),
                    _fmt(profile.get("market_data_coverage", candidate.get("data_quality"))),
                    _fmt(profile.get("documentation_coverage", profile.get("data_coverage"))),
                    _fmt(profile.get("calibrated_confidence", profile.get("source_confidence"))),
                    _fmt(profile.get("decision_confidence")),
                    "Nei",
                ],
            ], colWidths=[24*mm, 26*mm, 29*mm, 25*mm, 34*mm, 30*mm])
            profile_table.setStyle(_table_style(6.2, padding=2))
            passport = candidate.get("evidence_passport") if isinstance(candidate.get("evidence_passport"), Mapping) else {}
            passport_rows = [[f"{candidate.get('ticker') or '-'} · Område", "Status", "Fakta", "Kilder", "Påvirket rangering", "Bidrag"]]
            verified_passport_statuses = {"AVAILABLE", "VERIFIED_FACTS_FOUND", "CHECKED_NO_EVENTS"}
            for area, area_data in (passport.get("areas") or {}).items():
                area_status = str(area_data.get("status") or "-").upper()
                contribution = area_data.get("ranking_contribution")
                evidence_backed = area_status in verified_passport_statuses
                affected_text = "Ja" if area_data.get("affected_ranking") and evidence_backed else ("Modellbaseline" if contribution and not evidence_backed else "Nei")
                contribution_text: Any = _fmt(contribution)
                if contribution and not evidence_backed:
                    contribution_text = _p(f"{_fmt(contribution)} - ikke evidens")
                passport_rows.append([
                    _p(_loc(str(area).title())), _p(_status_label(area_status)), area_data.get("fact_count", 0),
                    area_data.get("source_count", 0), _p(affected_text), contribution_text,
                ])
            passport_table = Table(passport_rows, repeatRows=1, colWidths=[29*mm, 46*mm, 20*mm, 20*mm, 34*mm, 19*mm])
            passport_table.setStyle(_table_style(6.1, padding=1.8))
            story += [
                Paragraph(f"{candidate_ticker} - faktaproveniens", styles["Section"]),
                provenance_table,
                Paragraph(f"{candidate_ticker} - kildedekningslogg", styles["Section"]),
                source_log_table,
                Paragraph(f"{candidate_ticker} - konfidenskalibrering og evidensport", styles["Section"]),
                confidence_table,
                Paragraph(f"{candidate_ticker} - modell-, data- og beslutningskonfidens", styles["Subsection"]),
                profile_table,
                Paragraph(escape(_loc(str(profile.get("explanation") or ""))), styles["Small"]),
                Paragraph(
                    "Bevispass · kontrollsum " + escape(str(passport.get("fingerprint") or "-")[:24]),
                    styles["Subsection"],
                ),
                passport_table,
            ]

            transparency = candidate.get("analysis_transparency") if isinstance(candidate.get("analysis_transparency"), Mapping) else {}
            if not transparency:
                try:
                    from analysis_transparency import build_candidate_transparency
                    transparency = build_candidate_transparency(candidate)
                except Exception:
                    transparency = {}
            if transparency:
                ledger = transparency.get("claim_ledger") if isinstance(transparency.get("claim_ledger"), Mapping) else {}
                conflict_register = transparency.get("conflict_register") if isinstance(transparency.get("conflict_register"), Mapping) else {}
                confidence_detail = transparency.get("confidence_breakdown") if isinstance(transparency.get("confidence_breakdown"), Mapping) else {}
                evidence_matrix = list(transparency.get("evidence_matrix") or [])
                transparency_rows = [["Dokumenterte fakta", "Forkastet", "Uavhengige utgivere", "Primærkilde forsøkt", "Ingen funn", "Kildefeil"]]
                transparency_rows.append([
                    ledger.get("claim_count", 0), ledger.get("rejected_claim_count", 0),
                    ledger.get("independent_source_count", 0),
                    len(ledger.get("primary_source_attempted_areas") or []),
                    ledger.get("checked_no_findings", 0), ledger.get("failed_attempts", 0),
                ])
                transparency_table = Table(transparency_rows, colWidths=[28*mm, 23*mm, 33*mm, 31*mm, 24*mm, 25*mm])
                transparency_table.setStyle(_table_style(6.0, padding=1.8))
                matrix_rows = [["Område", "Statusklasse", "Fakta", "Kilder", "Primær forsøkt", "Primærfakta", "Rangeringsbidrag"]]
                for item in evidence_matrix:
                    matrix_rows.append([
                        _p(_loc(str(item.get("area") or "-").title())), _p(str(item.get("status_class") or "-")),
                        item.get("fact_count", 0), item.get("source_count", 0),
                        "Ja" if item.get("primary_attempted") else "Nei",
                        "Ja" if item.get("primary_fact_present") else "Nei",
                        _fmt(item.get("ranking_contribution")),
                    ])
                matrix_table = Table(matrix_rows, repeatRows=1, colWidths=[25*mm, 34*mm, 16*mm, 16*mm, 25*mm, 24*mm, 28*mm])
                matrix_table.setStyle(_table_style(5.8, padding=1.5))
                deductions = list(confidence_detail.get("deductions") or [])
                deduction_text = " • ".join(str(item.get("reason") or "") for item in deductions if isinstance(item, Mapping)) or "Ingen særskilte evidenstrekk."
                story += [
                    Paragraph(f"{candidate_ticker} - transparens og evidens", styles["Section"]),
                    transparency_table,
                    Paragraph(
                        f"<b>Beslutningsstyrke:</b> {_fmt(confidence_detail.get('transparent_decision_confidence'))}/100. "
                        f"<b>Konflikter:</b> {int(conflict_register.get('count') or 0)}. "
                        "Scoren er ikke sannsynlighet for kursgevinst.",
                        styles["Small"],
                    ),
                    Paragraph(f"<b>Trekk og begrensninger:</b> {escape(_loc(deduction_text))}", styles["Small"]),
                    Paragraph(f"{candidate_ticker} - evidensmatrise per analyseområde", styles["Subsection"]),
                    matrix_table,
                ]

            discovery_detail = raw.get("discovery_evidence") or raw.get("ai_discovery") or candidate.get("discovery_reason") or "Ingen separat Discovery-dokumentasjon registrert."
            backtest_detail = raw.get("backtest") or raw.get("validation") or candidate.get("validation_reason") or "Ingen detaljert backtest registrert."
            positives = " • ".join(str(x) for x in (candidate.get("positives") or [])) or "Ingen særskilte positive drivere registrert."
            risks = " • ".join(str(x) for x in (candidate.get("risks") or [])) or "Ingen særskilte risikofaktorer registrert."
            story += [
                Paragraph(
                    f"{escape(str(candidate.get('ticker') or '-'))} – AI-funn, historikk og porteføljetilpasning",
                    styles["Section"],
                ),
                Paragraph(f"<b>AI-funn:</b> {escape(_loc(_short(discovery_detail, 650)))}", styles["Small"]),
                Paragraph(f"<b>Historisk test / treffsikkerhet:</b> {escape(_loc(_short(backtest_detail, 650)))}", styles["Small"]),
                Paragraph(
                    f"<b>Porteføljetilpasning:</b> score {_fmt(candidate.get('portfolio_fit_score'))}; "
                    f"foreslått vekt {_fmt(candidate.get('proposed_position_pct'))} %. "
                    f"<b>Strategier:</b> {escape(translate_list(candidate.get('strategy_matches') or []))}.",
                    styles["Small"],
                ),
                Paragraph(f"<b>Positive drivere:</b> {escape(_loc(positives))}", styles["Small"]),
                Paragraph(f"<b>Risikofaktorer og manglende data:</b> {escape(_loc(risks))}; {escape(_clean_sentence(_loc(evidence['cautions'])))}", styles["Small"]),
            ]
        # RC16.9: Never rank rejected/watched/manual candidates in the investor report.
        # The only public ranking is the buy-only candidate_decisions section.
        story += [Paragraph("Analysegrunnlag – ikke kandidatrangering", styles["Subsection"]),
                  Paragraph("Ikke-kjøpsgodkjente aksjer vises kun kort i kontrollvedlegget. Tekniske scorer brukes internt og er ikke en offentlig rangering.", styles["Small"])]
        strategy_data = [["Ticker", "Bransje", "Parallelle strategitreff", "Forklaring"]]
        for candidate in candidates:
            analysis_layer = candidate.get("analysis_ranking") or {}
            matches = candidate.get("strategy_matches") or analysis_layer.get("matches") or []
            strategy_data.append([
                _p(candidate.get("ticker")), _p(sector_label(analysis_layer.get("sector") or candidate.get("sector"))),
                _p(translate_list(matches) if matches else "Ingen over terskel"),
                _p("Separate scorer; ingen ny universalscore" if analysis_layer else "Eldre kandidatformat"),
            ])
        strategy_table = Table(strategy_data, repeatRows=1, colWidths=[22*mm, 34*mm, 68*mm, 50*mm])
        strategy_table.setStyle(_table_style(6.3, padding=2))
        story += [Paragraph("Parallelle strategier", styles["Subsection"]),
                  Paragraph("Kandidaten kan passe flere strategier samtidig. Hver score bruker bransjereferanser, råfelt, komponentbidrag og egen datadekning.", styles["Small"]),
                  strategy_table]
    candidate_lookup = {str(row.get("ticker") or "").upper(): row for row in candidates}
    proposal_rows = [candidate_lookup.get(str(row.get("ticker") or "").upper(), row)
                     for row in (run.get("proposals") or []) if isinstance(row, Mapping)]
    for p in proposal_rows:
        raw = p.get("raw") or {}; insider = raw.get("insider_intelligence") or {}; news = raw.get("news_intelligence") or {}
        score_data = [
            ["AI-funn", "Fundamentalt", "Analyse", "Historisk test", "Portefølje", "Innsider", "Nyheter", "Risiko (0-100)"],
            [_fmt(p.get("discovery_score")), _fmt(p.get("fundamental_score")), _fmt(p.get("research_score")), _fmt(p.get("validation_score")), _fmt(p.get("portfolio_fit_score")), _fmt(raw.get("insider_score", 50)), _fmt(raw.get("news_score", 50)), format_risk(p.get("risk_score"))],
        ]
        score_table = Table(score_data, colWidths=[23*mm]*8)
        score_table.setStyle(_table_style(6.5, padding=2))
        positives = " • ".join(str(x) for x in (p.get("positives") or [])) or "Ingen registrerte positive drivere."
        risks = " • ".join(str(x) for x in (p.get("risks") or [])) or "Ingen registrerte risikopunkter."
        action = str(p.get("autonomy_outcome_code") or p.get("portfolio_action") or "REVIEW").upper()
        proposal = [
            Paragraph(f"{escape(str(p.get('ticker') or '-'))} – foreløpig modellkandidat (ikke handelsforslag)", styles["Section"]),
            Paragraph(f"<b>Status:</b> {escape(str(p.get('autonomy_outcome_label') or _loc(str(p.get('status') or '-'))))} &nbsp; | &nbsp; <b>Investeringsscore:</b> {escape(str(_fmt(p.get('investment_score'))))} / 100 &nbsp; | &nbsp; <b>Beslutningskonfidens:</b> {escape(str(_fmt(p.get('decision_confidence') or _mapping(p.get('confidence_profile')).get('decision_confidence'))))} / 100 &nbsp; | &nbsp; <b>Scoretrend:</b> {escape(str(p.get('score_trend') or p.get('trend', 'NY')))}", styles["BodyCompact"]),
            score_table,
            Paragraph(f"<b>Innsider:</b> {escape(_loc(str(raw.get('insider_signal', 'INGEN DATA'))))} · score {escape(str(_fmt(raw.get('insider_score', 50))))} / 100 · nettoverdi {escape(format_whole_currency(insider.get('net_value', 0), market_currency(p.get('market'), p.get('ticker'), insider.get('currency'))))}", styles["Small"]),
            Paragraph(f"<b>Nyheter:</b> {escape(_loc(str(raw.get('news_sentiment', 'INGEN DATA'))))} · score {escape(str(_fmt(raw.get('news_score', 50))))} / 100 · {escape(_loc(str(news.get('summary') or 'Ingen oppsummering.')))}", styles["Small"]),
            Paragraph(f"<b>Positive drivere:</b> {escape(_loc(positives))}", styles["Small"]),
            Paragraph(f"<b>Risiko:</b> {escape(_loc(risks))}", styles["Small"]),
            Paragraph(f"<b>Strategitreff:</b> {escape(translate_list(p.get('strategy_matches') or str(p.get('strategy_match') or '-')))} · <b>Autonomiutfall:</b> {escape(str(p.get('autonomy_outcome_label') or _decision_label(action)))}" + (f" · <b>teoretisk vekt:</b> {escape(str(p.get('proposed_position_pct', 0)))} %" if action == "BUY" else " · Ingen kjøpsvekt før godkjenning"), styles["Small"]),
        ]
        story += proposal + [Spacer(1, 1.2*mm)]
    portfolio_proposal = run.get("portfolio_proposal") or {}
    portfolio_layer = run.get("portfolio_decisions") or {}
    if portfolio_layer:
        context = portfolio_layer.get("portfolio_context") or {}; actions = portfolio_layer.get("actions") or {}
        decision_table = Table([
            [_p(_decision_label("BUY")), actions.get("BUY", 0), _p(_decision_label("HOLD")), actions.get("HOLD", 0), _p(_decision_label("SELL")), actions.get("SELL", 0), _p(_decision_label("SKIP")), actions.get("SKIP", 0)],
            [_p("Foreløpig viderebehandling i porteføljelaget"), actions.get("REVIEW", 0), _p("Konkrete manuelle oppgaver"), int(reduction.get("manual_task_count") or 0), _p("Overvåkes automatisk"), int(reduction.get("automatic_watch") or 0), _p("Automatisk avvist"), int(reduction.get("automatic_rejected") or 0)],
            [_p("Posisjoner"), context.get("position_count", 0), _p("Kontant %"), _fmt(context.get("cash_pct", 0)), _p("Effektive posisjoner"), _fmt(context.get("effective_positions", 0)), _p("Porteføljevurdert"), "JA"],
        ], colWidths=[26*mm, 16*mm]*4)
        decision_table.setStyle(_table_style(6.5, header=False, padding=2))
        story += [Paragraph("Autonomis primære simulerte portefølje og beslutningslag", styles["Section"]), decision_table,
                  Paragraph(escape(_loc(str(portfolio_layer.get("approval_rule") or "Ingen kjøpskandidat vurderes isolert fra eksisterende portefølje"))), styles["Small"])]
        request = portfolio_layer.get("discovery_request") or {}
        if request:
            story += [Paragraph("Porteføljebehov har opprettet Discovery-oppdrag " + escape(str(request.get("request_id"))) + ".", styles["Small"])]
    funnel = run.get("decision_funnel") or {}
    if funnel:
        rejection_names = {
            "portfolio_active": "Portefølje ikke aktiv",
            "autonomy_outcome_buy": "Ikke godkjent som kjøpskandidat av Autonomi",
            "portfolio_layer_buy": "Porteføljelaget ga ikke kjøpshandling",
            "valid_for_decision": "Markedsdata ikke beslutningsgyldige",
            "evidence_valid_for_decision": "Evidens ikke beslutningsgyldig",
            "final_decision_ready": "Ikke endelig kjøpsklar",
            "technical_timing": "Teknisk timing gir vent",
            "score": "Kjøpsscore", "data_quality": "Datakvalitet", "risk": "Risiko",
            "price": "Markedspris", "position_capacity": "Posisjonsgrense",
            "addition_policy": "Tilleggskjøp ikke tillatt",
        }
        counts = dict(funnel.get("rejection_counts") or {})
        analytical_counts = dict(funnel.get("analytical_rejection_counts") or {})
        execution_counts = dict(funnel.get("execution_block_counts") or {})
        funnel_rows = [row for row in (funnel.get("candidates") or []) if isinstance(row, Mapping)]
        analytical_keys = {"mission_eligible", "valid_for_decision", "evidence_valid_for_decision", "technical_timing", "score", "data_quality", "risk", "price"}
        execution_keys = {"portfolio_active", "position_capacity", "addition_policy", "portfolio_layer_buy", "autonomy_outcome_buy"}
        if not analytical_counts:
            for row in funnel_rows:
                gates = row.get("analytical_gates") if isinstance(row.get("analytical_gates"), Mapping) else (row.get("gates") or {})
                for key, value in gates.items():
                    if key in analytical_keys and not value:
                        analytical_counts[key] = analytical_counts.get(key, 0) + 1
        if not execution_counts:
            for row in funnel_rows:
                gates = row.get("execution_gates") if isinstance(row.get("execution_gates"), Mapping) else (row.get("gates") or {})
                for key, value in gates.items():
                    if key in execution_keys and not value:
                        execution_counts[key] = execution_counts.get(key, 0) + 1
        analytical_buy_count = funnel.get("analytical_buy_recommendations")
        if analytical_buy_count is None:
            analytical_buy_count = sum(
                all(value for key, value in ((row.get("analytical_gates") or row.get("gates") or {}).items()) if key in analytical_keys)
                for row in funnel_rows
            )
        trade_executable_count = funnel.get("trade_executable", funnel.get("eligible", 0))
        portfolio_blocked_count = funnel.get("portfolio_blocked_buy_recommendations", 0)
        capacity_blocked_count = funnel.get("capacity_blocked_buy_recommendations", 0)
        funnel_summary = Table([
            ["Vurdert", funnel.get("evaluated", 0), "Analytisk kjøpssignal", analytical_buy_count,
             "Gjennomførbar handel", trade_executable_count, "Produksjonsterskel", _fmt(funnel.get("production_threshold", 78), 1)],
            ["Stoppet av porteføljelag", portfolio_blocked_count,
             "Stoppet av posisjonsgrense", capacity_blocked_count,
             "Uten kjøpssignal", max(0, int(funnel.get("evaluated", 0)) - int(analytical_buy_count or 0)),
             "Portefølje", _p(funnel.get("portfolio_name") or "Autonomis primære simulerte portefølje", "Tiny")],
        ], colWidths=[29*mm, 12*mm, 33*mm, 12*mm, 31*mm, 12*mm, 25*mm, 30*mm])
        funnel_summary.setStyle(_table_style(5.7, header=False, padding=1.6))
        analytical_text = "; ".join(f"{rejection_names.get(key, key)}: {value}" for key, value in analytical_counts.items()) or "Ingen analytiske avvisninger"
        execution_text = "; ".join(f"{rejection_names.get(key, key)}: {value}" for key, value in execution_counts.items()) or "Ingen gjennomføringsblokker"
        legacy_text = "; ".join(f"{rejection_names.get(key, key)}: {value}" for key, value in counts.items()) or "Ingen avvisninger"
        story += [Paragraph("Beslutningstrakt og kjøpsvurdering – analyse separat fra handel", styles["Section"]), funnel_summary,
                  Paragraph(
                      "Et analytisk kjøpssignal er et modellresultat før evidens-, Autonomi- og porteføljekontroll. "
                      "Bare «gjennomførbar handel» er kjøpsgodkjent i denne rapporten.", styles["Small"],
                  ),
                  Paragraph("Analytiske krav: " + escape(analytical_text), styles["Small"]),
                  Paragraph("Gjennomføring i Autonomis simulerte portefølje: " + escape(execution_text), styles["Small"]),
                  Paragraph("Produksjonskjeden er uendret. Kompatibilitetsporter: " + escape(legacy_text), styles["Footer"])]
        near_rows = [["Ticker", "Score / terskel", "Analytisk vurdering", "Handelsstatus", "Hovedgrunn"]]
        for row in list(funnel.get("near_threshold") or [])[:10]:
            reason_values = row.get("analytical_reasons") or row.get("reasons") or []
            reason_text = "; ".join(_clean_legacy_portfolio_reason(value) for value in reason_values)
            near_rows.append([_p(row.get("ticker")), _p(f"{_fmt(row.get('score'))} / {_fmt(row.get('production_threshold'), 1)}"),
                              _p(row.get("analytical_recommendation_label") or "Ikke analytisk kjøpsanbefalt"),
                              _p(row.get("trade_execution_label") or _candidate_outcome_label(row.get("ticker"), row.get("portfolio_action"))),
                              _p(_short(reason_text, 180))])
        if len(near_rows) > 1:
            near_table = Table(near_rows, repeatRows=1, colWidths=[18*mm, 26*mm, 40*mm, 48*mm, 42*mm])
            near_table.setStyle(_table_style(5.8, padding=1.7))
            story += [Paragraph("Nærmest kjøpskravene", styles["Subsection"]), near_table]
        shadow_rows = [["Terskel", "Rolle", "Score bestått", "Analytisk bestått", "Alle produksjonsporter", "Prod. endret"]]
        for row in funnel.get("shadow_thresholds") or []:
            shadow_rows.append([_fmt(row.get("threshold"), 1), model_role_label(row.get("role")), row.get("score_qualified_count", 0),
                                row.get("analytical_eligible_count", 0), row.get("eligible_count", 0), "NEI"])
        shadow_table = Table(shadow_rows, repeatRows=1, colWidths=[20*mm, 30*mm, 30*mm, 32*mm, 42*mm, 20*mm])
        shadow_table.setStyle(_table_style(6.3, padding=2))
        story += [Paragraph("Skyggemodus – kjøpsterskel", styles["Subsection"]), shadow_table,
                  Paragraph("Tersklene 76, 74 og 72 er utfordrer-simuleringer. De kan ikke utløse kjøp eller endre produksjonsregelen uten eksplisitt godkjenning.", styles["Small"])]
        report_summary_v19143 = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
        story += [Paragraph(
            f"Kandidatavstemming: {len(candidates)} totalt | {int(report_summary_v19143.get('buy_candidates') or 0)} kjøpsgodkjent | "
            f"{int(report_summary_v19143.get('moderate_buy_recommendations') or 0)} moderat kjøpsanbefalt | "
            f"{int(report_summary_v19143.get('automatic_watch') or 0)} overvåkes | "
            f"{int(report_summary_v19143.get('manual_review') or 0)} undersøkes manuelt | "
            f"{int(report_summary_v19143.get('automatic_rejected') or 0)} avvist | "
            f"avstemt {int(report_summary_v19143.get('buy_candidates') or 0) + int(report_summary_v19143.get('moderate_buy_recommendations') or 0) + int(report_summary_v19143.get('automatic_watch') or 0) + int(report_summary_v19143.get('manual_review') or 0) + int(report_summary_v19143.get('automatic_rejected') or 0)} av {len(candidates)}",
            styles["Footer"],
        )]
        provenance = list(funnel.get("position_provenance") or [])
        if provenance:
            provenance_rows = [["Ticker", "Opprinnelse", "Kildekjøring", "Bevis"]]
            for row in provenance:
                provenance_rows.append([row.get("ticker"), _loc(row.get("origin")), row.get("source_run_id"), _loc(row.get("evidence"))])
            provenance_table = Table(provenance_rows, repeatRows=1, colWidths=[24*mm, 55*mm, 65*mm, 30*mm])
            provenance_table.setStyle(_table_style(6.3, padding=2))
            story += [Paragraph("Opprinnelse til åpne posisjoner", styles["Subsection"]), provenance_table]
    allocations = portfolio_proposal.get("allocations") or []
    if allocations:
        pdata = [["Ticker", "Marked", "Sektor", "Vekt %", "Score", "Konfidens", "Risiko (0-100)"]]
        for a in allocations:
            pdata.append([a.get("ticker"), a.get("market"), sector_label(a.get("sector")), _fmt(a.get("weight_pct")), _fmt(a.get("score")), _fmt(a.get("confidence")), format_risk(a.get("risk"))])
        ptable = Table(pdata, repeatRows=1, colWidths=[24*mm, 24*mm, 38*mm, 18*mm, 18*mm, 20*mm, 18*mm])
        ptable.setStyle(_table_style())
        story += [KeepTogether([Paragraph("Foreløpig modellportefølje før endelig beslutningsport", styles["Section"]),
                               Paragraph(f"Investert: {_fmt(portfolio_proposal.get('invested_pct', 0))} % | Kontanter: {_fmt(portfolio_proposal.get('cash_pct', 100))} %", styles["BodyCompact"]),
                               ptable])]
    technical_story = story
    full_task_story: list[Any] = []
    if decision_tasks:
        full_task_rows = [["Prioritet", "Kandidat / kontroll", "Type", "Status", "Komplett oppfølging"]]
        for task in decision_tasks:
            full_task_rows.append([
                _p(task.get("priority") or "NORMAL", "Tiny"),
                _p(task.get("subject") or "-", "Tiny"),
                _p(_loc(task.get("kind") or "-"), "Tiny"),
                _p(_loc(task.get("status") or "-"), "Tiny"),
                _p(task.get("action") or "-", "Tiny"),
            ])
        full_task_table = Table(
            full_task_rows, repeatRows=1,
            colWidths=[18*mm, 37*mm, 31*mm, 20*mm, 78*mm],
        )
        full_task_table.setStyle(_table_style(5.6, padding=1.4))
        full_task_story = [
            Paragraph(f"Komplett oppgavespor ({len(decision_tasks)})", styles["Section"]),
            Paragraph(
                "Kort rapport viser bare de tre høyest prioriterte oppgavene. Tabellen under inneholder alle registrerte oppgaver for neste kjøring.",
                styles["Small"],
            ),
            full_task_table,
        ]
    has_technical_content = bool(
        run.get("candidates") or run.get("errors") or run.get("warnings")
        or run.get("data_quality") or run.get("combined_data_quality") or run.get("combined_quality")
        or run.get("market_runs") or run.get("source_health") or run.get("portfolio_decisions")
        or run.get("decision_funnel") or run.get("data_contract")
    )
    if has_technical_content and include_technical:
        story = decision_story + [
            PageBreak(),
            Paragraph("Teknisk vedlegg", styles["ReportTitle"]),
            Paragraph("Full rangering, datakontrakter, kildelogger, bevis, modellbidrag, porteføljelag og revisjonsspor.", styles["BodyCompact"]),
        ] + decision_audit_story + full_task_story + technical_story[2:]
    else:
        has_followup_content_v1924 = bool(
            run.get("candidates") or run.get("changes") or decision_tasks or decision_events
            or decision_historical or decision_diffs or decision_counter_hypotheses
        )
        story = (decision_story + decision_audit_story) if has_followup_content_v1924 else decision_story[:decision_page_one_end_v1924]
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    pdf_bytes = buf.getvalue()
    # ReportLab inherits the Render host timezone for PDF metadata. Rewrite the
    # metadata timestamp to the job's IANA timezone so file properties agree
    # with the visible report and archive.
    try:
        from pypdf import PdfReader, PdfWriter
        local_created = as_local(run.get("created_at"), str(run.get("timezone_name") or DEFAULT_TIMEZONE))
        offset = local_created.strftime("%z")
        pdf_date = f"D:{local_created:%Y%m%d%H%M%S}{offset[:3]}'{offset[3:]}'"
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        # add_page() discarded the outline tree created by ReportLab. Clone the
        # whole document and add a deterministic page outline only if the
        # runtime did not preserve the semantic heading outline.
        writer.clone_document_from_reader(reader)
        try:
            if not list(reader.outline or []):
                for page_index in range(len(reader.pages)):
                    writer.add_outline_item(f"Side {page_index + 1}", page_index)
        except Exception:
            for page_index in range(len(reader.pages)):
                writer.add_outline_item(f"Side {page_index + 1}", page_index)
        metadata = {str(k): str(v) for k, v in dict(reader.metadata or {}).items() if v is not None}
        metadata.update({"/CreationDate": pdf_date, "/ModDate": pdf_date,
                         "/Title": report_type, "/Author": "AI Aksje Analyzer Pro"})
        writer.add_metadata(metadata)
        out = io.BytesIO()
        writer.write(out)
        pdf_bytes = out.getvalue()
    except Exception:
        pass
    pdf_semantics = validate_pdf_semantics(pdf_bytes, run)
    if not pdf_semantics.get("ok"):
        raise ValueError("PDF/JSON-integritet feilet: " + "; ".join(pdf_semantics.get("errors") or []))
    return pdf_bytes


def build_main_pdf(run: Mapping[str, Any], report_type: str | None = None) -> bytes:
    """Investor-facing decision report without the verbose technical appendix."""
    return build_pdf(run, report_type=report_type, include_technical=False)


def build_technical_pdf(run: Mapping[str, Any], report_type: str | None = None) -> bytes:
    """Complete audit report retained separately for source and model review."""
    return build_pdf(run, report_type=report_type, include_technical=True)


def _finalize_completed_report_artifacts(
    run: dict[str, Any], *, previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Regenerate both PDFs from the final execution receipt and error state.

    The first render must exist before Pushover so its URL can be delivered.
    That render is necessarily provisional. This final pass makes the stored
    JSON, investor PDF, technical PDF and archive describe the same completed
    execution instead of freezing the documents before the final chain gates.
    """
    if not run.get("pdf_path"):
        return {"generated": False, "reason": "PDF ikke bestilt"}

    # Re-canonicalise at the actual artifact boundary.  Downstream stages such
    # as parallel validation and controlled learning may enrich the run after
    # the first report render; a stored integrity result from before those
    # stages is therefore not authoritative.
    run.pop("report_document", None)
    run.pop("decision_report", None)
    apply_report_integrity(run)
    run.pop("report_document", None)
    run.pop("decision_report", None)
    ensure_report_document(run, previous)

    pdf_path = Path(str(run["pdf_path"]))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    main_bytes = build_main_pdf(run)
    pdf_path.write_bytes(main_bytes)
    publish_pdf(run, main_bytes)
    run["report_url"] = report_public_url(run)
    run["pdf_delivery"] = {
        "required": True,
        "generated": True,
        "validated": _valid_pdf_bytes(main_bytes),
        "published": bool(run.get("public_pdf_name")),
        "report_url_available": bool(run.get("report_url")),
        "regenerated_after_notification": True,
        "finalized_after_execution_receipt": True,
    }

    technical_path = Path(str(run.get("technical_pdf_path") or pdf_path.with_name(pdf_path.stem + "_technical.pdf")))
    technical_bytes = build_technical_pdf(run)
    technical_path.write_bytes(technical_bytes)
    run["technical_pdf_path"] = str(technical_path)
    run["technical_pdf_name"] = technical_path.name
    from public_report_store import publish_durable_pdf
    publish_durable_pdf(
        run, technical_bytes, token_field="technical_report_token",
        filename_field="technical_pdf_name", document_kind="technical",
    )
    run["technical_pdf_delivery"] = {
        "generated": True,
        "validated": _valid_pdf_bytes(technical_bytes),
        "durable": bool(run.get("technical_report_token")),
        "finalized_after_execution_receipt": True,
    }

    _write(RUNS_DIR / f"{run.get('run_id')}.json", run)
    if str(run.get("trigger") or "").upper() != "REVALIDATION":
        _write(LATEST_PATH, run)
    archive_report(run)
    persistence = verify_report_persistence(str(run.get("run_id") or ""))
    if not persistence.get("ok"):
        raise RuntimeError(str(persistence.get("error") or "Sluttrapporten kunne ikke bekreftes"))
    run["persistence"] = persistence
    return {
        "generated": True,
        "main_valid": bool(run["pdf_delivery"]["validated"]),
        "technical_valid": bool(run["technical_pdf_delivery"]["validated"]),
    }






def _same_job_name(left: str, right: str) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _effective_execution_job(job: JobProfile, trigger: str) -> tuple[JobProfile, dict[str, Any]]:
    """Use one analysis configuration for draft and immediate final execution.

    A saved job may still contain an older scan profile while the editor draft has
    just been tested. For an explicit manual full-chain run, merge the current
    same-name draft analysis settings into the saved job identity. Scheduling and
    persistent job identity remain attached to the saved job.
    """
    trigger_key = str(trigger or "").upper()
    detail = {"requested_fingerprint": job_fingerprint(job), "draft_merged": False}
    if trigger_key != "MANUAL_FULL_CHAIN" or job.job_id == DRAFT_JOB_ID:
        detail["effective_fingerprint"] = job_fingerprint(job)
        return job, detail
    draft = load_draft_job()
    if not _same_job_name(job.name, draft.name):
        detail["effective_fingerprint"] = job_fingerprint(job)
        return job, detail
    merged = JobProfile(**{
        **asdict(draft),
        "job_id": job.job_id,
        "created_at": job.created_at,
        "last_run_at": job.last_run_at,
        "last_status": job.last_status,
        "enabled": job.enabled,
    })
    detail.update({
        "draft_merged": True,
        "draft_fingerprint": job_fingerprint(draft),
        "effective_fingerprint": job_fingerprint(merged),
    })
    return merged, detail


def _recent_validated_draft(job: JobProfile, trigger: str) -> dict[str, Any] | None:
    """Return a recent successful draft that exactly matches the final job config."""
    if str(trigger or "").upper() != "MANUAL_FULL_CHAIN":
        return None
    latest = _read(LATEST_PATH, {})
    identity = resolve_report_identity(latest)
    if identity.get("type") != "UTKAST" or latest.get("analysis_aborted"):
        return None
    if not _same_job_name(str(latest.get("job_name") or ""), job.name):
        return None
    fingerprint = str((latest.get("validation") or {}).get("draft_handoff_fingerprint") or "")
    if fingerprint != job_fingerprint(job):
        return None
    try:
        created = datetime.fromisoformat(str(latest.get("created_at")))
        age = _now() - created.astimezone(_now().tzinfo)
        if age > timedelta(minutes=RECENT_DRAFT_REUSE_MINUTES):
            return None
    except Exception:
        return None
    refresh = latest.get("data_refresh") or {}
    if int(refresh.get("live_count", 0)) + int(refresh.get("cache_count", 0)) <= 0:
        return None
    return latest


def _persist_promoted_run(source: Mapping[str, Any], job: JobProfile, trigger: str, handoff: Mapping[str, Any]) -> dict[str, Any]:
    """Promote a validated draft to final report without a second API burst."""
    run = json.loads(json.dumps(dict(source), ensure_ascii=False, default=str))
    run_id = local_run_id("MI", timezone_name=job.timezone_name)
    promoted_created_at = _now_iso()
    run.update({
        "version": VERSION,
        "run_id": run_id,
        "created_at": promoted_created_at,
        "created_at_local": local_display(promoted_created_at, job.timezone_name),
        "timezone_name": valid_timezone(job.timezone_name),
        "job_id": job.job_id,
        "job_name": job.name,
        "trigger": trigger,
        "report_identity": report_identity(
            trigger, job.name, job.job_id, created_at=promoted_created_at,
            timezone_name=job.timezone_name,
        ),
        "execution_mode": "PROMOTED_VALIDATED_DRAFT",
        "source_draft_run_id": source.get("run_id"),
        "configuration_handoff": dict(handoff),
    })
    validation = dict(run.get("validation") or {})
    validation.update({"unified_execution_pipeline": True, "promoted_from_validated_draft": True})
    run["validation"] = validation
    run["notification"] = {"sent": False, "detail": "Rapport promotert fra validert utkast; ingen ny API-kjøring"}
    ensure_report_document(run, source)
    pdf_path = SUMMARIES_DIR / safe_report_filename(run, "pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = build_main_pdf(run)
    pdf_path.write_bytes(pdf_bytes)
    run["pdf_path"] = str(pdf_path)
    publish_pdf(run, pdf_bytes)
    run["report_url"] = report_public_url(run)
    _write(RUNS_DIR / f"{run_id}.json", run)
    _write(LATEST_PATH, run)
    _write(SUMMARIES_DIR / f"{run_id}.json", {k: run.get(k) for k in ("run_id", "created_at", "job_name", "markets", "summary", "changes", "errors")})
    job.last_run_at, job.last_status = run["created_at"], "OK"
    if not bool(run.get("test_run")) and not str(job.job_id or "").upper().startswith("MI-AUTONOMY-REPORT-TEST"):
        upsert_job(job)
    _audit("JOB_RUN_PROMOTED", {"job_id": job.job_id, "run_id": run_id, "source_draft_run_id": source.get("run_id")})
    return run

def _refresh_meta(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return refresh telemetry regardless of whether it lives top-level or in raw.

    CandidateAssessment serializes the enriched source row under ``raw``. Older
    telemetry code only inspected the assessment top-level and therefore reported
    zero live/cache fetches and unknown trade dates even when live fetching ran.
    """
    raw = candidate.get("raw") if isinstance(candidate, Mapping) else None
    raw = raw if isinstance(raw, Mapping) else {}
    merged = dict(raw)
    merged.update({k: v for k, v in dict(candidate).items() if v is not None})
    return merged


def _build_refresh_summary(candidates: Sequence[Mapping[str, Any]], force_refresh: bool) -> dict[str, Any]:
    rows = [_refresh_meta(c) for c in candidates]
    live_success = [r for r in rows if str(r.get("data_source", "")).endswith("-live") and r.get("data_fetch_status") in {"OK", "NO_DATA"}]
    live_attempts = [r for r in rows if r.get("refresh_proof") in {"LIVE_CACHE_BYPASSED", "LIVE_CACHE_MISS", "LIVE_ATTEMPT_FAILED"} or r.get("fetch_started_at")]
    cache_rows = [r for r in rows if bool(r.get("cache_hit")) or r.get("refresh_proof") == "CACHE_USED"]
    bypass_rows = [r for r in rows if bool(r.get("cache_bypass_applied")) and r.get("refresh_proof") == "LIVE_CACHE_BYPASSED"]
    failed_rows = [r for r in rows if r.get("data_fetch_status") == "ERROR" or r.get("refresh_proof") == "LIVE_ATTEMPT_FAILED"]
    comparable = [r for r in rows if r.get("market_data_changed") is not None]
    verified = bool(force_refresh) and bool(rows) and len(bypass_rows) == len(rows)
    if not force_refresh:
        reason = "Normal cachepolicy"
    elif not rows:
        reason = "Ingen kandidater å verifisere"
    elif verified:
        reason = "Cache ble ignorert og live-innhenting ble fullført for alle kandidater"
    elif failed_rows:
        reason = f"Live-innhenting feilet for {len(failed_rows)} av {len(rows)} kandidater"
    else:
        reason = f"Telemetri mangler for {len(rows) - len(bypass_rows)} av {len(rows)} kandidater"
    execution_trace = []
    for r in rows:
        execution_trace.append({
            "ticker": r.get("ticker"),
            "force_refresh_requested": bool(r.get("force_refresh_requested")),
            "cache_bypass_applied": bool(r.get("cache_bypass_applied")),
            "refresh_proof": r.get("refresh_proof") or "UKJENT",
            "data_source": r.get("data_source") or "UKJENT",
            "data_fetch_status": r.get("data_fetch_status") or "UKJENT",
            "fetch_started_at": r.get("fetch_started_at"),
            "fetch_completed_at": r.get("fetch_completed_at"),
            "latest_trade_date": r.get("latest_trade_date"),
            "market_data_changed": r.get("market_data_changed"),
            "error": r.get("data_fetch_error") or "",
        })
    return {
        "force_refresh_requested": bool(force_refresh),
        "cache_bypass_verified": verified,
        "verification_reason": reason,
        "candidate_count": len(rows),
        "live_attempt_count": len(live_attempts),
        "live_count": len(live_success),
        "cache_count": len(cache_rows),
        "bypass_count": len(bypass_rows),
        "error_count": len(failed_rows),
        "unchanged_market_data_count": sum(1 for r in comparable if r.get("market_data_changed") is False),
        "comparable_market_data_count": len(comparable),
        "latest_trade_dates": sorted({str(r.get("latest_trade_date")) for r in rows if r.get("latest_trade_date")}),
        "proof": "LIVE_CACHE_BYPASSED" if verified else ("FORCE_REFRESH_UNVERIFIED" if force_refresh else "NORMAL_CACHE_POLICY"),
        "cache_ttl_seconds": 21600,
        "execution_trace": execution_trace,
    }

def normalise_progress_counts(completed: Any, total: Any) -> tuple[int, int]:
    """Return safe progress counters for internal and third-party callbacks."""
    try:
        done = max(0, int(completed or 0))
    except (TypeError, ValueError, OverflowError):
        done = 0
    try:
        count = max(1, int(total or 1))
    except (TypeError, ValueError, OverflowError):
        count = 1
    return done, count


def compact_market_run_for_report(result: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve market audit semantics without retaining duplicate raw trees."""
    candidates = list(result.get("candidates") or [])
    proposals = list(result.get("proposals") or [])
    candidate_keys = (
        "ticker", "market", "status", "portfolio_action",
        "investment_score", "confidence_score", "risk_score",
        "valid_for_decision", "evidence_valid_for_decision",
        "autonomy_outcome_code", "autonomy_outcome_reason",
    )
    compact = {
        key: result.get(key) for key in (
            "version", "run_id", "created_at", "config", "summary",
            "analysis_stages", "evidence_observability", "universe_contract",
            "sector_selection", "detection_audit", "candidate_source",
            "discovery_data", "data_refresh", "loader_diagnostics",
        ) if key in result
    }
    compact.update({
        "candidate_count": len(candidates),
        "proposal_count": len(proposals),
        "candidates": [
            {key: row.get(key) for key in candidate_keys if key in row}
            for row in candidates if isinstance(row, Mapping)
        ],
        "proposals": [
            {key: row.get(key) for key in candidate_keys if key in row}
            for row in proposals if isinstance(row, Mapping)
        ],
    })
    return compact


def _run_job_impl(
    job: JobProfile,
    trigger: str = "MANUAL",
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    force_refresh: bool = False,
    revision_parent: Mapping[str, Any] | None = None,
    send_notifications: bool = True,
    scheduled_for: str | None = None,
    _trace_id: str = "",
) -> dict[str, Any]:
    full_run_started = time_module.perf_counter()
    execution_started_at = _now_iso()
    requested_job = job
    trigger = str(trigger or "MANUAL").upper()
    delayed_catchup = trigger == "MISSED_SCHEDULE_CATCHUP"
    job, execution_settings = apply_execution_settings(job)
    # A manual/test run must never inherit an old planned slot. This was the
    # root cause of manually started drafts looking like delayed scheduled
    # reports in Pushover.
    if trigger not in {"SCHEDULED", "MISSED_SCHEDULE_CATCHUP"}:
        scheduled_for = None
    job, handoff = _effective_execution_job(job, trigger)
    if delayed_catchup:
        # A delayed catch-up may rebuild and deliver the missing report, but it
        # must never create portfolio or learning transactions retroactively.
        job = replace(job, run_autonomous_portfolio=False, run_controlled_learning=False)
        execution_settings = {
            **dict(execution_settings or {}),
            "delayed_catchup": True,
            "portfolio_actions_blocked": True,
            "learning_actions_blocked": True,
        }
    profile = market_profile_contract(job.market_profile, job.markets, name=job.name)
    job = replace(
        job,
        market_profile=str(profile["profile_id"]),
        markets=list(profile["selections"]),
    )
    resolved_markets = list(profile["expanded_markets"])
    # Portfolio demand is an input to the mission, never an afterthought.
    from autonomi_core.portfolio_decisions import read_portfolio_needs
    portfolio_need_preflight = read_portfolio_needs()
    from autonomi_core.missions.investment_mission import (
        STRATEGY_PROFILES, create_investment_mission, engine_handoff, load_investment_mission,
    )
    from autonomi_core.configuration.registry import status as _central_configuration_status
    from autonomi_core.configuration.policy import load_policy as _load_mission_policy
    from autonomi_core.missions.user_mission import load_user_mission as _load_legacy_user_mission

    central_configuration_version = str(_central_configuration_status().get("config_version") or "")
    investment_mission = load_investment_mission(job.investment_mission_id) if job.investment_mission_id else {}
    investment_mission = dict(investment_mission or {})
    mission_configuration_version = str(investment_mission.get("configuration_version") or "")
    job_configuration_version = str(job.configuration_version or "")
    mission_missing = not bool(investment_mission)
    mission_stale = bool(investment_mission) and (
        mission_configuration_version != central_configuration_version
        or job_configuration_version != mission_configuration_version
    )

    if mission_missing or mission_stale:
        legacy_mission = _load_legacy_user_mission()
        legacy_mission = (
            legacy_mission
            if str(legacy_mission.get("mission_id") or "") == str(job.user_mission_id or "")
            else {}
        )
        source_mission = investment_mission or legacy_mission
        policy = _load_mission_policy()
        strategy = str(source_mission.get("strategy") or "Kvalitet til rimelig pris")
        if strategy not in STRATEGY_PROFILES:
            strategy = "Kvalitet til rimelig pris"
        generated = create_investment_mission(
            search_for=str(
                source_mission.get("search_for")
                or source_mission.get("goal")
                or job.name
                or "Beste relevante kandidater"
            ),
            markets=resolved_markets,
            sectors=list(source_mission.get("sectors") or []),
            strategy=strategy,
            horizon=str(source_mission.get("horizon") or "3–12 måneder"),
            risk=str(source_mission.get("risk") or "Balansert"),
            risk_ceiling=float(source_mission.get("risk_ceiling", 65.0)),
            portfolio_need=str(
                source_mission.get("portfolio_need")
                or portfolio_need_preflight.get("summary")
                or "Beste enkeltkandidater"
            ),
            minimum_data_quality=float(
                source_mission.get("minimum_data_quality", policy.minimum_data_quality)
            ),
            candidate_count=int(source_mission.get("candidate_count") or job.deep_count),
            exclusions=list(source_mission.get("exclusions") or []),
            objective=str(
                source_mission.get("objective")
                or source_mission.get("goal")
                or job.name
            ),
        )
        old_mission_id = str(investment_mission.get("mission_id") or job.investment_mission_id or "")
        old_configuration_version = mission_configuration_version or job_configuration_version
        investment_mission = generated.to_dict()
        job = replace(
            job, investment_mission_id=generated.mission_id,
            configuration_version=generated.configuration_version,
        )
        persisted_job = replace(
            requested_job,
            name=explicit_job_name_v19220_rc12(
                requested_job.name, profile_id=job.market_profile, markets=job.markets,
                draft=str(requested_job.job_id or "") == DRAFT_JOB_ID,
            ),
            investment_mission_id=generated.mission_id,
            configuration_version=generated.configuration_version,
        )
        if str(persisted_job.job_id or "") == DRAFT_JOB_ID:
            save_draft_job(persisted_job)
        else:
            upsert_job(persisted_job)
        requested_job = persisted_job
        handoff = dict(handoff or {})
        handoff["configuration_contract_migration"] = {
            "performed": True,
            "reason": "MISSION_MISSING" if mission_missing else "CENTRAL_CONFIGURATION_CHANGED",
            "old_mission_id": old_mission_id,
            "new_mission_id": generated.mission_id,
            "old_configuration_version": old_configuration_version,
            "new_configuration_version": generated.configuration_version,
            "schedules_preserved": list(persisted_job.schedules or []),
            "timezone_preserved": persisted_job.timezone_name,
        }
        _audit("JOB_CONFIGURATION_CONTRACT_MIGRATED_RC12", {
            "job_id": persisted_job.job_id, "job_name": persisted_job.name,
            **handoff["configuration_contract_migration"],
        })

    if investment_mission:
        mission_markets = normalize_markets(investment_mission.get("markets") or [])
        if mission_markets != resolved_markets:
            investment_mission["source_markets_before_profile_reconciliation"] = mission_markets
            investment_mission["markets"] = list(resolved_markets)
            investment_mission["market_profile_reconciled"] = True
        investment_mission["market_profile"] = dict(profile)
    if investment_mission and str(investment_mission.get("configuration_version") or "") != str(job.configuration_version or ""):
        raise ValueError("Oppdragets konfigurasjonsversjon kunne ikke migreres til jobbkontrakten")
    if investment_mission and str(investment_mission.get("configuration_version") or "") != central_configuration_version:
        raise ValueError("Oppdragets konfigurasjonsversjon kunne ikke migreres til sentral konfigurasjon")
    from evidence_integrity import build_integrity_preflight
    integrity_preflight = build_integrity_preflight(job)
    if not integrity_preflight.get("can_run"):
        blockers = ", ".join(
            str(row.get("name") or "ukjent")
            for row in integrity_preflight.get("checks") or [] if row.get("blocking")
        )
        raise ValueError(f"Forhåndskontroll blokkerte kjøringen: {blockers or 'ukjent blokkering'}")
    previous = dict(revision_parent or {}) or _read(LATEST_PATH, {})
    reusable = None if force_refresh or revision_parent else _recent_validated_draft(job, trigger)
    if reusable is not None:
        if progress_callback:
            progress_callback({"phase": "COMPLETE", "completed": 1, "total": 1, "message": "Validerte utkastdata gjenbrukes som endelig morgenrapport"})
        return _persist_promoted_run(reusable, job, trigger, handoff)
    def emit(phase: str, completed: int, total: int, message: str, **extra: Any) -> None:
        completed, total = normalise_progress_counts(completed, total)
        payload = {"phase": phase, "completed": completed, "total": total, "message": message, **extra}
        if progress_callback:
            progress_callback(payload)
        if _trace_id:
            try:
                from operational_telemetry import mark_run_stage
                phase_status = "COMPLETED" if completed >= total else "RUNNING"
                mark_run_stage(_trace_id, phase, status=phase_status, message=message, metrics={
                    key: value for key, value in payload.items() if key not in {"phase", "message"}
                })
            except Exception:
                # Telemetry is observational and must never stop a report run.
                pass
    emit("START", 0, 1, "Starter markedsskanning")
    market_runs, all_candidates, all_proposals = [], [], []
    market_candidate_total = 0
    market_diagnostics: list[dict[str, Any]] = []
    totals = {"scanned": 0, "deep_analyzed": 0, "proposals": 0, "recommended": 0, "rejected": 0}
    errors = []
    warnings = []
    markets = list(resolved_markets)
    for market_index, market in enumerate(markets, start=1):
        market_deep_budget = _allocated_market_budget(job.deep_count, market_index, len(markets), minimum=1)
        market_evidence_budget = min(
            market_deep_budget,
            _allocated_market_budget(job.proposal_count, market_index, len(markets), minimum=0),
        )
        market_deep_budget = _allocated_market_budget(job.deep_count, market_index, len(markets), minimum=1)
        # Evidence must follow quality, not a 4/3/3-style market quota.  Taking
        # the local Top N in each market is the bounded one-pass guarantee that
        # the later global Top N has complete evidence coverage.
        market_evidence_analysis_budget = _effective_global_evidence_size(
            job.evidence_analysis_count, market_deep_budget,
        )
        cfg = PipelineConfig(market_scope=market, scan_limit=job.scan_limit, deep_analysis_count=market_deep_budget,
                             proposal_count=market_evidence_budget, use_research="AI Research Assistant" in job.modules,
                             evidence_analysis_count=market_evidence_analysis_budget,
                             use_backtest="Backtesting Validation" in job.modules,
                             use_portfolio_fit="Portfolio Optimizer" in job.modules,
                             use_learning_advisor="Learning Advisor" in job.modules,
                             use_insider_intelligence="Insider Intelligence" in job.modules,
                             use_news_intelligence="News & Sentiment Intelligence" in job.modules,
                             min_data_quality=float(investment_mission.get("minimum_data_quality", 45.0)),
                             max_risk_score=float(investment_mission.get("risk_ceiling", 75.0)),
                             mission_id=str(investment_mission.get("mission_id") or ""),
                             configuration_version=str(investment_mission.get("configuration_version") or ""),
                             full_universe_scan=market in {"Norge", "Sverige", "USA"}).normalized()
        try:
            emit("MARKET", market_index - 1, len(markets), f"Forbereder marked {market_index}/{len(markets)}: {market}", market=market)
            try:
                loaded = _load_candidate_rows_from_app(cfg, return_discovery=True)
            except TypeError as exc:
                if "return_discovery" not in str(exc):
                    raise
                loaded = _load_candidate_rows_from_app(cfg)
            # Compatibility with integrations/tests that still provide the
            # established two-value loader contract.
            if len(loaded) == 3:
                rows, source, discovery = loaded
            else:
                rows, source = loaded
                discovery = {"version": "LEGACY", "market": market, "selected": len(rows), "rotated_from_previous": False}
            if not rows:
                error = f"{market}: ingen kandidater i valgt markedsunivers"
                errors.append(error)
                market_diagnostics.append({"market": market, "scanned": 0, "analyzed": 0, "live": 0,
                                           "errors": 1, "status": "FEIL: INGEN KANDIDATER", "error_detail": error})
                continue
            # Candidate-recall repair: market data has already been fetched for
            # these rows, so calculate the deterministic local score for every
            # fetched candidate.  Expensive evidence collection remains bounded
            # by evidence_analysis_count/proposal_count.
            cfg = replace(
                cfg,
                deep_analysis_count=_full_score_budget(len(rows)),
                evidence_analysis_count=_effective_global_evidence_size(job.evidence_analysis_count, len(rows)),
            ).normalized()
            def _pipeline_progress(event: Mapping[str, Any]) -> None:
                e = dict(event)
                e["market"] = market
                e["market_index"] = market_index
                e["market_total"] = len(markets)
                if progress_callback:
                    progress_callback(e)
            result = run_pipeline(rows, cfg, progress_callback=_pipeline_progress, force_refresh=force_refresh)
            result["candidate_source"] = source
            result["discovery_data"] = discovery
            market_refresh = _build_refresh_summary(result.get("candidates") or [], force_refresh)
            # A whole-market zero-live result is usually temporary throttling. Retry
            # only that market once, after a controlled cooldown, instead of
            # publishing a misleading partial ranking.
            if int(market_refresh.get("live_attempt_count", 0)) > 0 and int(market_refresh.get("live_count", 0)) == 0:
                emit("MARKET_DATA", 0, 1, f"{market}: ingen live-data, venter og prøver markedet én gang til", market=market)
                time_module.sleep(3.0)
                retry_result = run_pipeline(rows, cfg, progress_callback=_pipeline_progress, force_refresh=True)
                retry_refresh = _build_refresh_summary(retry_result.get("candidates") or [], True)
                if int(retry_refresh.get("live_count", 0)) > int(market_refresh.get("live_count", 0)):
                    result = retry_result
                    result["candidate_source"] = source
                    result["discovery_data"] = discovery
                    market_refresh = retry_refresh
                    result["market_retry_used"] = True
            if market_index < len(markets):
                time_module.sleep(1.0)
            candidate_errors = list(result.get("candidate_errors") or [])
            skipped_tickers = sorted({
                str(item.get("ticker") or "").strip().upper()
                for item in candidate_errors if isinstance(item, Mapping) and item.get("ticker")
            })
            loader_skipped = int((result.get("loader_diagnostics") or {}).get("skipped_count", 0))
            skipped_count = len(skipped_tickers) or loader_skipped
            market_data_errors = int(market_refresh.get("error_count", 0))
            market_diagnostics.append({
                "market": market,
                "scanned": int((result.get("summary") or {}).get("scanned", len(rows))),
                "analyzed": len(result.get("candidates") or []),
                "live": int(market_refresh.get("live_count", 0)),
                "errors": market_data_errors,
                "market_data_errors": market_data_errors,
                "candidate_error_events": len(candidate_errors),
                "skipped_candidate_count": skipped_count,
                "skipped_tickers": skipped_tickers,
                "status": ("OK" if int(market_refresh.get("live_count", 0)) > 0 else "INGEN LIVE-DATA") + (f" · {skipped_count} kandidat(er) hoppet over" if skipped_count else ""),
                "candidate_errors": candidate_errors[:10],
                "universe_contract": result.get("universe_contract") or {},
                "sector_selection": result.get("sector_selection") or {},
            })
            for item in candidate_errors:
                warnings.append(f"{market}/{item.get('ticker') or 'ukjent'} ({item.get('stage')}): {item.get('error')}")
            result_candidates = list(result.get("candidates") or [])
            result_proposals = list(result.get("proposals") or [])
            market_candidate_total += len(result_candidates)
            all_candidates.extend(result_candidates)
            all_proposals.extend(result_proposals)
            # Keep the market-level audit contract, but not a second complete
            # candidate/evidence tree for the rest of the report lifecycle.
            # Canonical full candidates live in all_candidates/run.candidates.
            market_runs.append(compact_market_run_for_report(result))
            for key in totals:
                totals[key] += int((result.get("summary") or {}).get(key, 0))
            # Drop stage-1 rows, selection traces and duplicate serialized
            # payloads before the next market. malloc_trim is important for a
            # long-lived Render web process where freed pandas arenas otherwise
            # remain charged to the cgroup.
            del result, result_candidates, result_proposals, rows, loaded
            from runtime_memory import release_process_memory
            release_process_memory(f"after_market_{market}")
        except Exception as exc:
            if isinstance(exc, ExecutionCancelled):
                raise
            errors.append(f"{market}: {exc}")
            market_diagnostics.append({"market": market, "scanned": 0, "analyzed": 0, "live": 0, "errors": 1,
                                       "status": "FEIL: MARKEDSKJØRING", "error_detail": str(exc)})
    emit("DEDUP", 1, 1, "Fjerner duplikater og rangerer kandidater")
    # Global identity integrity: one ticker, one canonical market, one assessment.
    deduped: dict[str, dict[str, Any]] = {}
    identity_rejections: list[dict[str, Any]] = []
    for raw_candidate in all_candidates:
        candidate = normalize_candidate_identity(raw_candidate)
        from decision_inputs import candidate_entry_score, candidate_score_audit
        score_audit = candidate_score_audit(candidate)
        candidate["investment_score_before_evidence_neutralisation"] = score_audit["raw_adjusted_score"]
        candidate["effective_entry_score"] = score_audit["effective_entry_score"]
        candidate["unverified_positive_credit_removed"] = score_audit["unverified_positive_credit_removed"]
        candidate["investment_score"] = candidate_entry_score(candidate)
        ticker = str(candidate.get("ticker") or "").upper()
        if not ticker:
            identity_rejections.append({"reason": "Mangler ticker", "candidate": dict(raw_candidate)})
            continue
        canonical_market = infer_market_from_ticker(ticker, str(candidate.get("market") or ""))
        candidate["market"] = canonical_market
        current = deduped.get(ticker)
        if current is None or float(candidate.get("investment_score", 0)) > float(current.get("investment_score", 0)):
            deduped[ticker] = candidate
    all_candidates = list(deduped.values())
    all_candidates.sort(key=lambda x: float(x.get("investment_score", 0)), reverse=True)
    # Select globally only after every fetched candidate has received the same
    # local scoring treatment.  A legacy deep_count of 10 can no longer create
    # a hidden 4/3/3 market quota.
    global_shortlist_size = _effective_global_shortlist_size(job.deep_count, len(all_candidates))
    all_candidates = _balanced_global_shortlist(all_candidates, global_shortlist_size, markets)
    for idx, row in enumerate(all_candidates, 1):
        row["rank"] = idx
        row["raw_rank"] = idx
    # RC16.21 migration bridge: reuse the proven Paper scanner's immutable
    # technical observations as an explicit Autonomi input.  This is
    # observational only and occurs after ranking, so it cannot mutate score,
    # order eligibility or the public candidate order.
    from paper_autonomy_bridge import attach_paper_engine_inputs
    paper_engine_handoff = attach_paper_engine_inputs(all_candidates)
    evidence_coverage_summary = apply_evidence_coverage_policy(all_candidates)
    from evidence_search_status import build_run_search_summary
    evidence_search_summary = build_run_search_summary(all_candidates)
    from autonomi_core.discovery_data.freshness import apply_data_contracts
    from autonomi_core.configuration.policy import load_policy
    freshness_policy = load_policy()
    if investment_mission:
        freshness_policy = replace(freshness_policy, minimum_data_quality=float(investment_mission.get("minimum_data_quality", freshness_policy.minimum_data_quality)))
    data_contract_summary = apply_data_contracts(all_candidates, policy=freshness_policy)
    for row in all_candidates:
        readiness = row.get("decision_readiness") if isinstance(row.get("decision_readiness"), dict) else {}
        readiness["market_data"] = "GYLDIG" if row.get("valid_for_decision") else "UGYLDIG"
        row["decision_readiness"] = readiness
    combined_quality = combined_quality_summary(all_candidates, data_contract_summary, evidence_coverage_summary)
    totals["deep_analyzed"] = len(all_candidates)
    from autonomi_core.missions.user_mission import apply_user_mission, load_user_mission
    stored_mission = load_user_mission()
    user_mission = investment_mission or (stored_mission if str(stored_mission.get("mission_id") or "") == str(job.user_mission_id or "") else {})
    mission_summary = apply_user_mission(all_candidates, user_mission)
    from autonomi_core.portfolio_decisions.layer import apply_portfolio_decisions
    portfolio_decisions = apply_portfolio_decisions(
        all_candidates, mission_id=str(investment_mission.get("mission_id") or ""),
        configuration_version=str(investment_mission.get("configuration_version") or ""),
    )
    from autonomous_portfolio import load_parameters, load_portfolio
    from autonomous_decision_reduction import apply_decision_reduction, MARKET_SOURCE_MATRIX
    autonomy_parameters = load_parameters().normalized()
    autonomous_portfolio_snapshot = load_portfolio()
    autonomous_portfolio_snapshot["maximum_open_positions"] = int(autonomy_parameters.maximum_open_positions)
    autonomous_portfolio_snapshot["reserve_cash_pct"] = float(autonomy_parameters.reserve_cash_pct)
    autonomous_portfolio_snapshot["snapshot_timing"] = "FØR_AUTONOMI"
    all_candidates, decision_reduction = apply_decision_reduction(
        all_candidates,
        threshold=float(autonomy_parameters.minimum_investment_score),
        maximum_risk=float(autonomy_parameters.maximum_risk_score),
        near_threshold_gap=6.0,
        max_manual_tasks=2,
    )
    evidence_ready_candidates = [
        x for x in all_candidates
        if bool(x.get("valid_for_decision"))
        and bool(x.get("evidence_valid_for_decision"))
        and bool(x.get("mission_eligible", True))
    ]
    final_decision_candidates = [
        x for x in evidence_ready_candidates
        if str(x.get("portfolio_action") or "").upper() in {"BUY", "KJØP"}
    ]
    analytical_recommendation_candidates = [
        x for x in all_candidates
        if str(x.get("autonomy_outcome_code") or "").upper()
        in {"KJØPSKANDIDAT", "MODERAT_KJØPSANBEFALING"}
    ]
    for index, row in enumerate(evidence_ready_candidates, 1):
        row["evidence_ready_rank"] = index
    for index, row in enumerate(final_decision_candidates, 1):
        row["decision_ready_rank"] = index
    evidence_ready_tickers = {str(row.get("ticker") or "") for row in evidence_ready_candidates}
    decision_ready_tickers = {str(row.get("ticker") or "") for row in final_decision_candidates}
    analytical_tickers = {str(row.get("ticker") or "") for row in analytical_recommendation_candidates}
    for row in all_candidates:
        row["evidence_data_ready"] = str(row.get("ticker") or "") in evidence_ready_tickers
        row["final_decision_ready"] = str(row.get("ticker") or "") in decision_ready_tickers
        row["analytical_recommendation_ready"] = str(row.get("ticker") or "") in analytical_tickers
        row["trade_authorized"] = False
        if not row["evidence_data_ready"]:
            row["evidence_ready_rank"] = None
        if not row["final_decision_ready"]:
            row["decision_ready_rank"] = None
    totals["recommended"] = len(analytical_recommendation_candidates)
    totals["rejected"] = sum(1 for x in all_candidates if x.get("status") in {"AVVIST AV RISIKOPORT", "UTILSTREKKELIGE DATA"})
    proposal_map: dict[str, dict[str, Any]] = {}
    for proposal in all_proposals:
        clean = normalize_candidate_identity(proposal)
        ticker = str(clean.get("ticker") or "").upper()
        if ticker and (ticker not in proposal_map or float(clean.get("investment_score", 0)) > float(proposal_map[ticker].get("investment_score", 0))):
            proposal_map[ticker] = clean
    candidate_by_ticker = {str(x.get("ticker") or "").upper(): x for x in all_candidates}
    valid_proposals: list[dict[str, Any]] = []
    for ticker, proposal in proposal_map.items():
        governed = candidate_by_ticker.get(ticker, {})
        proposal.update({key: governed.get(key) for key in (
            "data_contract", "valid_for_decision", "confidence_score", "status",
            "status_before_data_contract", "confidence_before_data_contract",
            "evidence_coverage", "evidence_valid_for_decision", "evidence_gate_status",
            "evidence_review_required", "evidence_confidence_penalty", "evidence_confidence_cap",
            "confidence_before_evidence_policy",
            "strategy_matches", "strategy_scores", "analysis_ranking",
            "portfolio_decision", "portfolio_action",
        ) if key in governed})
        proposal["mission_eligible"] = governed.get("mission_eligible", True)
        proposal["mission_fit"] = governed.get("mission_fit")
        proposal["autonomy_outcome_code"] = governed.get("autonomy_outcome_code")
        proposal["autonomy_outcome_label"] = governed.get("autonomy_outcome_label")
        if (proposal.get("valid_for_decision") and proposal.get("evidence_valid_for_decision")
                and proposal.get("mission_eligible", True)
                and proposal.get("portfolio_action") in {"BUY", "REVIEW"}
                and governed.get("autonomy_outcome_code") != "AUTOMATISK_AVVIST"):
            valid_proposals.append(proposal)
    all_proposals = sorted(valid_proposals, key=lambda x: float(x.get("investment_score", 0)), reverse=True)[:job.proposal_count]
    totals["proposals"] = len(all_proposals)
    run_id = local_run_id("MI", timezone_name=job.timezone_name)
    if _trace_id:
        try:
            from operational_telemetry import bind_run_trace
            bind_run_trace(_trace_id, run_id=run_id, report_id=run_id, job_id=job.job_id)
        except Exception:
            pass
    refresh_summary = _build_refresh_summary(all_candidates, force_refresh)
    attempted = int(refresh_summary.get("live_attempt_count", 0))
    successful = int(refresh_summary.get("live_count", 0)) + int(refresh_summary.get("cache_count", 0))
    analysis_aborted = bool(attempted > 0 and successful == 0)
    if analysis_aborted:
        all_proposals = []
        totals["proposals"] = 0
        totals["recommended"] = 0
        errors.append(f"Analyse avbrutt: live-innhenting feilet for {attempted} av {attempted} kandidater")
    market_status = build_market_status(markets, refresh_summary)
    data_quality = build_data_quality(refresh_summary, len(all_candidates), market_diagnostics, markets)
    failed_markets = list(data_quality.get("failed_markets") or [])
    partial_market_failure = bool(failed_markets and all_candidates)
    run_created_at = _now_iso()
    run = {"version": VERSION, "run_id": run_id, "created_at": run_created_at,
           "execution_started_at": execution_started_at,
           "operations_trace_id": _trace_id,
           "created_at_local": local_display(run_created_at, job.timezone_name), "job_id": job.job_id, "job_name": job.name,
           "timezone_name": valid_timezone(job.timezone_name),
           "trigger": trigger, "scheduled_for": scheduled_for or "",
           "execution_settings": execution_settings,
           "test_run": "TEST" in str(trigger or "").upper(),
           "report_test_series": {
               "series_id": str(getattr(job, "report_test_series_id", "") or ""),
               "part": int(getattr(job, "report_test_part", 0) or 0),
               "total": int(getattr(job, "report_test_total", 0) or 0),
               "attempt": int(getattr(job, "report_test_attempt", 0) or 0),
               "automatic": bool(getattr(job, "report_test_series_id", "")),
           },
           "suppress_notifications": should_suppress_notifications(trigger, send_notifications),
           "markets": markets, "market_profile": dict(profile), "modules": job.modules, "summary": totals, "candidates": all_candidates,
           "proposals": all_proposals, "market_runs": market_runs, "errors": errors, "warnings": warnings, "execution": "ANALYSIS_ONLY",
           "data_refresh": refresh_summary, "market_status": market_status, "data_quality": data_quality,
           "data_contract": data_contract_summary,
           "evidence_coverage": evidence_coverage_summary,
           "evidence_search_summary": evidence_search_summary,
           "paper_engine_handoff": paper_engine_handoff,
           "combined_data_quality": combined_quality,
           "integrity_preflight": integrity_preflight,
           "portfolio_need_preflight": portfolio_need_preflight,
           "portfolio_decisions": portfolio_decisions,
           "autonomous_decision_reduction": decision_reduction,
           "manual_tasks": list(decision_reduction.get("manual_tasks") or []),
           "priority_top3": list(decision_reduction.get("priority_top3") or []),
           "source_strategy": {
               "version": APP_VERSION, "market_matrix": {market: MARKET_SOURCE_MATRIX.get(market, {}) for market in markets},
               "policy": "Primærkilde -> reservekilde -> automatisk overvåking; manuell oppgave bare for nær-terskel kritiske mangler",
           },
           "analysis_stages": {
               "stage1_scanned": sum(int((item.get("summary") or {}).get("stage1_scanned", 0)) for item in market_runs),
               "stage1_screened_out": sum(int((item.get("summary") or {}).get("stage1_screened_out", 0)) for item in market_runs),
               "stage2_extended": len(all_candidates),
               "stage3_evidence_controlled": sum(int((item.get("summary") or {}).get("stage3_evidence_controlled", 0)) for item in market_runs),
           },
           "universe_coverage": [dict(item.get("universe_contract") or {}) for item in market_runs],
           "sector_selection": [dict(item.get("sector_selection") or {}) for item in market_runs],
           "detection_audit": [dict(item.get("detection_audit") or {}) for item in market_runs],
           "discovery_data": {
               "version": "v18.8.7", "markets": [dict(item.get("discovery_data") or {}) for item in market_runs],
               "selected": sum(int((item.get("discovery_data") or {}).get("selected", 0)) for item in market_runs),
               "quarantined": sum(int((item.get("discovery_data") or {}).get("quarantined", 0)) for item in market_runs),
               "rotated": all(bool((item.get("discovery_data") or {}).get("rotated_from_previous", False)) for item in market_runs) if market_runs else False,
           },
           "user_mission": user_mission,
           "mission_summary": mission_summary,
           "investment_mission": investment_mission,
           "mission_id": investment_mission.get("mission_id") or "",
           "configuration_version": investment_mission.get("configuration_version") or "",
           "engine_handoff": engine_handoff(investment_mission, list(job.modules) + ["Investment Pipeline", "Autonomous Portfolio", "Controlled Learning", "Reporting"]) if investment_mission else {},
           "analysis_aborted": analysis_aborted,
           "partial_market_failure": partial_market_failure,
           "completion_status": "FULLFØRT MED MARKEDSFEIL" if partial_market_failure else ("AVBRUTT" if analysis_aborted else "FULLFØRT"),
           "executive_intelligence": executive_intelligence(all_candidates),
           "raw_top3": select_diverse_candidates(all_candidates, 3),
           "evidence_ready_top3": select_diverse_candidates(evidence_ready_candidates, 3),
           "decision_ready_top3": select_diverse_candidates(final_decision_candidates, 3),
           "final_decision_top3": select_diverse_candidates(final_decision_candidates, 3),
           "diverse_top3": select_diverse_candidates(all_candidates, 3),
           "top3_status": {
               "priority_count": min(3, len(decision_reduction.get("priority_top3") or [])),
               "raw_count": min(3, len(all_candidates)),
               "evidence_data_ready_count": min(3, len(evidence_ready_candidates)),
               "decision_ready_count": min(3, len(final_decision_candidates)),
               "label": ("Kjøpsgodkjent Top 3" if final_decision_candidates else ("Evidens- og dataklar kortliste" if evidence_ready_candidates else "Rå rangering")),
               "complete": len(final_decision_candidates) >= 3,
               "display_mode": "FINAL_DECISION" if final_decision_candidates else ("EVIDENCE_SHORTLIST" if evidence_ready_candidates else "RAW_RANKING"),
           },
           "report_identity": (
               dict(previous.get("report_identity") or {})
               if revision_parent and isinstance(previous.get("report_identity"), Mapping)
               else report_identity(
                   trigger, job.name, job.job_id, created_at=run_created_at,
                   timezone_name=job.timezone_name,
               )
           ),
           "revalidation": {
               "is_revalidation": bool(revision_parent),
               "parent_run_id": previous.get("run_id") if revision_parent else "",
               "attempt": int((previous.get("revalidation") or {}).get("attempt") or 0) + 1 if revision_parent else 0,
           },
           "execution_mode": "UNIFIED_PIPELINE",
           "autonomous_portfolio_snapshot": autonomous_portfolio_snapshot,
           "configuration_handoff": handoff,
           "market_diagnostics": market_diagnostics,
           "candidate_selection": {
               "policy": "FULL_LOCAL_SCORE_THEN_GLOBAL_SHORTLIST",
               "available_after_deduplication": len(deduped),
               "selected": len(all_candidates),
               "configured_legacy_deep_count": int(job.deep_count),
               "minimum_global_shortlist": MINIMUM_GLOBAL_CANDIDATE_SHORTLIST,
               "minimum_per_selected_market": MINIMUM_CANDIDATES_PER_SELECTED_MARKET,
               "production_threshold_changed": False,
               "shadow_thresholds": [73.0, 70.0, 68.0, 65.0],
           },
           "validation": {
               "unique_tickers": len(all_candidates),
               "identity_rejections": identity_rejections,
               "duplicate_count_removed": max(0, market_candidate_total - len(all_candidates)),
               "draft_handoff_fingerprint": job_fingerprint(job),
               "report_identity_present": True,
               "unified_execution_pipeline": True,
               "requested_job_fingerprint": job_fingerprint(requested_job),
               "effective_job_fingerprint": job_fingerprint(job),
               "valid_for_ranking": not analysis_aborted and bool(all_candidates),
           },
           "scan_configuration": {
               "per_market": "Hele konfigurert univers" if set(markets).issubset({"Norge", "Sverige", "USA"}) else job.scan_limit,
               "market_count": len(markets),
               "planned_maximum": sum(int((item.get("universe_contract") or {}).get("configured_universe", 0)) for item in market_runs),
               "deep_analysis_total_budget": int(job.deep_count),
               "evidence_analysis_total_budget": int(job.evidence_analysis_count),
               "effective_global_evidence_minimum": int(MINIMUM_GLOBAL_EVIDENCE_SHORTLIST),
               "evidence_selection_policy": "LOCAL_TOP_N_GUARANTEES_GLOBAL_TOP_N",
               "newsapi_per_report_hard_cap": 5 if "TEST" in str(trigger or "").upper() or "TEST" in str(job.name or "").upper() else 15,
               "actual_by_market": {
                   str(item.get("config", {}).get("market_scope") or "Ukjent"): int((item.get("summary") or {}).get("scanned", 0))
                   for item in market_runs
               },
           }}
    run["market_coverage"] = build_market_coverage_v19220_rc9(run)
    run["ranking_explanation"] = build_ranking_explanation(run)
    run["autonomy_candidate_handoff"] = build_autonomy_candidate_handoff(run)
    from autonomi_core.portfolio_decisions.layer import build_portfolio_aware_proposal
    emit("PORTFOLIO_PROPOSAL", 1, 1, "Beregner porteføljeforslag")
    run["portfolio_proposal"] = ({"positions": [], "allocations": [], "invested_pct": 0.0, "cash_pct": 100.0, "status": "AVBRUTT_UTILSTREKKELIGE_DATA"}
                                 if analysis_aborted else build_portfolio_aware_proposal(evidence_ready_candidates, portfolio_decisions))
    if analysis_aborted:
        run["changes"] = {"new": [], "improved": [], "weakened": [], "unchanged": [], "dropped": []}
    else:
        run["changes"] = compare_runs(run, previous)
        _update_history(run)
    from evidence_integrity import finalize_run_integrity
    apply_report_integrity(run)
    from universe_coverage import build_buy_gate_audit
    canonical_candidates = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    production_threshold = float((run.get("report_summary") or {}).get("production_buy_threshold") or 78.0)
    run["buy_gate_audit"] = build_buy_gate_audit(canonical_candidates, production_threshold)
    finalize_run_integrity(run, previous)
    ensure_report_document(run, previous)
    # Stable identity is known before Controlled Learning runs. The immutable
    # record itself is committed after the autonomous stages are complete.
    run["canonical_result"] = {"result_id": f"RESULT-{run_id}", "run_id": run_id, "pending_storage": True}
    try:
        if analysis_aborted:
            run["autonomous_chain"] = {"status": "SKIPPED", "reason": "Utilstrekkelige markedsdata"}
        else:
            from runtime_memory import release_process_memory
            run["memory_cleanup_before_autonomy"] = release_process_memory("before_autonomy")
            from autonomi_core.runtime.orchestrator import execute_market_mission
            emit("AUTONOMOUS", 0, 1, "Kjører teoretiske kjøps- og salgsbeslutninger")
            run["autonomous_chain"] = execute_market_mission(
            run,
            run_autonomous=job.run_autonomous_portfolio,
            run_learning=job.run_controlled_learning,
            require_active_portfolio=job.require_active_portfolio,
                trigger=trigger,
                progress_callback=lambda event: emit(
                    "AUTONOMOUS", event.get("completed"), event.get("total"),
                    str(event.get("message") or event.get("substage") or "Autonomi arbeider"),
                    ticker=str(event.get("ticker") or ""),
                ),
            )
            emit("AUTONOMOUS", 1, 3, "Autonomi fullført; kontrollerer lagrede læringsbeslutninger")
            from learning_acceptance import evaluate_learning_run
            run["learning_acceptance"] = evaluate_learning_run(run)
            emit("AUTONOMOUS", 2, 3, "Læringsaksept lagret; bygger canonical rapportgrunnlag")
            run["autonomy_candidate_handoff"] = build_autonomy_candidate_handoff(run, run.get("autonomous_chain"))
            if run["autonomy_candidate_handoff"].get("mismatch"):
                warnings.append(run["autonomy_candidate_handoff"].get("warning"))
    except Exception as exc:
        if isinstance(exc, ExecutionCancelled):
            raise
        run["autonomous_chain"] = {
            "status": "ERROR", "errors": [str(exc)],
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc()[-12000:],
            "failed_stage": "AUTONOMY_GATEWAY",
        }
        try:
            from learning_acceptance import evaluate_learning_run
            run["learning_acceptance"] = evaluate_learning_run(run)
        except Exception:
            pass
        errors.append(f"Autonom orkestrering: {exc}")
    # v19.0.6: one canonical explanation mirrors the final Autonomous Portfolio
    # gates. Shadow thresholds are diagnostic and never alter production.
    try:
        from autonomous_portfolio import TRADES_PATH, load_parameters, load_portfolio
        from durable_runtime import read_json as read_durable_json
        from autonomi_core.portfolio_decisions.decision_funnel import apply_funnel_annotations, build_decision_funnel
        trades = read_durable_json("autonomous_portfolio/trades.json", TRADES_PATH, []) or []
        run["decision_funnel"] = build_decision_funnel(
            all_candidates, parameters=load_parameters().normalized(), portfolio=load_portfolio(), trades=trades,
        )
        apply_funnel_annotations(all_candidates, run["decision_funnel"])
        apply_funnel_annotations(run.get("candidates") or [], run["decision_funnel"])
    except Exception as exc:
        run["decision_funnel"] = {"version": APP_VERSION, "mode": "DIAGNOSTIC_ONLY", "error": str(exc)}
    # RC16.31n: every report consumer must use one post-trade snapshot.  The
    # previous implementation retained the pre-trade snapshot while later
    # sections counted newly executed positions, producing 12/13 conflicts.
    from autonomous_portfolio import load_parameters as _load_final_parameters, load_portfolio as _load_final_portfolio
    _final_parameters = _load_final_parameters().normalized()
    _final_portfolio = _load_final_portfolio()
    _final_portfolio["maximum_open_positions"] = int(_final_parameters.maximum_open_positions)
    _final_portfolio["reserve_cash_pct"] = float(_final_parameters.reserve_cash_pct)
    _final_portfolio["snapshot_timing"] = "ETTER_AUTONOMI"
    _final_portfolio["snapshot_run_id"] = str(run_id)
    run["autonomous_portfolio_snapshot"] = _final_portfolio
    # Owned positions are a mandatory report population, independent of the
    # candidate evidence budget. Complete and merge their short/insider checks
    # before the immutable report document is assembled.
    from report_portfolio_intelligence import ensure_portfolio_evidence
    run["candidates"] = ensure_portfolio_evidence(
        _final_portfolio, run.get("candidates") or [], force_refresh=bool(getattr(job, "force_refresh", False))
    )
    # Rebuild the canonical report after Autonomi so production and learning
    # activity is separated in the same document that is persisted and rendered.
    apply_report_integrity(run)
    emit("AUTONOMOUS", 3, 3, "Kontrollerer samsvar mellom læringshandler og rapport")
    from report_integrity import audit_learning_report_consistency
    run["learning_report_consistency"] = audit_learning_report_consistency(run)
    if not run["learning_report_consistency"].get("ok"):
        raise RuntimeError("Lærings-/rapportkonsistens feilet: " + "; ".join(run["learning_report_consistency"].get("errors") or []))
    run.pop("report_document", None)
    run.pop("decision_report", None)
    from report_portfolio_intelligence import assert_portfolio_report_integrity, build_portfolio_report
    _portfolio_report_preflight = build_portfolio_report(_final_portfolio, run.get("candidates") or [], now=_now())
    assert_portfolio_report_integrity(_portfolio_report_preflight)
    run["portfolio_accounting_preflight"] = dict(_portfolio_report_preflight.get("reconciliation") or {})
    from autonomi_core.runtime.full_execution import reconcile_portfolio_assessment
    run["portfolio_assessment_contract"] = reconcile_portfolio_assessment(run)
    # This is the last canonicalisation point before every external consumer.
    # JSON, PDFs, Pushover and publication gates must observe the same rows.
    apply_report_integrity(run)
    finalize_run_integrity(run, previous)
    from decision_plausibility import audit_decision_plausibility
    _previous_for_plausibility = [previous] if isinstance(previous, Mapping) and previous else []
    run["decision_plausibility"] = audit_decision_plausibility(run, _previous_for_plausibility)
    if not run["decision_plausibility"].get("ok"):
        raise RuntimeError(
            "Beslutningsplausibilitet feilet: "
            + "; ".join(run["decision_plausibility"].get("errors") or [])
        )
    run.pop("report_document", None)
    run.pop("decision_report", None)

    # Persist the domain result exactly once. Every downstream consumer receives
    # a view of this immutable record, not a separately assembled copy.
    from autonomi_core.learning_reporting import canonical_payload, publish_canonical_top_picks, save_canonical_result
    report_path_hint = (SUMMARIES_DIR / safe_report_filename(run, "pdf")) if job.save_pdf else (RUNS_DIR / f"{run_id}.json")
    emit("REPORT", 0, 3, "Kontrollerer rapportlagring og filbaner")
    try:
        run["report_storage_preflight"] = report_storage_preflight(run_id, report_path_hint)
        ensure_report_document(run, previous)
        canonical_record = save_canonical_result(run)
        canonical_run = canonical_payload(canonical_record)
        run["canonical_result"] = dict(canonical_run["canonical_result"])
        emit("REPORT", 0, 1, "Genererer rapport og lagrer resultat")
        if job.save_pdf:
            pdf_path = SUMMARIES_DIR / safe_report_filename(run, "pdf")
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_bytes = build_main_pdf(canonical_run)
            pdf_path.write_bytes(pdf_bytes)
            run["pdf_path"] = str(pdf_path)
            technical_pdf_path = pdf_path.with_name(pdf_path.stem + "_technical.pdf")
            technical_pdf_bytes = build_technical_pdf(canonical_run)
            technical_pdf_path.write_bytes(technical_pdf_bytes)
            run["technical_pdf_path"] = str(technical_pdf_path)
            run["technical_pdf_name"] = technical_pdf_path.name
            from public_report_store import publish_durable_pdf
            publish_durable_pdf(
                run, technical_pdf_bytes, token_field="technical_report_token",
                filename_field="technical_pdf_name", document_kind="technical",
            )
            run["technical_pdf_delivery"] = {
                "generated": True, "validated": _valid_pdf_bytes(technical_pdf_bytes),
                "durable": bool(run.get("technical_report_token")),
            }
            publish_pdf(run, pdf_bytes)
            run["report_url"] = report_public_url(run)
            run["pdf_delivery"] = {
                "required": True, "generated": True,
                "validated": _valid_pdf_bytes(pdf_bytes),
                "published": bool(run.get("public_pdf_name")),
                "report_url_available": bool(run.get("report_url")),
            }
        else:
            run["pdf_delivery"] = {
                "required": False, "generated": False, "validated": False,
                "published": False, "report_url_available": False,
            }
        emit("REPORT", 1, 3, "Rapportfil er ferdig; lagrer rapport og historikk")
        _write(RUNS_DIR / f"{run_id}.json", run)
        if trigger != "REVALIDATION":
            _write(LATEST_PATH, run)
        _write(SUMMARIES_DIR / f"{run_id}.json", {k: run[k] for k in ("run_id", "created_at", "job_name", "markets", "summary", "changes", "errors")})
        archive_view = dict(canonical_run)
        archive_view.update({key: run.get(key) for key in (
            "pdf_path", "public_pdf_name", "public_report_token", "report_url",
            "technical_pdf_path", "technical_pdf_name", "technical_report_token",
            "technical_pdf_delivery",
        )})
        archive_report(archive_view)
        persistence = verify_report_persistence(run_id)
        if not persistence.get("ok"):
            raise RuntimeError(str(persistence.get("error") or "Rapportarkivet kunne ikke bekreftes"))
        run["persistence"] = persistence
        try:
            from historical_learning import register_run
            run["historical_learning"] = {"snapshots_created": register_run(canonical_run), "mode": "DESCRIPTIVE_ONLY", "result_id": canonical_record["result_id"]}
            _write(RUNS_DIR / f"{run_id}.json", run)
        except Exception as exc:
            run["historical_learning"] = {"snapshots_created": 0, "error": str(exc), "mode": "DESCRIPTIVE_ONLY"}
        emit("REPORT", 2, 3, "Rapport, arkiv og historikk er lagret; kontrollerer varsling")
        notification_view = dict(canonical_run)
        notification_view.update({key: run.get(key) for key in (
            "pdf_path", "public_pdf_name", "public_report_token", "report_url", "trigger", "test_run",
            "suppress_notifications", "scheduled_for",
        )})
        from autonomi_core.runtime.full_execution import pre_notification_gate
        run["portfolio_assessment_contract"] = reconcile_portfolio_assessment(run)
        delivery_gate = pre_notification_gate(run)
        delivery_override = _scheduled_report_delivery_override(job, run, delivery_gate)
        if delivery_gate.get("ok") or delivery_override.get("allowed"):
            if delivery_override.get("allowed"):
                run["delivery_limitation"] = delivery_override
                notification_view["delivery_limitation"] = delivery_override
            notify_ok, notify_detail = _notification(job, notification_view)
            notify_attempted = bool(job.notify_pushover and not run.get("suppress_notifications"))
        else:
            notify_ok = False
            notify_attempted = False
            notify_detail = "Ikke sendt: Autonomi-forutsetning feilet (" + ", ".join(delivery_gate.get("failed_stages") or []) + ")"
        run["pre_notification_gate"] = delivery_gate
        run["notification_delivery_override"] = delivery_override
        status_label = "Sendt" if notify_ok else ("Ikke sendt" if not notify_attempted else "Feilet")
        run["notification"] = {
            "sent": notify_ok, "attempted": notify_attempted, "detail": notify_detail,
            "status_label": status_label, "report_url": report_public_url(run),
            "required": bool(job.notify_pushover and not run.get("suppress_notifications")),
            "test_run": bool(run.get("test_run")),
        }
        # v19.0.17: the first PDF is generated before the notification step so the
        # public URL can be included in Pushover. Regenerate once after the
        # notification decision so the PDF itself explains whether Pushover was sent,
        # skipped or failed.
        if job.save_pdf and run.get("pdf_path"):
            try:
                pdf_bytes = build_main_pdf(run)
                Path(str(run["pdf_path"])).write_bytes(pdf_bytes)
                publish_pdf(run, pdf_bytes)
                run["report_url"] = report_public_url(run)
                run["pdf_delivery"] = {
                    "required": True, "generated": True, "validated": _valid_pdf_bytes(pdf_bytes),
                    "published": bool(run.get("public_pdf_name")),
                    "report_url_available": bool(run.get("report_url")),
                    "regenerated_after_notification": True,
                }
            except Exception as exc:
                errors.append(f"PDF etter Pushover-status kunne ikke regenereres: {exc}")
        notification_is_policy_skip = any(token in str(notify_detail or "") for token in ("Ingen feil", "Ingen kvalifiserende", "deaktivert", "Duplikat blokkert", "Test uten varsling"))
    except Exception as exc:
        context = record_report_failure(run_id, report_path_hint, exc, stage="REPORT")
        try:
            emit(
                "REPORT", 0, 3,
                f"Rapportfeil: {context.get('error_type')}: {context.get('error')}",
                error_type=context.get("error_type"), error=context.get("error"),
                report_path=context.get("report_path"), diagnostic_path=context.get("diagnostic_path"),
            )
        except Exception:
            pass
        message = (
            f"REPORT feilet [{context.get('error_type')}]: {context.get('error')}"
            f" · bane: {context.get('report_path') or '-'}"
        )
        raise ReportStageError(message, context=context) from exc
    from autonomi_core.runtime.full_execution import build_full_execution_receipt, prepublication_gate
    run["portfolio_assessment_contract"] = reconcile_portfolio_assessment(run)
    prerequisite_gate = prepublication_gate(run)
    downstream_ok = prerequisite_gate.get("ok") and not bool(run.get("historical_learning", {}).get("error")) and (notify_ok or not job.notify_pushover or notification_is_policy_skip)
    # Final publication commit: reporting, history/learning and required
    # notification must have completed before Dashboard/Top Picks can change.
    run["canonical_top_picks"] = (publish_canonical_top_picks(canonical_record, limit=max(10, int(job.proposal_count or 10)))
                                  if downstream_ok else {"published": False, "reason": "Full Autonomy-forutsetning, etterbehandling eller varsling feilet; siste gyldige Top Picks beholdes", "failed_stages": prerequisite_gate.get("failed_stages")})
    run["full_autonomy_execution"] = build_full_execution_receipt(run)
    if not run["full_autonomy_execution"].get("self_contained"):
        errors.append("Full Autonomy Execution er ufullstendig: " + ", ".join(run["full_autonomy_execution"].get("failed_stages") or []))
    # The documents created before Pushover carry a usable delivery URL, but
    # they are not the authoritative final artifacts. Persist the final error
    # list and execution receipt, then rebuild both PDFs and the archive once.
    run["errors"] = list(errors)
    try:
        run["final_artifact_sync"] = _finalize_completed_report_artifacts(run, previous=previous)
        run["full_autonomy_execution"] = build_full_execution_receipt(run)
    except Exception as exc:
        errors.append(f"Sluttrapportene kunne ikke synkroniseres: {exc}")
        run["errors"] = list(errors)
        run["pdf_delivery"] = {
            **dict(run.get("pdf_delivery") or {}),
            "validated": False,
            "finalized_after_execution_receipt": False,
        }
        run["technical_pdf_delivery"] = {
            **dict(run.get("technical_pdf_delivery") or {}),
            "validated": False,
            "finalized_after_execution_receipt": False,
        }
        run["full_autonomy_execution"] = build_full_execution_receipt(run)
    # v18.9.3: both evaluators inspect the same immutable input in parallel.
    # The Shadow result is observational and cannot publish or execute anything.
    from autonomi_core.runtime.parallel_validation import build_parallel_validation, save_parallel_validation
    parallel = build_parallel_validation(run, total_runtime_seconds=round(time_module.perf_counter() - full_run_started, 3))
    try:
        from historical_learning import register_run as register_validation_run
        shadow_rows = list(parallel.get("shadow_candidates") or [])
        shadow_run = {
            "run_id": f"SHADOW-{run_id}", "created_at": run.get("created_at"), "job_name": run.get("job_name"),
            "report_identity": {"type": "SHADOW_VALIDATION"}, "candidates": shadow_rows, "proposals": shadow_rows,
            "analysis_aborted": False,
        }
        parallel["shadow_learning_snapshots"] = register_validation_run(shadow_run)
    except Exception as exc:
        parallel["shadow_learning_error"] = str(exc)
    run["parallel_validation"] = save_parallel_validation(parallel)
    try:
        from autonomi_core.runtime.parallel_validation import load_parallel_validation_history
        from autonomi_core.discovery_data.controlled_learning import run_controlled_discovery_learning
        run["controlled_discovery_learning"] = run_controlled_discovery_learning(load_parallel_validation_history(100))
    except Exception as exc:
        run["controlled_discovery_learning"] = {"version": "v18.9.4", "error": str(exc), "production_changed": False}

    try:
        if trigger == "SCHEDULED" and not bool(run.get("test_run")):
            from learning_observation_engine import register_report_observations
            learning_observation_plan = register_report_observations(run, commit=False)
        else:
            learning_observation_plan = {"status":"SKIPPED_NON_SCHEDULED","created":0,"committed":False,"production_changed":False,"trade_authorized":False}
    except Exception as exc:
        learning_observation_plan = {"status":"FAILED","error":str(exc)[:500],"production_changed":False,"trade_authorized":False}

    # AW hard release gate: parallel validation and controlled learning are the
    # final domain mutations.  Rebuild the canonical model and every artifact
    # only now, then run the same cross-channel audit used for downloadable
    # report packages.  A mismatch is a report failure, never a green status.
    run["errors"] = list(errors)
    run["full_autonomy_execution"] = build_full_execution_receipt(run)
    run["final_artifact_sync"] = {
        "generated": False,
        "canonicalized_after_all_domain_stages": True,
        "release_gate": "PENDING",
    }
    run.pop("report_document", None)
    run.pop("decision_report", None)
    apply_report_integrity(run)
    try:
        run["final_artifact_sync"] = {
            **dict(run.get("final_artifact_sync") or {}),
            **_finalize_completed_report_artifacts(run, previous=previous),
        }
        from report_export_audit import validate_artifacts
        final_pdf = Path(str(run.get("pdf_path") or "")).read_bytes() if run.get("pdf_path") else b""
        final_json = json.dumps(run, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        final_text = build_text_report(run).encode("utf-8")
        export_gate = validate_artifacts(
            run=run,
            pdf=final_pdf,
            txt=final_text,
            json_bytes=final_json,
        )
        live_integrity = validate_report_integrity(run)
        if not live_integrity.get("ok"):
            raise RuntimeError(
                "Slutt-JSON feilet ny integritetskontroll: "
                + "; ".join(live_integrity.get("errors") or [])
            )
        if not export_gate.get("ok"):
            raise RuntimeError(
                "Sluttkanalene avviker: " + "; ".join(export_gate.get("errors") or [])
            )
        trade_authorization_true_count = sum(
            1 for row in (run.get("candidates") or [])
            if isinstance(row, Mapping) and row.get("trade_authorized") is True
        )
        moderate_trade_authorizations = [
            str(row.get("ticker") or "-") for row in (run.get("candidates") or [])
            if isinstance(row, Mapping)
            and str(row.get("autonomy_outcome_code") or "").upper() == "MODERAT_KJØPSANBEFALING"
            and row.get("trade_authorized") is True
        ]
        if moderate_trade_authorizations:
            raise RuntimeError(
                "Moderate anbefalinger fikk handelsfullmakt: "
                + ", ".join(moderate_trade_authorizations)
            )
        run["final_release_gate"] = {
            "ok": True,
            "integrity_checked_after_all_domain_stages": True,
            "json_integrity": live_integrity,
            "channel_export": export_gate,
            "trade_authorization_true_count": trade_authorization_true_count,
            "moderate_trade_authorization_true_count": len(moderate_trade_authorizations),
        }
        run["final_artifact_sync"]["release_gate"] = "PASSED"
        if str(learning_observation_plan.get("status") or "") == "COMMIT_AFTER_FINAL_GATE":
            try:
                from learning_observation_engine import register_report_observations
                committed_observations = register_report_observations(run, commit=True)
                _audit("LEARNING_OBSERVATIONS_COMMITTED", {"run_id":run_id,"created":int(committed_observations.get("created") or 0),"created_by_group":dict(committed_observations.get("created_by_group") or {}),"production_changed":False})
            except Exception as learning_exc:
                _audit("LEARNING_OBSERVATION_COMMIT_FAILED", {"run_id":run_id,"error":str(learning_exc)[:500],"production_changed":False})
    except Exception as exc:
        errors.append(f"AV sluttport feilet: {exc}")
        run["errors"] = list(errors)
        run["final_release_gate"] = {
            "ok": False,
            "integrity_checked_after_all_domain_stages": True,
            "error": str(exc),
        }
        run["final_artifact_sync"] = {
            **dict(run.get("final_artifact_sync") or {}),
            "release_gate": "FAILED",
        }
        run["report_status"] = {
            **dict(run.get("report_status") or {}),
            "state": "FAILED_VALIDATION",
            "label": "IKKE ENDELIG – SLUTTKONTROLL FEILET",
        }
    from production_readiness import assess_production_readiness
    run["production_readiness"] = assess_production_readiness(run)
    _write(RUNS_DIR / f"{run_id}.json", run)
    # A maintenance revision belongs in its immutable series and archive, but
    # must not masquerade as the latest ordinary 08/14/22 report in the UI.
    if trigger != "REVALIDATION":
        _write(LATEST_PATH, run)
    if trigger != "REVALIDATION":
        job.last_run_at = run["created_at"]
        job.last_completed_at = run["created_at"]
        job.last_scheduled_at = scheduled_for or job.last_scheduled_at
    job.last_notification_status = str((run.get("notification") or {}).get("status_label") or "")
    job.last_status = "FULLFØRT MED MARKEDSFEIL" if partial_market_failure else ("FULLFØRT MED FEIL" if errors else ("OK MED DATAVARSLER" if warnings else "OK"))
    if trigger != "REVALIDATION" and not bool(run.get("test_run")) and not str(job.job_id or "").upper().startswith("MI-AUTONOMY-REPORT-TEST"):
        upsert_job(job)
    history_type = (
        "Test" if run.get("test_run") else
        ("Planlagt" if trigger == "SCHEDULED" else
         ("Revalidering" if trigger == "REVALIDATION" else "Manuell"))
    )
    _append_job_history({
        "job_id": job.job_id, "job_name": job.name, "run_id": run_id,
        "type": history_type,
        "trigger": trigger, "planned_at": scheduled_for or "", "started_at": execution_started_at,
        "report_created_at": run_created_at,
        "completed_at": _now_iso(), "status": "Fullført" if not errors else "Fullført med feil",
        "pdf": bool(run.get("pdf_path")), "report_url": report_public_url(run),
        "pushover_attempted": bool((run.get("notification") or {}).get("attempted")),
        "pushover_sent": bool((run.get("notification") or {}).get("sent")),
        "notification_detail": (run.get("notification") or {}).get("detail", ""),
        "duration_seconds": round(time_module.perf_counter() - full_run_started, 2),
    })
    _audit("JOB_RUN", {"job_id": job.job_id, "run_id": run_id, "trigger": trigger, "errors": errors})
    emit(
        "COMPLETE", 1, 1,
        "Hele kjeden er fullført" if not errors else "Kjeden ble avsluttet med dokumenterte feil",
        run_id=run_id, status="COMPLETED" if not errors else "FAILED",
    )
    return run


def run_job(
    job: JobProfile,
    trigger: str = "MANUAL",
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    force_refresh: bool = False,
    revision_parent: Mapping[str, Any] | None = None,
    send_notifications: bool = True,
    scheduled_for: str | None = None,
) -> dict[str, Any]:
    """Run one report job with a durable end-to-end operational trace."""
    from execution_coordination import report_execution_lock
    from operational_telemetry import (
        begin_run_trace, bind_run_trace, complete_run_trace, mark_run_stage, stable_error_code,
    )
    trace = begin_run_trace(
        kind="REPORT", trigger=trigger, job_id=str(getattr(job, "job_id", "") or ""),
        metadata={
            "job_name": str(getattr(job, "name", "") or ""),
            "markets": list(getattr(job, "markets", []) or []),
            "force_refresh": bool(force_refresh),
            "scheduled_for": str(scheduled_for or ""),
        },
    )
    trace_id = str(trace.get("trace_id") or "")
    mark_run_stage(trace_id, "PREFLIGHT", status="RUNNING", message="Starter forhåndskontroll og klargjøring")
    from newsapi_budget import begin_report_budget, end_report_budget
    report_api_limit = 5 if "TEST" in str(trigger or "").upper() or "TEST" in str(getattr(job, "name", "") or "").upper() else 15
    manual_wait_seconds = 1800 if str(trigger or "").upper().startswith("MANUAL") else 0
    wait_deadline = time_module.monotonic() + manual_wait_seconds
    budget_started = False
    try:
        while True:
            lock_owner = {
                "trigger": str(trigger or ""), "job_id": str(getattr(job, "job_id", "") or ""),
                "job_name": str(getattr(job, "name", "") or ""), "trace_id": trace_id,
                "scheduled_for": str(scheduled_for or ""), "stage": "PREFLIGHT",
            }
            with report_execution_lock(lock_owner) as execution_acquired:
                if execution_acquired:
                    begin_report_budget(report_api_limit, label=f"{trigger}:{getattr(job, 'job_id', '')}")
                    budget_started = True
                    result = _run_job_traced(
                        job, trigger, progress_callback, force_refresh, revision_parent,
                        send_notifications, scheduled_for, trace_id,
                    )
                    result["newsapi_report_budget"] = end_report_budget()
                    budget_started = False
                    return result
            if not execution_acquired:
                from execution_coordination import report_execution_owner
                owner = report_execution_owner()
                if manual_wait_seconds and time_module.monotonic() < wait_deadline:
                    if progress_callback:
                        progress_callback({
                            "phase": "WAITING_FOR_REPORT_LOCK", "completed": 0, "total": 1,
                            "message": "Venter i kø på aktiv rapportkjøring",
                            "lock_owner": owner,
                        })
                    time_module.sleep(5)
                    continue
                owner_label = str(owner.get("job_name") or owner.get("job_id") or owner.get("trigger") or "ukjent rapportkjøring")
                raise RuntimeError(f"Rapportmotoren er opptatt av {owner_label}. Kjøringen ble ikke startet.")
    except Exception as exc:
        if budget_started:
            end_report_budget()
        code = stable_error_code("REPORT", "report_run_failed", "RUN")
        mark_run_stage(trace_id, "FAILED", status="ERROR", message="Rapportkjøringen feilet", error_code=code, error=exc)
        complete_run_trace(trace_id, status="FAILED", error_code=code, error=exc)
        raise
    finally:
        # Runs share the Streamlit web process. Always release cyclic objects
        # and libc arenas, including after cancellation or provider failure.
        try:
            from runtime_memory import release_process_memory
            release_process_memory("report_run_finally")
        except Exception:
            pass


def _run_job_traced(
    job: JobProfile,
    trigger: str,
    progress_callback: Callable[[Mapping[str, Any]], None] | None,
    force_refresh: bool,
    revision_parent: Mapping[str, Any] | None,
    send_notifications: bool,
    scheduled_for: str | None,
    trace_id: str,
) -> dict[str, Any]:
    from operational_telemetry import bind_run_trace, complete_run_trace
    try:
        if progress_callback:
            progress_callback({
                "phase": "START", "completed": 0, "total": 4,
                "message": "Oppstartskontroll: validerer jobb, oppdrag og konfigurasjon",
                "substep": "JOB_AND_MISSION_CONTRACT",
            })
        result = _run_job_impl(
            job, trigger=trigger, progress_callback=progress_callback, force_refresh=force_refresh,
            revision_parent=revision_parent, send_notifications=send_notifications, scheduled_for=scheduled_for,
            _trace_id=trace_id,
        )
        run_id = str(result.get("run_id") or "")
        if run_id:
            bind_run_trace(trace_id, run_id=run_id, report_id=run_id, job_id=str(getattr(job, "job_id", "") or ""))
        result["operations_trace_id"] = trace_id
        complete_run_trace(
            trace_id, status="COMPLETED",
            metrics={
                "errors": len(result.get("errors") or []),
                "warnings": len(result.get("warnings") or []),
                "candidates": len(result.get("candidates") or []),
                "proposals": len(result.get("proposals") or []),
            },
        )
        return result
    except Exception:
        raise


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    try:
        hh, mm = map(int, str(value).split(":"))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        pass
    return None


def _window_slot_due(job: JobProfile, now: datetime, last: datetime | None) -> bool:
    for window in job.scan_windows or []:
        start_v, end_v = _parse_hhmm(window.get("start", "")), _parse_hhmm(window.get("end", ""))
        if not start_v or not end_v:
            continue
        start_dt = datetime.combine(now.date(), time(*start_v), tzinfo=now.tzinfo)
        end_dt = datetime.combine(now.date(), time(*end_v), tzinfo=now.tzinfo)
        if end_dt < start_dt:
            end_dt = end_dt.replace(day=end_dt.day) + timedelta(days=1)
        if not (start_dt <= now <= end_dt):
            continue
        interval = max(5, min(1440, int(window.get("interval_minutes", 30))))
        elapsed = max(0, int((now - start_dt).total_seconds() // 60))
        slot_dt = start_dt + timedelta(minutes=(elapsed // interval) * interval)
        if not last or last < slot_dt:
            return True
    return False


def _due_slot_info(job: JobProfile, now: datetime, *, authoritative_unattended: bool = False) -> dict[str, Any]:
    timeline = schedule_timeline(job, now, authoritative_unattended=authoritative_unattended)
    # A slot is due as soon as the scheduled minute has passed and the
    # last successful/attempted run is older than that planned slot.
    # The user-facing status remains "Venter" until the grace window expires,
    # but the scheduler itself must not wait five minutes before starting.
    due = bool(
        job.enabled
        and timeline.get("previous_planned_utc")
        and not timeline.get("unobserved_after_restart")
        and timeline.get("last_planned_status") not in {"Fullført", "Feil"}
    )
    return {**timeline, "due": due}


def _slot_due(job: JobProfile, now: datetime, *, authoritative_unattended: bool = False) -> bool:
    return bool(_due_slot_info(job, now, authoritative_unattended=authoritative_unattended).get("due"))


def run_due_jobs(now: datetime | None = None, *, authoritative_unattended: bool = False) -> list[dict[str, Any]]:
    now = now or _now()
    results = []
    for job in load_jobs():
        slot = _due_slot_info(job, now, authoritative_unattended=authoritative_unattended)
        due = bool(slot.get("due"))
        _audit("SCHEDULE_CHECK", {
            "job_id": job.job_id,
            "job_name": job.name,
            "enabled": job.enabled,
            "due": due,
            "last_run_at": job.last_run_at,
            "previous_planned_utc": slot.get("previous_planned_utc"),
            "next_planned_utc": slot.get("next_planned_utc"),
            "timezone_name": job.timezone_name,
            "authoritative_unattended": bool(authoritative_unattended),
            "authoritative_slot_eligible": bool(slot.get("authoritative_slot_eligible")),
        })
        if not due:
            continue
        planned_at = str(slot.get("previous_planned_utc") or "")
        job.last_scheduled_at = planned_at
        job.last_attempted_at = _now_iso()
        upsert_job(job)
        _append_job_history({
            "job_id": job.job_id, "job_name": job.name, "type": "Planlagt",
            "planned_at": planned_at, "started_at": job.last_attempted_at,
            "status": "Startet", "pdf": False, "pushover_attempted": False,
            "pushover_sent": False,
        })
        _audit("SCHEDULED_RUN_STARTED", {
            "job_id": job.job_id, "job_name": job.name, "last_run_at": job.last_run_at,
            "planned_at": planned_at,
        })
        try:
            # The 14:00 report exists to catch information published after
            # the 08:00 run while Nordic exchanges are still open. Bypass the
            # normal six-hour cache so this slot always attempts fresh data.
            force_fresh = job.job_id == "MI-REQUIRED-AFTERNOON"
            result = run_job(
                job, trigger="SCHEDULED", scheduled_for=planned_at,
                force_refresh=force_fresh,
            )
            results.append(result)
            _audit("SCHEDULED_RUN_COMPLETED", {
                "job_id": job.job_id, "job_name": job.name, "run_id": result.get("run_id"),
                "status": job.last_status, "planned_at": planned_at,
            })
        except Exception as exc:
            job.last_failed_at = _now_iso()
            job.last_status = "FEIL"
            upsert_job(job)
            _append_job_history({
                "job_id": job.job_id, "job_name": job.name, "type": "Planlagt",
                "planned_at": planned_at, "started_at": job.last_attempted_at,
                "completed_at": job.last_failed_at, "status": "Feil",
                "error": str(exc)[:1000], "pdf": False, "pushover_attempted": False,
                "pushover_sent": False,
            })
            _audit("SCHEDULED_RUN_FAILED", {
                "job_id": job.job_id, "job_name": job.name, "error": str(exc)[:1000],
                "planned_at": planned_at,
            })
            # One failed fixed report must not suppress other reports due in
            # the same cron cycle.  Return a structured failure for telemetry
            # and continue with the remaining jobs.
            results.append({
                "scheduler_result": "FAILED", "job_id": job.job_id,
                "job_name": job.name, "planned_at": planned_at,
                "error": str(exc)[:1000],
            })
            continue
    scheduler_health_snapshot(now)
    return results


def revalidation_blackout_status(now: datetime | None = None) -> dict[str, Any]:
    """Protect the mandatory 08/14/22 reports from maintenance contention."""
    from zoneinfo import ZoneInfo

    current = (now or _now()).astimezone(ZoneInfo(DEFAULT_TIMEZONE))
    minute = current.hour * 60 + current.minute
    # Start well before the due time because a revalidation may use the shared
    # report owner for more than 20 minutes. Keep a post-run recovery margin.
    windows = ((7 * 60 + 15, 9 * 60 + 30, "08:00"),
               (13 * 60 + 15, 15 * 60 + 30, "14:00"),
               (21 * 60 + 15, 23 * 60 + 30, "22:00"))
    for start, end, schedule in windows:
        if start <= minute <= end:
            return {
                "blocked": True, "schedule": schedule,
                "state": "SKIPPED_MANDATORY_REPORT_WINDOW",
                "checked_at": current.isoformat(timespec="seconds"),
            }
    return {"blocked": False, "schedule": "", "state": "ALLOWED",
            "checked_at": current.isoformat(timespec="seconds")}


def revalidate_provisional_reports(
    now: datetime | None = None,
    *,
    limit: int = 1,
) -> dict[str, Any]:
    """Rerun a stored provisional report without overwriting its original revision.

    Revalidation is deliberately conservative: at most one report is rerun per
    unattended cycle by default, a local NewsAPI reserve is respected, and a
    report series is attempted no more than the configured maximum.
    """
    import os

    now = (now or _now()).astimezone(timezone.utc)
    blackout = revalidation_blackout_status(now)
    if blackout["blocked"]:
        return {**blackout, "eligible": 0, "runs": [], "errors": []}
    wait_hours = max(1, int(os.getenv("REPORT_REVALIDATION_HOURS", "6") or 6))
    max_attempts = max(1, int(os.getenv("REPORT_REVALIDATION_MAX_ATTEMPTS", "1") or 1))
    reserve = max(0, int(os.getenv("NEWSAPI_REVALIDATION_RESERVE", "10") or 10))
    try:
        from newsapi_budget import health_snapshot
        budget = health_snapshot()
    except Exception:
        budget = {}
    if budget.get("configured") and int(budget.get("remaining_today") or 0) <= reserve:
        return {
            "state": "SKIPPED_BUDGET_RESERVE",
            "checked_at": now.isoformat(timespec="seconds"),
            "remaining": int(budget.get("remaining_today") or 0),
            "reserve": reserve,
            "runs": [],
        }
    jobs = {job.job_id: job for job in load_jobs()}
    latest_by_series: dict[str, dict[str, Any]] = {}
    for entry in _load_report_archive():
        series = str(entry.get("report_series_id") or entry.get("run_id") or "")
        if series and series not in latest_by_series:
            latest_by_series[series] = dict(entry)
    candidates: list[tuple[datetime, dict[str, Any], dict[str, Any], JobProfile]] = []
    for entry in latest_by_series.values():
        if not entry.get("revalidation_required") and str(entry.get("report_state") or "") != "PROVISIONAL":
            continue
        run = load_archived_run(entry)
        if not run or str(run.get("job_id") or "") == DRAFT_JOB_ID:
            continue
        attempt = int((run.get("revalidation") or {}).get("attempt") or 0)
        if attempt >= max_attempts:
            continue
        job = jobs.get(str(run.get("job_id") or ""))
        if not job:
            continue
        try:
            created = datetime.fromisoformat(str(run.get("created_at") or "").replace("Z", "+00:00"))
            created = created.replace(tzinfo=created.tzinfo or timezone.utc).astimezone(timezone.utc)
        except Exception:
            continue
        if now - created < timedelta(hours=wait_hours):
            continue
        candidates.append((created, entry, run, job))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for _created, entry, parent, job in sorted(candidates, key=lambda item: item[0])[:max(0, int(limit))]:
        try:
            revised = run_job(
                job,
                trigger="REVALIDATION",
                force_refresh=True,
                revision_parent=parent,
                send_notifications=False,
            )
            revised_state = str((revised.get("report_status") or {}).get("state") or "")
            notification_sent = False
            notification_detail = "Revalidering er ferdig; Pushover er ikke påkrevd"
            revised_notification = dict(revised.get("notification") or {})
            revised["notification"] = {
                **revised_notification,
                "sent": False,
                "attempted": False,
                "required": False,
                "terminal": True,
                "terminal_reason": "SUPPRESSED_REVALIDATION",
                "status_label": "Ikke påkrevd",
                "detail": notification_detail,
            }
            _write(RUNS_DIR / f"{revised.get('run_id')}.json", revised)
            results.append({
                "parent_run_id": parent.get("run_id"),
                "run_id": revised.get("run_id"),
                "revision": (revised.get("report_revision") or {}).get("revision_label"),
                "state": revised_state,
                "material_change": (revised.get("change_since_previous") or {}).get("material_change"),
                "notification_sent": notification_sent,
                "notification_detail": notification_detail,
            })
        except Exception as exc:
            errors.append({"run_id": str(parent.get("run_id") or ""), "error": str(exc)[:500]})
    return {
        "state": "COMPLETED" if not errors else "COMPLETED_WITH_ERRORS",
        "checked_at": now.isoformat(timespec="seconds"),
        "eligible": len(candidates),
        "runs": results,
        "errors": errors,
    }



def _manual_report_status_label_v1924(state: Any) -> str:
    return {
        "QUEUED": "Venter på oppstart",
        "RUNNING": "Kjører",
        "STOP_REQUESTED": "Stopper ved neste sikre kontrollpunkt",
        "COMPLETED": "Fullført",
        "FAILED": "Feilet",
        "CANCELLED": "Avbrutt",
        "STALLED": "Fastlåst – stoppmerket",
    }.get(str(state or "").upper(), str(state or "Ikke startet"))


def _render_manual_report_progress_v1924() -> None:
    """Render durable progress for report-center jobs without blocking navigation."""
    import streamlit as st
    from manual_job_background import (
        diagnostic_bundle, force_release, get_active_status_snapshot, is_running,
        publish_diagnostic_download, request_cancel,
    )

    status = get_active_status_snapshot()
    if not status:
        st.caption("Ingen manuell rapportkjøring er aktiv.")
        return
    state = str(status.get("state") or "").upper()
    percent = max(0, min(100, int(status.get("percent") or 0)))
    message = str(status.get("message") or _manual_report_status_label_v1924(state))
    job_name = str(status.get("job_name") or "Rapportjobb")
    execution_id = str(status.get("execution_id") or "-")
    active_stage = str(status.get("active_stage") or status.get("phase") or "PREFLIGHT")

    with st.container(border=True):
        status_col, stage_col, updated_col = st.columns([1.25, 1, 1.25], gap="large")
        status_col.metric("Jobbstatus", _manual_report_status_label_v1924(state))
        stage_col.metric("Aktivt steg", active_stage)
        updated_col.metric("Jobb", job_name)
        st.progress(percent, text=f"{percent} % · {message}")
        completed = [str(value) for value in (status.get("completed_steps") or []) if str(value).strip()]
        if completed:
            st.caption("Fullførte steg: " + " → ".join(completed))
        timezone_name = str(status.get("timezone_name") or DEFAULT_TIMEZONE)
        progress_at = status.get("last_progress_at") or status.get("updated_at")
        heartbeat_at = status.get("worker_heartbeat_at") or status.get("heartbeat_at")
        st.caption(
            f"Kjørings-ID: {execution_id} · Siste fremdrift: "
            f"{local_display(progress_at, timezone_name) if progress_at else '-'} · "
            f"Worker-heartbeat: {local_display(heartbeat_at, timezone_name) if heartbeat_at else '-'}"
        )
        poll_source = str(status.get("ui_poll_source") or "UKJENT")
        st.caption(
            "Automatisk UI-poll: aktiv hvert 2. sekund · "
            f"kilde {poll_source} · lest {local_display(_now_iso(), timezone_name)}"
        )
        stalled_seconds = 0
        try:
            progress_dt = datetime.fromisoformat(str(progress_at).replace("Z", "+00:00")) if progress_at else None
            heartbeat_dt = datetime.fromisoformat(str(heartbeat_at).replace("Z", "+00:00")) if heartbeat_at else None
            if progress_dt and heartbeat_dt:
                if progress_dt.tzinfo is None:
                    progress_dt = progress_dt.replace(tzinfo=timezone.utc)
                if heartbeat_dt.tzinfo is None:
                    heartbeat_dt = heartbeat_dt.replace(tzinfo=timezone.utc)
                stalled_seconds = max(0, int((heartbeat_dt - progress_dt).total_seconds()))
                if stalled_seconds >= 60 and state == "RUNNING":
                    st.warning(
                        f"Worker-prosessen svarer, men aktivt steg har ikke meldt ny fremdrift på "
                        f"{stalled_seconds // 60} min. Markedsfristen vil avbryte hengende datakall kontrollert."
                    )
        except (TypeError, ValueError):
            pass
        if state in {"FAILED", "STALLED"}:
            st.error(str(status.get("error") or "Rapportkjøringen feilet uten registrert feilmelding."))
        elif state == "CANCELLED":
            st.warning(str(status.get("cancel_reason") or message))
        elif state == "COMPLETED":
            st.success("Rapportkjøringen er fullført og lagret.")
        elif is_running(status):
            if st.button("Stopp kjøringen kontrollert", key=f"mi_stop_{execution_id}", width="content"):
                request_cancel(execution_id, requested_by="RAPPORTSENTER")
                _rerun_reports_v19220_rc11(st)
            if stalled_seconds >= 60:
                confirm_release = st.checkbox("Bekreft sikker frigivelse", key=f"mi_release_confirm_{execution_id}")
                if st.button("Frigi fastlåst jobb", disabled=not confirm_release, key=f"mi_release_{execution_id}"):
                    force_release(execution_id, requested_by="RAPPORTSENTER")
                    _rerun_reports_v19220_rc11(st)
        if state in {"FAILED", "STALLED", "CANCELLED"}:
            bundle, filename = diagnostic_bundle(execution_id)
            delivery = publish_diagnostic_download(bundle, filename)
            from mobile_file_delivery import render_mobile_file_delivery
            render_mobile_file_delivery(
                st, url=str(delivery["url"]), filename=filename,
                label="🩺 Åpne diagnosepakke", mime="application/zip", data=bundle,
                key=f"mi_diag_{execution_id}",
            )

    # RC14: a fragment must never trigger an automatic full-app rerun when a
    # job reaches terminal state. Streamlit kept the old fragment DOM while the
    # complete app was appended below it on some browser/Render combinations,
    # which duplicated the whole page. The fragment now owns only its progress
    # area; the report archive updates on the next normal user/page refresh.
    if state in {"COMPLETED", "FAILED", "CANCELLED"} or state == "STALLED":
        st.caption("Rapportarkivet oppdateres ved neste vanlige sideoppdatering. Ingen automatisk helsidererender kjøres.")


def _live_report_progress_body_v19220_rc161() -> None:
    """Render the small, read-only report status region on every fragment tick."""
    _render_manual_report_progress_v1924()


try:
    import streamlit as _st_fragment_rc161
except ImportError:  # Allows non-UI unit tests to import the module.
    _st_fragment_rc161 = None

if _st_fragment_rc161 is not None:
    _fragment_decorator_rc161 = getattr(_st_fragment_rc161, "fragment", None)
    if callable(_fragment_decorator_rc161):
        _live_report_progress_fragment_v19220_rc161 = _fragment_decorator_rc161(run_every=2.0)(
            _live_report_progress_body_v19220_rc161
        )
    elif getattr(_st_fragment_rc161, "__file__", None):
        # A real Streamlit runtime without fragments is a deployment error.
        # Unit tests use a tiny module stub without __file__ and may import the
        # non-UI report functions without installing Streamlit.
        raise RuntimeError("Streamlit-fragment mangler; automatisk rapportfremdrift kan ikke startes")
    else:
        _live_report_progress_fragment_v19220_rc161 = _live_report_progress_body_v19220_rc161
else:
    _live_report_progress_fragment_v19220_rc161 = _live_report_progress_body_v19220_rc161


def _render_replay_export_status_v19220_rc16(status_override: Mapping[str, Any] | None = None) -> None:
    import streamlit as st
    from replay_export_background import get_status, is_running, read_export_bytes

    status = dict(status_override or get_status())
    if not status:
        st.caption("Ingen komplett replay-eksport er startet ennå.")
        return
    state = str(status.get("state") or "").upper()
    percent = max(0, min(100, int(status.get("percent") or 0)))
    with st.container(border=True):
        e1, e2, e3 = st.columns([1, 1, 1.5])
        e1.metric("Eksportstatus", {"QUEUED": "Venter", "RUNNING": "Kjører", "COMPLETED": "Fullført", "FAILED": "Feilet"}.get(state, state or "-"))
        e2.metric("Fremdrift", f"{percent} %")
        e3.metric("Eksport-ID", status.get("execution_id") or "-")
        st.progress(percent, text=str(status.get("message") or "Bygger replay-arkiv"))
        stage = str(status.get("stage") or "KLARGJØRING")
        completed = int(status.get("completed") or 0)
        total = max(1, int(status.get("total") or 1))
        st.caption(f"Aktivt pakkesteg: {stage} · arbeidsenheter {completed}/{total} · automatisk oppdatering hvert 3. sekund")
        if status.get("current_file"):
            st.caption("Behandler: " + str(status.get("current_file")))
        if status.get("worker_heartbeat_at"):
            st.caption("Worker-heartbeat: " + local_display(status.get("worker_heartbeat_at"), DEFAULT_TIMEZONE))
        if state == "FAILED":
            st.error(str(status.get("error") or "Replay-eksporten feilet uten registrert detalj."))
        elif state == "COMPLETED":
            summary = status.get("summary") if isinstance(status.get("summary"), Mapping) else {}
            a, b, c, d, e = st.columns(5)
            a.metric("Rapporter", summary.get("unique_reports_exported", 0))
            b.metric("Full replay", (summary.get("replay_levels") or {}).get("FULL_REPLAY", 0))
            c.metric("Delvis replay", (summary.get("replay_levels") or {}).get("DECISION_REPLAY", 0))
            d.metric("Kun rapport", (summary.get("replay_levels") or {}).get("REPORT_ONLY", 0))
            e.metric("Karantene", summary.get("reports_quarantined", 0))
            if int(summary.get("reports_quarantined") or 0):
                st.warning(
                    f"{int(summary.get('reports_quarantined') or 0)} historiske rapport(er) besto ikke dagens "
                    "offentlige eksportport eller tidsgrense. De er bevart som saniterte karantenevedlegg; "
                    f"{int(summary.get('reports_timed_out') or 0)} ble tidsavbrutt. Resten av arkivet er komplett."
                )
            payload = read_export_bytes(status)
            if payload and bool(status.get("zip_verified", True)):
                if status.get("file_sha256"):
                    st.caption(f"ZIP verifisert · SHA-256: {str(status.get('file_sha256'))[:16]}…")
                st.download_button(
                    "Last ned komplett rapport- og læringsarkiv",
                    data=payload,
                    file_name=str(status.get("filename") or "AI_Aksje_Analyzer_Replay_Export.zip"),
                    mime="application/zip",
                    key="mi_download_complete_replay_export_v19220_rc16",
                    width="stretch",
                )
            else:
                st.warning("Eksporten er registrert som fullført, men ZIP-filen finnes ikke lenger på denne instansen.")
        elif is_running(status):
            st.caption("Eksporten kjører i en separat worker. Rapportvisningen kan brukes mens arkivet bygges.")


def _start_replay_export_callback_v19220_rc1616() -> None:
    """Create the worker before Streamlit processes the fragment rerun."""
    import streamlit as st
    from replay_export_background import start_export

    started = start_export()
    st.session_state["mi_replay_export_start_ack_v19220_rc1616"] = str(started.get("execution_id") or "")


def _replay_export_start_body_v19220_rc1616() -> None:
    """Stable, non-periodic action surface; polling can never replace its click."""
    import streamlit as st
    from replay_export_background import get_status, is_running

    status = get_status()
    st.button(
        "Bygg komplett rapport-, replay- og læringsarkiv (ZIP)",
        key="mi_start_complete_replay_archive_button_v19220_rc1616",
        type="primary",
        width="stretch",
        disabled=is_running(status),
        on_click=_start_replay_export_callback_v19220_rc1616,
    )
    acknowledged_id = str(st.session_state.get("mi_replay_export_start_ack_v19220_rc1616") or "")
    if acknowledged_id and acknowledged_id != str(status.get("execution_id") or ""):
        st.success(f"Start registrert · eksport-ID {acknowledged_id}")
    elif acknowledged_id and is_running(status):
        st.success(f"Eksporten kjører · eksport-ID {acknowledged_id}")


def _replay_export_status_body_v19220_rc1615() -> None:
    """Read-only periodic polling surface."""
    _render_replay_export_status_v19220_rc16()


try:
    _replay_export_start_fragment_v19220_rc1616 = _st_fragment_rc161.fragment(
        _replay_export_start_body_v19220_rc1616
    )
    _replay_export_status_fragment_v19220_rc16 = _st_fragment_rc161.fragment(run_every="3s")(
        _replay_export_status_body_v19220_rc1615
    )
except Exception:
    _replay_export_start_fragment_v19220_rc1616 = _replay_export_start_body_v19220_rc1616
    _replay_export_status_fragment_v19220_rc16 = _replay_export_status_body_v19220_rc1615


def _build_report_package_with_visible_progress_v19220_rc1611(
    st: Any,
    run: Mapping[str, Any],
    *,
    archive_entry: Mapping[str, Any] | None = None,
) -> tuple[bytes, str]:
    """Build one package synchronously while publishing every real work stage."""
    import time
    from report_replay_export import build_single_report_package, single_report_package_filename

    started = time.monotonic()
    progress = st.progress(0, text="Starter rapportpakken …")
    detail = st.empty()

    def update(done: int, total: int, message: str) -> None:
        percent = max(0, min(100, int(int(done) / max(1, int(total)) * 100)))
        progress.progress(percent, text=f"{percent} % · {message}")
        detail.caption(
            f"Aktivt steg: {message} · arbeidsenheter {int(done)}/{max(1, int(total))} "
            f"· kjørt i {time.monotonic() - started:.1f} sekunder"
        )

    payload, _manifest = build_single_report_package(
        run,
        archive_entry=archive_entry,
        progress_callback=update,
    )
    update(12, 12, "Rapportpakken er ferdig og verifisert")
    detail.success(f"ZIP klar etter {time.monotonic() - started:.1f} sekunder.")
    return payload, single_report_package_filename(run)


def _render_quick_report_archive_v19220_rc1618(st: Any) -> None:
    """Fast default workspace: no scheduler, history, analytics or report bodies."""
    import pandas as pd

    st.markdown("### 📦 Hurtigarkiv")
    st.caption(
        "Starter komplett rapport-, replay- og læringseksport uten å laste jobbprofiler, historikk, "
        "Accuracy Analytics, Drift, PDF-er eller rapportdetaljer i brukerflaten."
    )
    _replay_export_start_fragment_v19220_rc1616()
    _replay_export_status_fragment_v19220_rc16()
    archive = _load_report_archive()
    st.metric("Rapporter registrert", len(archive))
    latest_rows = []
    for row in archive[:20]:
        latest_rows.append({
            "Rapport": row.get("report_label") or "Rapport",
            "Jobb": row.get("job_name") or "-",
            "Tid": row.get("created_at_local") or local_display(
                row.get("created_at"), str(row.get("timezone_name") or DEFAULT_TIMEZONE)
            ),
            "Status": row.get("report_status_label") or row.get("report_state") or "Eldre rapport",
        })
    if latest_rows:
        st.dataframe(pd.DataFrame(latest_rows), width="stretch", hide_index=True)
        st.caption("Viser kun lett metadata for de 20 nyeste rapportene. Ingen rapportfiler er lastet.")


def _render_priority_candidate_cards_v19220_rc1631t(st, candidates: Sequence[Mapping[str, Any]]) -> None:
    """Render readable responsive cards without Streamlit column overflow."""
    cards: list[str] = []
    for index, raw_candidate in enumerate(candidates, 1):
        candidate = dict(raw_candidate or {})
        strengths = {
            "AI Discovery": candidate.get("discovery_score", 0),
            "Fundamentaler": candidate.get("fundamental_score", 0),
            "Research": candidate.get("research_score", 0),
            "Validering": candidate.get("validation_score", 0),
            "Porteføljetilpasning": candidate.get("portfolio_fit_score", 0),
            "Insider": (candidate.get("raw") or {}).get("insider_score", 50),
        }
        strongest = max(strengths, key=lambda key: float(strengths[key] or 0))
        ticker = html_escape(str(candidate.get("ticker") or "-"))
        market = html_escape(str(candidate.get("market") or "-"))
        display_name = html_escape(str(candidate.get("name") or candidate.get("ticker") or "-"))
        confidence = float(
            candidate.get("decision_confidence")
            or _mapping(candidate.get("confidence_profile")).get("decision_confidence")
            or 0
        )
        outcome = html_escape(str(
            candidate.get("autonomy_outcome_label")
            or decision_label(candidate.get("autonomy_outcome_code") or candidate.get("portfolio_action"))
        ))
        next_action = html_escape(str(candidate.get("automatic_next_action") or "Vurderes automatisk på nytt ved neste relevante kjøring."))
        cards.append(
            '<article class="mi-priority-card-v19220rc1631t">'
            f'<div class="mi-priority-rank-v19220rc1631t">PRIORITET {index}</div>'
            f'<h3>{display_name}</h3><div class="mi-priority-market-v19220rc1631t">{ticker} · {market}</div>'
            '<dl>'
            f'<div><dt>Score</dt><dd>{float(candidate.get("investment_score") or 0):.2f}</dd></div>'
            f'<div><dt>Beslutningskonfidens</dt><dd>{confidence:.1f} %</dd></div>'
            f'<div><dt>Risiko</dt><dd>{float(candidate.get("risk_score") or 0):.1f}</dd></div>'
            f'<div><dt>Foreslått vekt</dt><dd>{float(candidate.get("proposed_position_pct") or 0):.2f} %</dd></div>'
            f'<div class="mi-priority-wide-v19220rc1631t"><dt>Sterkeste faktor</dt><dd>{html_escape(component_label(strongest))} {float(strengths[strongest] or 0):.1f}</dd></div>'
            '</dl>'
            '<div class="mi-priority-section-v19220rc1631t"><strong>Autonomiutfall</strong>'
            f'<p>{outcome}</p></div>'
            '<div class="mi-priority-section-v19220rc1631t"><strong>Neste handling</strong>'
            f'<p>{next_action}</p></div>'
            '</article>'
        )
    st.markdown('<div class="mi-priority-grid-v19220rc1631t">' + "".join(cards) + '</div>', unsafe_allow_html=True)


def render_market_intelligence() -> None:
    import pandas as pd
    import streamlit as st
    install_browser_timezone_bootstrap()

    st.markdown("""<style>
    div[data-baseweb="tab-list"] button {font-size: 16px !important; font-weight: 600 !important; padding: 10px 18px !important;}
    div[data-baseweb="tab-list"] {gap: 8px !important;}
    label, div[data-testid="stWidgetLabel"] p {font-size: 14px !important; font-weight: 600 !important;}
    div[data-baseweb="select"] *, div[data-baseweb="input"] input, .stTextInput input {font-size: 15px !important;}
    button[kind] p {font-size: 15px !important;}
    @media (max-width: 768px) {
      div[data-baseweb="tab-list"] button {font-size: 16px !important; padding: 12px 14px !important; min-height: 46px !important;}
      label, div[data-testid="stWidgetLabel"] p {font-size: 16px !important;}
      .stNumberInput, .stSelectbox, .stMultiSelect {margin-bottom: 10px !important;}
      div[data-testid="stHorizontalBlock"] {gap: 0.75rem !important;}
      .stDataFrame, div[data-testid="stDataFrame"] {max-width:100% !important; overflow-x:auto !important;}
      button[kind] {min-height:44px !important;}
      .mi-mobile-card {overflow-wrap:anywhere; word-break:normal;}
    }
    .mi-chip {display:inline-block; padding:.15rem .45rem; border:1px solid rgba(148,163,184,.45); border-radius:999px; margin:.1rem .15rem .1rem 0; overflow-wrap:anywhere;}
    div[data-testid="stHorizontalBlock"] .stButton > button {min-height:34px !important; height:auto !important; padding:.35rem .72rem !important;}
    div[data-testid="stCheckbox"] {margin:.20rem 0 .38rem 0 !important; min-height:34px !important;}
    div[data-testid="stCheckbox"] label {align-items:flex-start !important; line-height:1.35 !important; padding-top:.08rem !important;}
    .mi-settings-heading {font-size:1rem; font-weight:800; line-height:1.35; margin:0 0 .75rem 0; padding-bottom:.45rem; border-bottom:1px solid rgba(148,163,184,.28);}
    .mi-settings-help {margin:.15rem 0 .7rem 0; opacity:.82; line-height:1.4;}
    .mi-priority-grid-v19220rc1631t {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin:.7rem 0 1.2rem;}
    .mi-priority-card-v19220rc1631t {min-width:0;padding:1rem;border:1px solid rgba(148,163,184,.42);border-radius:16px;background:rgba(15,23,42,.48);overflow:hidden;}
    .mi-priority-card-v19220rc1631t h3 {margin:.22rem 0 .05rem;font-size:1.28rem;overflow-wrap:anywhere;}
    .mi-priority-rank-v19220rc1631t {font-size:.78rem;font-weight:800;letter-spacing:.055em;opacity:.82;}
    .mi-priority-market-v19220rc1631t {font-size:.86rem;opacity:.75;margin-bottom:.75rem;overflow-wrap:anywhere;}
    .mi-priority-card-v19220rc1631t dl {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem;margin:0;}
    .mi-priority-card-v19220rc1631t dl>div {min-width:0;padding:.55rem .62rem;border-radius:10px;background:rgba(15,23,42,.58);}
    .mi-priority-card-v19220rc1631t dt {font-size:.74rem;line-height:1.25;opacity:.72;overflow-wrap:anywhere;}
    .mi-priority-card-v19220rc1631t dd {margin:.12rem 0 0;font-size:.98rem;font-weight:750;line-height:1.25;overflow-wrap:anywhere;}
    .mi-priority-wide-v19220rc1631t {grid-column:1/-1;}
    .mi-priority-section-v19220rc1631t {margin-top:.7rem;padding-top:.65rem;border-top:1px solid rgba(148,163,184,.25);overflow-wrap:anywhere;word-break:normal;}
    .mi-priority-section-v19220rc1631t strong {font-size:.78rem;opacity:.75;}
    .mi-priority-section-v19220rc1631t p {margin:.18rem 0 0;line-height:1.42;}
    .mi-contract-grid-v19220rc1631t {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin:.5rem 0 1rem;}
    .mi-contract-grid-v19220rc1631t>div {min-width:0;padding:.72rem .8rem;border:1px solid rgba(148,163,184,.4);border-radius:14px;background:rgba(15,23,42,.4);}
    .mi-contract-grid-v19220rc1631t span {display:block;font-size:.82rem;line-height:1.25;opacity:.76;overflow-wrap:anywhere;}
    .mi-contract-grid-v19220rc1631t strong {display:block;margin-top:.28rem;font-size:1.15rem;}
    @media (max-width: 980px) {.mi-priority-grid-v19220rc1631t {grid-template-columns:repeat(2,minmax(0,1fr));}}
    @media (max-width: 768px) {
      .mi-priority-grid-v19220rc1631t {grid-template-columns:1fr;gap:.8rem;}
      .mi-priority-card-v19220rc1631t {padding:.9rem;}
      .mi-contract-grid-v19220rc1631t {grid-template-columns:repeat(2,minmax(0,1fr));}
    }
    </style>""", unsafe_allow_html=True)
    st.markdown("#### 📊 Rapportsenter · Investor Edition")
    from navigation_state import (
        REPORT_SURFACE_LABEL_BY_SLUG_V19220_RC1631T,
        REPORT_SURFACE_SLUG_BY_LABEL_V19220_RC1631T,
        get_global_navigation_state,
        set_global_navigation_state,
    )
    report_surface_key = "mi_report_surface_v19220_rc1631t"
    if report_surface_key not in st.session_state:
        route_subtab = str(get_global_navigation_state(st).get("subtab") or "")
        restored_surface = REPORT_SURFACE_LABEL_BY_SLUG_V19220_RC1631T.get(route_subtab, "")
        if not restored_surface:
            legacy_workspace = str(st.session_state.get("mi_report_workspace_v19220_rc1618") or "")
            legacy_surface = str(st.session_state.get("mi_full_center_surface_v19220_rc1620") or "")
            if legacy_workspace == "Hurtigarkiv og komplett ZIP":
                restored_surface = "Hurtigarkiv og komplett ZIP"
            elif legacy_surface in {"Kjøring og fremdrift", "Rapporter, historikk og avansert"}:
                restored_surface = legacy_surface
        st.session_state[report_surface_key] = restored_surface or "Rapporter, historikk og avansert"
    report_surface_v19220_rc1631t = st.radio(
        "Rapportområde",
        ["Rapporter, historikk og avansert", "Kjøring og fremdrift", "Hurtigarkiv og komplett ZIP"],
        horizontal=True,
        key=report_surface_key,
        help="Ett direkte valg erstatter de to tidligere menynivåene. Bare valgt område lastes.",
    )
    report_surface_slug = REPORT_SURFACE_SLUG_BY_LABEL_V19220_RC1631T[report_surface_v19220_rc1631t]
    set_global_navigation_state(
        st, nav="autonomy", group="Autonomi", panel="🧠 Autonomi – Kontrollsenter",
        tab="reports", subtab=report_surface_slug,
    )
    if report_surface_v19220_rc1631t == "Hurtigarkiv og komplett ZIP":
        _render_quick_report_archive_v19220_rc1618(st)
        return
    st.caption("Kjør utkast og manglende faste rapporter fra ett kompakt handlingsområde. Planlegging, historikk og avanserte valg ligger lenger ned.")
    # The web process is display/control only. Authoritative scheduled work is
    # owned by scheduled_runner.py in Render Cron and never starts on login.
    try:
        from scheduled_runner import load_unattended_state
        unattended = load_unattended_state()
        if unattended.get("state") == "RUNNING":
            st.caption("⏳ Den uavhengige cron-jobben kontrollerer planlagte rapporter.")
        elif unattended.get("state") == "FAILED":
            st.warning(f"Siste uavhengige planleggerkontroll feilet: {unattended.get('error') or 'ukjent feil'}")
    except Exception:
        pass

    # The report center follows the operator workflow deliberately:
    # status -> actions -> latest reports -> history -> advanced planning.
    quick_jobs = load_jobs()
    health = scheduler_health_snapshot(persist=False, jobs=quick_jobs)
    from manual_job_background import get_active_status, is_running, start_manual_job
    active_manual_status = get_active_status()
    manual_job_running = is_running(active_manual_status)

    with st.container(border=True):
        st.markdown("##### 1. Status for planlagte rapporter")
        next_job = health.get("next") or {}
        status_next, status_active, status_missed, status_unobserved = st.columns([2, 1, 1, 1])
        status_next.metric(
            "Neste planlagte kjøring",
            local_display(next_job.get("next_planned_utc"), str(next_job.get("timezone_name") or DEFAULT_TIMEZONE)) if next_job else "-",
        )
        status_active.metric("Aktive jobber", health.get("active_jobs", 0))
        status_missed.metric("Mistet", len(health.get("missed") or []))
        unobserved_jobs = health.get("unobserved_after_restart") or []
        status_unobserved.metric("Ikke vurdert", len(unobserved_jobs))
        required_next = list(health.get("required_next") or [])
        if required_next:
            fixed_columns = st.columns(3)
            fixed_labels = {
                "MI-REQUIRED-MORNING": "Fast morgenrapport",
                "MI-REQUIRED-AFTERNOON": "Fast ettermiddagsrapport",
                "MI-REQUIRED-EVENING": "Fast kveldsrapport",
            }
            for column, row in zip(fixed_columns, required_next):
                column.metric(
                    fixed_labels.get(str(row.get("job_id") or ""), str(row.get("job_name") or "Fast rapport")),
                    local_display(row.get("next_planned_utc"), str(row.get("timezone_name") or DEFAULT_TIMEZONE)),
                )
        if unobserved_jobs:
            st.info(
                f"{len(unobserved_jobs)} planlagt(e) tidspunkt lå før denne serverprosessen startet. "
                "De er ikke merket som mistet og startes ikke automatisk i ettertid."
            )
        missed_jobs = health.get("missed") or []
        if not missed_jobs:
            st.caption("Ingen manglende planlagte rapporter er registrert.")
        for missed in missed_jobs:
            job = next((item for item in quick_jobs if item.job_id == missed.get("job_id")), None)
            if not job:
                continue
            missed_text, missed_action = st.columns([5, 1])
            missed_text.warning(
                f"{job.name}: planlagt kjøring {local_display(missed.get('previous_planned_utc'), job.timezone_name)} "
                "ble ikke registrert som startet/fullført."
            )
            if missed_action.button("Kjør manglende rapport nå", key=f"mi_catchup_{job.job_id}", width="content", disabled=manual_job_running):
                started = start_manual_job(
                    job,
                    trigger="MISSED_SCHEDULE_CATCHUP",
                    force_refresh=False,
                    scheduled_for=str(missed.get("previous_planned_utc") or ""),
                )
                execution_id = str(started.get("execution_id") or "")
                st.session_state["mi_active_execution_v1924"] = execution_id
                _rerun_reports_v19220_rc11(st)
        delivery_ledger = required_report_delivery_ledger()
        st.markdown("**Dagens obligatoriske rapporter**")
        st.dataframe([{
            "Rapport": row["name"], "Tid": row["schedule"], "Status": row["status"],
            "PDF": "Ja" if row["pdf_created"] else "Nei",
            "Lagring": "Ja" if row["stored"] else "Nei",
            "Pushover": "Sendt" if row["pushover_sent"] else "Ikke sendt",
            "Rapport-ID": row["run_id"] or "-",
        } for row in delivery_ledger["rows"]], width="stretch", hide_index=True)

    with st.container(border=True):
        st.markdown("##### 2. Handlinger")
        morning_job = next((j for j in quick_jobs if "morgen" in str(j.name).casefold()), None)
        afternoon_job = next((j for j in quick_jobs if "ettermiddag" in str(j.name).casefold()), None)
        evening_job = next((j for j in quick_jobs if any(x in str(j.name).casefold() for x in ["kveld", "evening"])), None)
        q1, q2, q3, q4 = st.columns(4, gap="large")
        if q1.button("📄 Nytt utkast", key="mi_quick_draft_v1924", type="primary", width="content", disabled=manual_job_running):
            from autonomy_overview import start_shared_manual_draft_job
            started = start_shared_manual_draft_job(trigger="MANUAL_DRAFT_TEST")
            execution_id = str(started.get("execution_id") or "")
            st.session_state["mi_active_execution_v1924"] = execution_id
            st.success("Utkastkjøringen er startet i samme motor som Autonomi Oversikt. Fremdriften oppdateres automatisk under.")
        if q2.button("🌅 Kjør morgenanalyse", key="mi_quick_morning_v1924", width="content", disabled=manual_job_running or morning_job is None):
            started = start_manual_job(
                morning_job, trigger="MANUAL_REPORT_CENTER", force_refresh=False,
            )
            execution_id = str(started.get("execution_id") or "")
            st.session_state["mi_active_execution_v1924"] = execution_id
            _rerun_reports_v19220_rc11(st)
        if q3.button("☀️ Kjør ettermiddagsanalyse", key="mi_quick_afternoon_v19220_rc1631", width="content", disabled=manual_job_running or afternoon_job is None):
            started = start_manual_job(
                afternoon_job, trigger="MANUAL_REPORT_CENTER", force_refresh=False,
            )
            execution_id = str(started.get("execution_id") or "")
            st.session_state["mi_active_execution_v1924"] = execution_id
            _rerun_reports_v19220_rc11(st)
        if q4.button("🌇 Kjør kveldsanalyse", key="mi_quick_evening_v1924", width="content", disabled=manual_job_running or evening_job is None):
            started = start_manual_job(
                evening_job, trigger="MANUAL_REPORT_CENTER", force_refresh=False,
            )
            execution_id = str(started.get("execution_id") or "")
            st.session_state["mi_active_execution_v1924"] = execution_id
            _rerun_reports_v19220_rc11(st)
        unavailable = []
        if morning_job is None:
            unavailable.append("morgenanalyse")
        if afternoon_job is None:
            unavailable.append("ettermiddagsanalyse")
        if evening_job is None:
            unavailable.append("kveldsanalyse")
        if unavailable:
            st.caption("Ikke konfigurert som aktiv jobbprofil: " + ", ".join(unavailable) + ". Opprett eller aktiver profilen under avanserte innstillinger.")
        # RC16.2: Rapporter uses the exact same live progress fragment as
        # Autonomi Oversikt. Do not maintain a second polling implementation.
        from autonomy_overview import render_shared_manual_job_progress
        render_shared_manual_job_progress(
            allow_quick_start=False,
            refresh_app_on_terminal=False,
        )

    if report_surface_v19220_rc1631t == "Kjøring og fremdrift":
        st.info("Lett fremdriftsvisning er aktiv. Velg «Rapporter, historikk og avansert» over når du faktisk trenger de tunge panelene.")
        return

    with st.container(border=True):
        st.markdown("##### 3. Siste rapporter")
        tab_latest = st.container()
        tab_reports = st.expander("Rapportarkiv og nedlastinger", expanded=False)

    with st.container(border=True):
        st.markdown("##### 4. Historikk")
        tab_history = st.container()

    with st.expander("5. Planlegging og avanserte innstillinger", expanded=False):
        from report_test_mode import build_test_job, load_report_test_mode, set_report_test_mode
        test_state = load_report_test_mode()
        with st.container(border=True):
            st.markdown("##### 🧪 Pushover-test av Autonomi-rapporter")
            st.caption(
                "Kjører en tydelig merket testrapport hvert 30. minutt via Render Cron. "
                "Testen kan ikke utføre ekte eller ordinære kjøp. Den kjører den virkelige, "
                "isolerte LEARNING_ONLY-kjeden og kan opprette små teoretiske læringsobservasjoner."
            )
            requested_test_mode = st.checkbox(
                "Aktiver testrapport med Pushover hvert 30. minutt",
                value=bool(test_state.get("enabled")), key="mi_report_test_mode_v19220_rc1623",
            )
            if requested_test_mode != bool(test_state.get("enabled")):
                test_state = set_report_test_mode(requested_test_mode)
                st.success("Rapporttest er aktivert." if requested_test_mode else "Rapporttest er avsluttet.")
            tm1, tm2, tm3, tm4 = st.columns(4)
            tm1.metric("Status", "AKTIV" if test_state.get("enabled") else "AV")
            tm2.metric("Vellykkede tester", f"{int(test_state.get('successes') or 0)}/4")
            tm3.metric("Siste rapport-ID", str(test_state.get("last_report_id") or "-"))
            tm4.metric("Pushover", str(test_state.get("last_notification_status") or "-"))
            st.caption(
                f"Testserie-ID: {test_state.get('series_id') or '-'} · "
                f"Automatiske forsøk: {int(test_state.get('attempts') or 0)} · "
                f"Feil: {int(test_state.get('failures') or 0)}/3"
            )
            st.info(
                f"Fase: {test_state.get('phase') or 'UKJENT'} · "
                f"{test_state.get('status_message') or 'Ingen statusforklaring registrert.'}"
            )
            st.caption(
                f"Sist startet: {local_display(test_state.get('last_started_at')) if test_state.get('last_started_at') else '-'} · "
                f"Sist fullført: {local_display(test_state.get('last_completed_at')) if test_state.get('last_completed_at') else '-'} · "
                f"Neste automatiske forsøk: {local_display(test_state.get('next_due_at')) if test_state.get('next_due_at') else '-'}"
            )
            if test_state.get("expected_result_at") and str(test_state.get("phase") or "") == "RUNNING_FULL_CHAIN":
                st.caption(
                    "Forventet resultat hvis kjeden fullfører normalt: "
                    + local_display(test_state.get("expected_result_at"))
                    + ". 1/4 registreres først etter godkjent PDF, lagring og Pushover."
                )
            if test_state.get("last_error"):
                st.error(f"Siste testfeil: {test_state.get('last_error')}")
            if test_state.get("persistence_error"):
                st.error(f"Statuslagring: {test_state.get('persistence_error')}")
            timeline_rows = list(test_state.get("timeline") or [])
            if timeline_rows:
                with st.expander("Vis automatisk testtidslinje", expanded=False):
                    st.dataframe(timeline_rows[-12:][::-1], width="stretch", hide_index=True)
            test_now, stop_test = st.columns(2)
            if test_now.button("🧪 Kjør én test umiddelbart", key="mi_report_test_now_v19220_rc1623", disabled=manual_job_running):
                started = start_manual_job(
                    build_test_job(), trigger="MANUAL_REPORT_TEST_NOTIFICATION",
                    force_refresh=False, scheduled_for="",
                )
                st.session_state["mi_active_execution_v1924"] = str(started.get("execution_id") or "")
                st.success("Testrapporten er startet i bakgrunnen. Pushover sendes når PDF-en er ferdig.")
                _rerun_reports_v19220_rc11(st)
            st.caption("En umiddelbar manuell test kontrollerer rapport og Pushover, men teller ikke i den automatiske serien 1/4–4/4.")
            if stop_test.button("Stopp og slå av testmodus", key="mi_report_test_stop_v19220_rc1623", disabled=not bool(test_state.get("enabled"))):
                set_report_test_mode(False)
                st.success("Testmodus er slått av. En allerede startet rapport får fullføre; eventuelle posisjoner er kun LEARNING_ONLY.")
                _rerun_reports_v19220_rc11(st)
            st.info("Automatisk sikkerhetsstopp: etter fire vellykkede automatiske tester, tre feil eller fire timer.")
            from report_system_check import load_report_system_check, run_full_system_check
            st.markdown("###### 🩺 Full systemkontroll")
            st.caption("Tester database, rapportlås, PDF-motor, offentlig lenke og Pushover uten markedsskann, porteføljehandling eller læringshandling.")
            if st.button("Kjør systemkontroll", key="mi_report_system_check_v19220_rc1631"):
                with st.spinner("Kontrollerer rapportleveransen …"):
                    st.session_state["mi_report_system_check_result_v19220_rc1631"] = run_full_system_check(send_notification=True)
            system_check = dict(st.session_state.get("mi_report_system_check_result_v19220_rc1631") or load_report_system_check() or {})
            if system_check:
                check_state = str(system_check.get("state") or "UKJENT")
                (st.success if check_state == "PASS" else st.warning if check_state == "DEGRADED" else st.error)(
                    f"Systemkontroll: {check_state} · fullført {local_display(system_check.get('completed_at')) if system_check.get('completed_at') else '-'}"
                )
                if system_check.get("checks"):
                    st.dataframe(system_check.get("checks"), width="stretch", hide_index=True)
        tab_jobs, tab_accuracy, tab_ops = st.tabs(["Jobbprofiler", "Accuracy Analytics", "Drift"])
    with tab_jobs:
        jobs = quick_jobs
        labels = ["Ny jobb"] + [f"{x.name} ({x.job_id})" for x in jobs]
        def _reset_job_editor_state_v19220_rc1631a() -> None:
            """Discard widget values belonging to the previously selected job."""
            exact = {
                "mi_name_v18687", "mi_timezone_v18711", "mi_markets_v18687", "mi_schedules_v18690",
                "mi_window_count_v18690", "mi_allow_weekends_v1870", "mi_days_v1870",
                "mi_modules_v18687", "mi_scan_profile_v18693", "mi_scan_custom_v18693",
                "mi_scan_loaded_v18710", "mi_deep_v18687", "mi_evidence_count_v19220_rc1627",
                "mi_prop_v18687", "mi_push_v1924", "mi_pdf_v1924", "mi_enabled_v1924",
                "mi_report_link_v1924", "mi_top3_push_v1924", "mi_notification_mode_v1924",
                "mi_auto_port_v18690", "mi_auto_learning_v18690", "mi_require_active_v18690",
            }
            prefixes = ("mi_wstart_", "mi_wend_", "mi_wint_")
            for state_key in list(st.session_state):
                if state_key in exact or str(state_key).startswith(prefixes):
                    del st.session_state[state_key]

        selected = st.selectbox(
            "Rediger jobb", labels, key="mi_job_select_v18687",
            on_change=_reset_job_editor_state_v19220_rc1631a,
        )
        editing_job = None if selected == "Ny jobb" else jobs[labels.index(selected)-1]
        # A new-job form is also the persistent auto-saved draft.  Loading that
        # draft prevents Streamlit reruns from replacing a custom limit with 25.
        current = editing_job or load_draft_job()
        name = st.text_input("Jobbnavn", value=current.name if current else "Morgenanalyse", key="mi_name_v18687")
        c1, c2 = st.columns(2)
        with c1:
            detected_timezone = browser_timezone(st)
            timezone_options = list(dict.fromkeys([detected_timezone, *SUPPORTED_TIMEZONES]))
            timezone_name = st.selectbox(
                "Tidssone for tidsplan",
                timezone_options,
                index=timezone_options.index(valid_timezone(current.timezone_name)) if valid_timezone(current.timezone_name) in timezone_options else 0,
                key="mi_timezone_v18711",
                help="Klokkeslett tolkes i denne tidssonen. UTC lagres i databasen; sommer-/vintertid håndteres automatisk.",
            )
            st.caption(f"PC/nettleser oppdaget: {detected_timezone} · lokal tid nå: {local_display(_now_iso(), timezone_name)} · lagres som UTC")
            market_choices = [CORE_MARKET_SCOPE_LABEL, EXTENDED_NORDIC_SCOPE_LABEL, NORDIC_MARKET_SCOPE_LABEL, FULL_MARKET_SCOPE_LABEL] + [x for x in BASE_MARKET_SCOPES if x not in {"Brasil"}]
            market_defaults = canonical_market_profile_selections(current.markets if current else None)
            markets = st.multiselect("Markeder (kan kombineres)", market_choices, default=market_defaults, key="mi_markets_v18687", help="Valgene viser nøyaktig hvilke land som blir skannet. Velg enkeltland eller en eksplisitt landkombinasjon.")
            selected_market_preview = normalize_markets(markets)
            st.caption("Denne kjøringen dekker: " + (", ".join(selected_market_preview) if selected_market_preview else "ingen markeder valgt"))
            schedules = st.multiselect("Faste tidspunkter (kan kombineres)", SCHEDULE_OPTIONS, default=current.schedules if current else ["08:00", "22:00"], key="mi_schedules_v18690")
            st.caption("Skanningsvinduer kjører gjentatte ganger innenfor valgte tidsrom.")
            windows = current.scan_windows if current and current.scan_windows else DEFAULT_SCAN_WINDOWS
            window_count = st.number_input("Antall skanningsvinduer", 0, 4, len(windows), 1, key="mi_window_count_v18690")
            scan_windows = []
            for wi in range(int(window_count)):
                default = windows[wi] if wi < len(windows) else {"start":"08:00","end":"10:00","interval_minutes":30}
                w1,w2,w3 = st.columns(3)
                start_t = w1.time_input(f"Fra {wi+1}", value=time.fromisoformat(default.get("start","08:00")), key=f"mi_wstart_{wi}_v18690")
                end_t = w2.time_input(f"Til {wi+1}", value=time.fromisoformat(default.get("end","10:00")), key=f"mi_wend_{wi}_v18690")
                interval = w3.selectbox(f"Intervall {wi+1}", [15,30,60,120,240], index=[15,30,60,120,240].index(int(default.get("interval_minutes",30))) if int(default.get("interval_minutes",30)) in [15,30,60,120,240] else 1, format_func=lambda x:f"{x} min", key=f"mi_wint_{wi}_v18690")
                scan_windows.append({"start":start_t.strftime("%H:%M"),"end":end_t.strftime("%H:%M"),"interval_minutes":int(interval)})
            allow_weekends = st.checkbox("Tillat helgekjøring", value=bool(current.allow_weekends) if current else False, key="mi_allow_weekends_v1870")
            day_options = WEEKDAY_NAMES if allow_weekends else WEEKDAY_NAMES[:5]
            default_days = [WEEKDAY_NAMES[i] for i in (current.weekdays if current else [0,1,2,3,4]) if WEEKDAY_NAMES[i] in day_options]
            if st.button("Velg mandag–fredag", key="mi_select_weekdays_v1870", width="stretch"):
                st.session_state["mi_days_v1870"] = WEEKDAY_NAMES[:5]
            weekday_names = st.multiselect("Ukedager", day_options, default=default_days, key="mi_days_v1870")
        with c2:
            modules = st.multiselect(
                "Analysemoduler",
                MODULE_OPTIONS,
                default=current.modules if current else MODULE_OPTIONS,
                key="mi_modules_v18687",
                format_func=lambda value: MODULE_LABELS_NO.get(str(value), str(value)),
            )
            current_limit = int(current.scan_limit if current else 25)
            reverse_profile = {value: label for label, value in SCAN_PROFILES.items() if value is not None}
            default_profile = reverse_profile.get(current_limit, "Egendefinert (10–250)")
            scan_state_token = f"{current.job_id if current else 'NEW'}:{current_limit}"
            if st.session_state.get("mi_scan_loaded_v18710") != scan_state_token:
                st.session_state["mi_scan_profile_v18693"] = default_profile
                st.session_state["mi_scan_custom_v18693"] = current_limit
                st.session_state["mi_scan_loaded_v18710"] = scan_state_token
            scan_profile_options = list(SCAN_PROFILES)
            scan_profile_kwargs = {"key": "mi_scan_profile_v18693"}
            if "mi_scan_profile_v18693" not in st.session_state:
                scan_profile_kwargs["index"] = scan_profile_options.index(default_profile)
            scan_profile = st.selectbox("Skanneprofil per marked", scan_profile_options, **scan_profile_kwargs)
            scan_limit = SCAN_PROFILES[scan_profile]
            if scan_limit is None:
                custom_kwargs = {"key": "mi_scan_custom_v18693"}
                if "mi_scan_custom_v18693" not in st.session_state:
                    custom_kwargs["value"] = current_limit
                scan_limit = st.number_input("Egendefinert antall per marked", 10, 250, step=5, **custom_kwargs)
                st.caption("Tillatt område: 10–250 aksjer per marked. 250 er systemets maksimum.")
            st.caption(f"Planlagt maksimum: {int(scan_limit) * len(normalize_markets(markets or ['Norge']))} aksjer ({int(scan_limit)} per marked).")
            if int(scan_limit) == 250:
                st.warning(f"Maksprofil: opptil {250 * len(normalize_markets(markets or ['Norge']))} aksjer. Dette kan gi lang kjøretid og høy API-bruk.")
            deep = st.number_input("Utvidet analyse - totalt antall kandidater", 3, 100, current.deep_count if current else 18, 1, key="mi_deep_v18687")
            evidence_count = st.number_input("Evidenskontroll - global Top N (garantert)", 1, 60, max(MINIMUM_GLOBAL_EVIDENCE_SHORTLIST, min(current.evidence_analysis_count, max(current.deep_count, MINIMUM_GLOBAL_EVIDENCE_SHORTLIST))) if current else 20, 1, key="mi_evidence_count_v19220_rc1631l")
            proposals = st.number_input("Grundig evidenskontroll - totalt antall", 1, 15, min(current.proposal_count, current.deep_count) if current else 5, 1, key="mi_prop_v18687")
        st.markdown("##### Varsling, lagring og aktivering")
        delivery_settings, notification_settings = st.columns(2, gap="large", vertical_alignment="top")
        with delivery_settings:
            with st.container(border=True):
                st.markdown('<div class="mi-settings-heading">Levering og jobbstatus</div>', unsafe_allow_html=True)
                st.markdown('<div class="mi-settings-help">Velg hvordan rapporten leveres og om jobbprofilen skal være aktiv.</div>', unsafe_allow_html=True)
                notify = st.checkbox("Send med Pushover", value=current.notify_pushover if current else True, key="mi_push_v1924")
                save_pdf = st.checkbox("Lagre PDF", value=current.save_pdf if current else True, key="mi_pdf_v1924")
                enabled = st.checkbox("Aktiv jobb", value=editing_job.enabled if editing_job else True, key="mi_enabled_v1924")
        with notification_settings:
            with st.container(border=True):
                st.markdown('<div class="mi-settings-heading">Innhold i varslingen</div>', unsafe_allow_html=True)
                st.markdown('<div class="mi-settings-help">Velg hvilket rapportinnhold som skal følge Pushover-varselet.</div>', unsafe_allow_html=True)
                include_report_link = st.checkbox(
                    "Direkte lenke til PDF",
                    value=current.include_report_link if current else True,
                    key="mi_report_link_v1924",
                    help="På Render brukes tjenestens offentlige adresse automatisk. REPORT_PUBLIC_BASE_URL kan overstyre adressen.",
                )
                include_top3 = st.checkbox(
                    "Top 3 i varsel",
                    value=current.include_top3_in_notification if current else True,
                    key="mi_top3_push_v1924",
                )
        mode_labels = {
            "ALWAYS": "Send alltid når rapporten er ferdig",
            "CHANGES_ONLY": "Bare ved kvalifiserende endringer",
            "ERRORS_ONLY": "Bare ved feil",
        }
        current_mode = _notification_mode(current) if current else "ALWAYS"
        notification_label = st.selectbox(
            "Når skal Pushover sendes?", list(mode_labels.values()),
            index=list(mode_labels).index(current_mode), key="mi_notification_mode_v1924",
        )
        notification_mode = next(key for key, label in mode_labels.items() if label == notification_label)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        global_alert_score = load_global_alert_score()
        min_score = st.number_input(
            "Minste score for varsel", 0, 100, int(global_alert_score), 1,
            key="mi_min_score_v2000",
            help="Gjelder alle nye manuelle og planlagte kjøringer. Pågående kjøringer beholder terskelen de startet med.",
        )
        min_score = save_global_alert_score(float(min_score))
        st.caption("Felles terskel: gjelder neste manuelle kjøring og alle faste jobber. Pågående kjøringer påvirkes ikke.")
        r1, r2 = st.columns(2)
        reset_alerts = r1.button("↺ Tilbakestill varselstandard", key="mi_reset_alerts_v1870", width="stretch")
        reset_all = r2.button("↺ Tilbakestill hele jobbprofilen", key="mi_reset_all_v1870", width="stretch")
        if reset_alerts:
            for key, value in {"mi_push_v1924": True, "mi_notification_mode_v1924": mode_labels["ALWAYS"], "mi_pdf_v1924": True, "mi_min_score_v2000": 80, "mi_report_link_v1924": True, "mi_top3_push_v1924": True}.items(): st.session_state[key] = value
            save_global_alert_score(DEFAULT_GLOBAL_ALERT_SCORE)
            _rerun_reports_v19220_rc11(st)
        if reset_all:
            defaults = load_draft_job()
            defaults.name = "Morgenanalyse"; defaults.markets=[CORE_MARKET_SCOPE_LABEL]; defaults.market_profile=MARKET_PROFILE_CORE; defaults.schedules=["08:00"]; defaults.weekdays=[0,1,2,3,4]; defaults.scan_limit=25; defaults.deep_count=10; defaults.evidence_analysis_count=10; defaults.proposal_count=5; defaults.coverage_profile_version="3.1"; defaults.min_alert_score=80; defaults.allow_weekends=False
            write_persistent_json(DRAFT_STORAGE_KEY, asdict(defaults))
            for key in list(st.session_state):
                if str(key).startswith("mi_"): del st.session_state[key]
            _rerun_reports_v19220_rc11(st)
        st.markdown("##### Etter skanningen")
        o1,o2,o3 = st.columns(3)
        run_auto = o1.checkbox("Kjør teoretisk portefølje", value=current.run_autonomous_portfolio if current else True, key="mi_auto_port_v18690")
        run_learning = o2.checkbox("Kjør kontrollert læring", value=current.run_controlled_learning if current else True, key="mi_auto_learning_v18690")
        require_active = o3.checkbox("Krev aktiv portefølje", value=current.require_active_portfolio if current else True, key="mi_require_active_v18690", help="Når valgt hoppes simulerte handler over dersom porteføljen er pauset.")
        selected_profile = infer_market_profile(markets or ["Norge"], name=name.strip() or "Uten navn")
        draft_job = JobProfile(
            name=name.strip() or "Uten navn", markets=profile_market_selections(selected_profile, markets or ["Norge"]),
            market_profile=selected_profile, schedules=schedules or [],
            weekdays=sorted(set([
                *[WEEKDAY_NAMES.index(x) for x in weekday_names],
                *([5, 6] if allow_weekends else []),
            ])), modules=modules or ["Market Scanner"],
            scan_limit=int(scan_limit), deep_count=int(deep), evidence_analysis_count=min(int(evidence_count), int(deep)), proposal_count=int(proposals), coverage_profile_version="3.0", min_alert_score=float(min_score),
            notify_pushover=notify, notify_only_changes=(notification_mode == "CHANGES_ONLY"), notification_mode=notification_mode, include_report_link=include_report_link,
            include_top3_in_notification=include_top3, allow_weekends=allow_weekends, save_pdf=save_pdf, enabled=False,
            scan_windows=scan_windows, run_autonomous_portfolio=run_auto, run_controlled_learning=run_learning, require_active_portfolio=require_active,
            timezone_name=timezone_name,
            job_id=DRAFT_JOB_ID, created_at=current.created_at if current else _now_iso(),
            last_run_at=current.last_run_at if current else "", last_status="UTKAST",
        )
        save_draft_job(draft_job)
        st.caption("💾 Utkastet lagres automatisk. Testkjøring oppretter ikke eller aktiverer en tidsplan.")

        def _run_visible_test(send_push: bool) -> None:
            progress = st.progress(0, text="Klargjør testkjøring")
            detail_box = st.empty()
            events: list[Mapping[str, Any]] = []
            def ui_progress(event: Mapping[str, Any]) -> None:
                events.append(dict(event))
                try:
                    from manual_job_background import progress_percent
                    pct = int(progress_percent(event))
                except Exception:
                    pct = min(99, max(1, int(100 * float(event.get("completed", 0)) / max(1, float(event.get("total", 1))))))
                message = str(event.get("message") or event.get("phase") or "Kjører")
                progress.progress(min(100, pct), text=message)
                recent = events[-6:]
                detail_box.markdown("\n".join(f"- {'✓' if item is not event else '⟳'} {item.get('message') or item.get('phase')}" for item in recent))
            trigger_name = "MANUAL_DRAFT_TEST_NOTIFICATION" if send_push else "MANUAL_DRAFT_TEST"
            st.session_state["mi_latest_v18687"] = run_job(
                draft_job, trigger=trigger_name, progress_callback=ui_progress,
                send_notifications=bool(send_push),
            )
            progress.progress(100, text="Testkjøringen er fullført")

        b1, b2, b3, b4 = st.columns(4)
        if b1.button("▶ Test uten varsling", type="primary", width="stretch", key="mi_test_draft_no_push_v1914"):
            with st.spinner("Kjører test fra automatisk lagret utkast uten å sende Pushover..."):
                _run_visible_test(False)
            st.success("Testkjøringen er fullført. Pushover ble ikke sendt. Oppsettet er fortsatt bare et utkast.")
            _rerun_reports_v19220_rc11(st)
        if b2.button("🧪 Test med Pushover", width="stretch", key="mi_test_draft_push_v1914"):
            with st.spinner("Kjører test og sender tydelig merket testvarsel..."):
                _run_visible_test(True)
            st.success("Testkjøringen er fullført. Eventuelt varsel er merket som TESTVARSEL.")
            _rerun_reports_v19220_rc11(st)
        if b3.button("Lagre og aktiver tidsplan", width="stretch", key="mi_save_activate_v18692a"):
            same_name = next((x for x in jobs if x.name.strip().casefold() == draft_job.name.strip().casefold()), None)
            target = editing_job or same_name
            job = JobProfile(**{**asdict(draft_job),
                              "name": activated_job_name_v19220_rc1631q(draft_job.name),
                              "job_id": target.job_id if target else f"MIJ-{uuid.uuid4().hex[:10].upper()}",
                              "created_at": target.created_at if target else _now_iso(),
                              "last_run_at": target.last_run_at if target else "",
                              "last_status": target.last_status if target else "ALDRI KJØRT",
                              "enabled": bool(enabled)})
            upsert_job(job)
            st.success("Jobben er lagret. Tidsplanen er aktivert dersom «Aktiv jobb» er valgt.")
            _rerun_reports_v19220_rc11(st)
        if current and b4.button("Slett lagret jobb", width="stretch", key="mi_delete_v18692a"):
            delete_job(current.job_id); st.success("Jobben er slettet. Det automatisk lagrede utkastet beholdes."); _rerun_reports_v19220_rc11(st)
        if jobs:
            st.markdown("##### Lagrede jobbprofiler")
            rows = []
            for job in jobs:
                timeline = schedule_timeline(job)
                rows.append({
                    "Jobb": job.name,
                    "Markeder": ", ".join(job.markets),
                    "Tid": ", ".join(job.schedules),
                    "Aktiv": job.enabled,
                    "Neste planlagt": local_display(
                        timeline.get("next_planned_utc"),
                        str(timeline.get("timezone_name") or DEFAULT_TIMEZONE),
                    ) if timeline.get("next_planned_utc") else "-",
                    "Siste faktisk": local_display(job.last_run_at, job.timezone_name) if job.last_run_at else "-",
                    "Status": job.last_status,
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    latest = st.session_state.get("mi_latest_v18687") or _read(LATEST_PATH, {})
    with tab_latest:
        if not latest:
            st.info("Ingen Scheduled Market Intelligence-rapport er generert ennå.")
        else:
            identity = resolve_report_identity(latest)
            st.markdown(f"### {identity.get('label', 'Rapport')} · {latest.get('job_name', '-')}")
            st.caption(f"Rapporttype: {identity.get('type', '-')} · Kjøring: {latest.get('run_id', '-')}")
            report_state = latest.get("report_status") if isinstance(latest.get("report_status"), Mapping) else {}
            revision = latest.get("report_revision") if isinstance(latest.get("report_revision"), Mapping) else {}
            if report_state.get("state") == "PROVISIONAL":
                st.warning(
                    f"{report_state.get('label')} · {revision.get('revision_label', 'R1')} · "
                    "automatisk revalidering er nødvendig"
                )
            elif report_state:
                st.success(f"{report_state.get('label', 'ENDELIG')} · {revision.get('revision_label', 'R1')}")
            if latest.get("analysis_aborted"):
                st.error("Analyse avbrutt – utilstrekkelige data. Rangeringskort, anbefalinger og porteføljeforslag er deaktivert for denne kjøringen.")
            s = latest.get("summary") or {}; ch = latest.get("changes") or {}
            scan_cfg = latest.get("scan_configuration") or {}
            a,b,c,d,e = st.columns(5)
            a.metric("Skannet", s.get("scanned",0), f"Planlagt maks {scan_cfg.get('planned_maximum', 0)}")
            b.metric("Grundig analysert", s.get("deep_analyzed",0))
            c.metric("Foreløpige modellkandidater", s.get("proposals",0))
            d.metric("Nye", len(ch.get("new",[])))
            e.metric("Forbedret", len(ch.get("improved",[])))
            intelligence = latest.get("executive_intelligence") or executive_intelligence(latest.get("candidates") or [])
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Gjennomsnittsscore", intelligence.get("average_score", 0))
            i2.metric("Høyeste score", intelligence.get("highest_score", 0))
            i3.metric("Unike selskaper", intelligence.get("unique_companies", 0))
            i4.metric("Markeder i Top 10", intelligence.get("markets_in_top10", 0))
            actual_by_market = scan_cfg.get("actual_by_market") or {}
            if actual_by_market:
                st.caption("Faktisk skannet per marked: " + " · ".join(f"{market}: {count}" for market, count in actual_by_market.items()))
            universe_coverage = [row for row in (latest.get("universe_coverage") or []) if isinstance(row, Mapping)]
            if universe_coverage:
                st.markdown("#### Univers- og dekningsrapport")
                coverage_rows = [{
                    "Marked": row.get("market"),
                    "Konfigurert univers": row.get("configured_universe", 0),
                    "Grovskannet": row.get("rough_scanned", 0),
                    "Utvidet analysert": row.get("extended_analyzed", 0),
                    "Evidenskontrollert": row.get("evidence_controlled", 0),
                    "Sektorer med data": row.get("known_sector_coverage", "-"),
                    "Dekning %": row.get("coverage_pct", 0),
                    "Manglende symboler": len(row.get("missing_symbols") or []),
                    "Manglende sektormetadata": len(row.get("missing_sector_metadata") or []),
                    "Kildetype": "Autoritativ børsliste" if row.get("source_authoritative_exchange_master") else "Kontrollert applikasjonsunivers",
                } for row in universe_coverage]
                st.dataframe(pd.DataFrame(coverage_rows), width="stretch", hide_index=True)
                failures = [str(row.get("market")) for row in universe_coverage if row.get("coverage_failure")]
                if failures:
                    st.error("Reell dekningsfeil i: " + ", ".join(failures))
                else:
                    st.success("Hele det konfigurerte universet ble grovskannet.")
                st.caption("Dette dokumenterer applikasjonens kontrolliste, ikke en komplett offisiell børsliste uten separat autoritativ kilde.")
                with st.expander("Vis sektorfordeling, mangler og oppdagelseskontroll", expanded=False):
                    for row in universe_coverage:
                        st.markdown(f"**{row.get('market')}**")
                        st.json({
                            "sektorfordeling": row.get("sector_counts") or {},
                            "manglende_standardsektorer": row.get("missing_canonical_sectors") or [],
                            "manglende_symboler": row.get("missing_symbols") or [],
                            "manglende_sektormetadata": row.get("missing_sector_metadata") or [],
                        })
                    audits = latest.get("detection_audit") or []
                    if audits:
                        st.markdown("**Etterkontroll av observerte vinnere**")
                        st.json(audits)
                gate_audit = [row for row in (latest.get("buy_gate_audit") or []) if isinstance(row, Mapping)]
                if gate_audit:
                    with st.expander("Vis hvorfor kandidater ikke ble BUY", expanded=False):
                        st.dataframe(pd.DataFrame([{
                            "Ticker": row.get("ticker"), "Marked": row.get("market"),
                            "Sektor": row.get("sector"), "Score": row.get("score"),
                            "Terskel": row.get("threshold"), "Handling": row.get("portfolio_action"),
                            "Første blocker": row.get("first_blocker"),
                        } for row in gate_audit]), width="stretch", hide_index=True)
            statuses = latest.get("market_status") or []
            if statuses:
                st.markdown("#### 🌍 Markedsstatus")
                status_cols = st.columns(min(3, len(statuses)))
                for idx, item in enumerate(statuses):
                    icon = "🟢" if item.get("status") == "ÅPEN" else "🔴"
                    status_cols[idx % len(status_cols)].metric(f"{icon} {item.get('market')}", item.get("status"), f"{item.get('local_time')} · {item.get('reason')}")
                refresh = latest.get("data_refresh") or {}
                dates = ", ".join(refresh.get("latest_trade_dates") or []) or "ukjent"
                if refresh.get("live_count", 0):
                    st.info(f"Live data ble hentet. Siste tilgjengelige handelsdato: {dates}.")
            quality = latest.get("data_quality") or {}
            if quality:
                st.progress(float(quality.get("score", 0))/100.0, text=f"Datakvalitet: {quality.get('score',0)} % · {quality.get('label','-')}")
                st.caption("Dette gjelder kurs- og markedsdata, ikke samlet evidens.")
            combined = latest.get("combined_data_quality") or {}
            if combined:
                level = st.success if combined.get("green") else st.warning
                level(
                    f"Samlet beslutningsgrunnlag: {combined.get('status', '-')} · "
                    f"markedsdata gyldig {combined.get('market_data_valid', 0)} · "
                    f"evidens gyldig {combined.get('evidence_valid', 0)} · "
                    f"NewsAPI ratebegrenset {combined.get('news_rate_limited', 0)}"
                )
            contract_summary = latest.get("data_contract") or {}
            if contract_summary:
                st.markdown("#### 🛡️ Freshness & Data Contract")
                contract_items = (
                    ("Kontrollert", contract_summary.get("evaluated", 0)),
                    ("Gyldig for beslutning", contract_summary.get("valid_for_decision", 0)),
                    ("Blokkert", len(contract_summary.get("blocked") or [])),
                    ("Fallback", len(contract_summary.get("fallback") or [])),
                )
                st.markdown(
                    '<div class="mi-contract-grid-v19220rc1631t">'
                    + "".join(
                        f"<div><span>{html_escape(str(label))}</span><strong>{html_escape(str(value))}</strong></div>"
                        for label, value in contract_items
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
                if contract_summary.get("blocked"):
                    st.warning("Beslutningsdelen er stoppet for: " + ", ".join(contract_summary.get("blocked") or []))
            candidates = [] if latest.get("analysis_aborted") else list(latest.get("candidates") or [])
            if candidates:
                from report_channel_consistency import projection_from_run
                channel_projection = projection_from_run(latest)
                by_ticker = {str(row.get("ticker") or "").upper(): dict(row) for row in candidates}
                displayed_candidates = []
                for projected in list(channel_projection.get("review_ranking") or channel_projection.get("ranking") or [])[:3]:
                    row = dict(by_ticker.get(str(projected.get("ticker") or "").upper()) or projected)
                    row["rank"] = projected.get("rank")
                    row["investment_score"] = projected.get("score")
                    row["portfolio_action"] = projected.get("decision")
                    row["autonomy_outcome_label"] = projected.get("decision_label")
                    displayed_candidates.append(row)
                heading = f"#### Prioritert vurderingsrekkefølge 1–3 ({len(displayed_candidates)})"
                st.info("Rangeringen viser hvilke kandidater som bør vurderes først og nærmere. Den er ikke en kjøpsanbefaling.")
                if not latest.get("evidence_ready_top3"):
                    st.caption("Ingen kandidat bestod data- og evidensporten; prioriteringen vises for å styre automatisk oppfølging og eventuell konkret manuell undersøkelse.")
                st.markdown(heading)
                if not displayed_candidates:
                    st.caption("Ingen kandidater er rangert for prioritert oppfølging i denne rapporten.")
                else:
                    _render_priority_candidate_cards_v19220_rc1631t(st, displayed_candidates)
            if latest.get("errors"): st.warning(" | ".join(latest["errors"]))
            st.markdown("#### Top 10")
            table = []
            for x in candidates[:10]:
                strengths = {
                    "AI Discovery": x.get("discovery_score", 0),
                    "Fundamentaler": x.get("fundamental_score", 0),
                    "Research": x.get("research_score", 0),
                    "Validering": x.get("validation_score", 0),
                    "Porteføljetilpasning": x.get("portfolio_fit_score", 0),
                    "Insider": (x.get("raw") or {}).get("insider_score", 50),
                }
                strongest = max(strengths, key=lambda key: float(strengths[key] or 0))
                action = x.get("autonomy_outcome_code") or x.get("portfolio_action") or ("BUY" if x.get("status") == "ANBEFALT FOR VURDERING" else "SKIP")
                table.append({
                    "Rang": x.get("rank"), "Ticker": x.get("ticker"), "Marked": x.get("market"),
                    "Sektor": sector_label(x.get("sector")), "Score": x.get("investment_score"),
                    "Porteføljebeslutning": decision_label(action),
                    "Beslutningskonfidens": x.get("decision_confidence") or _mapping(x.get("confidence_profile")).get("decision_confidence"), "Trend": x.get("trend"),
                    "Datagyldighet": (x.get("data_contract") or {}).get("validity", "UKJENT"),
                    "Datakilde": (x.get("data_contract") or {}).get("source", "UKJENT"),
                    "Endring": x.get("score_delta"), "Risiko": x.get("risk_score"),
                    "Sterkeste faktor": f"{component_label(strongest)} {float(strengths[strongest] or 0):.1f}",
                    "Handling": decision_label(action), "Status": x.get("autonomy_outcome_label") or decision_label(action),
                })
            if table: st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
            handoff = latest.get("autonomy_candidate_handoff") if isinstance(latest.get("autonomy_candidate_handoff"), Mapping) else {}
            if handoff:
                st.markdown("#### Autonomi-kandidatoverlevering")
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("Rapportkandidater", handoff.get("report_candidates", 0))
                h2.metric("Sendt til Autonomi", handoff.get("sent_to_autonomy", 0))
                h3.metric("Autonomi-status", label_for(handoff.get("autonomy_stage_status") or "-"))
                h4.metric("Avvik", "Ja" if handoff.get("mismatch") else "Nei")
                if handoff.get("mismatch"):
                    st.error(handoff.get("warning"))
                elif handoff.get("autonomy_reason"):
                    st.info(handoff.get("autonomy_reason"))
            ranking_explanation = latest.get("ranking_explanation") if isinstance(latest.get("ranking_explanation"), Mapping) else {}
            if ranking_explanation:
                st.markdown("#### Slik leses rangeringene")
                if ranking_explanation.get("note"):
                    st.info(ranking_explanation.get("note"))
                st.dataframe(pd.DataFrame(ranking_explanation.get("ranking_types") or []), width="stretch", hide_index=True)
            delivery = resolve_report_delivery(latest)
            e1,e2 = st.columns(2)
            technical_delivery = resolve_technical_report_delivery(latest)
            if technical_delivery.get("ok"):
                e1.download_button(
                    "📘 Last ned full rapport med vedlegg",
                    technical_delivery["data"], file_name=technical_delivery["filename"],
                    mime="application/pdf", width="stretch", type="primary",
                    key="mi_download_technical_pdf_v19220_rc1631u",
                )
                e1.caption("Anbefalt: hovedrapport og alle tekniske vedleggssider i én PDF.")
            else:
                e1.error(str(technical_delivery.get("error") or "Full rapport med vedlegg er ikke tilgjengelig."))
            if delivery.get("ok"):
                e2.download_button(
                    "📄 Last ned kort rapport (3 sider)", delivery["data"],
                    file_name=delivery["filename"], mime="application/pdf",
                    width="stretch", key="mi_download_pdf_v19132",
                )
                if delivery.get("url"):
                    safe_url = html_escape(str(delivery["url"]), quote=True)
                    with e2.expander("Ekstern offentlig PDF", expanded=False):
                        st.warning("På iPhone/PWA kan denne lenken forlate appen. Bruk nedlastingsknappen over når rapporten skal deles.")
                        st.markdown(
                            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">Åpne ekstern PDF</a>',
                            unsafe_allow_html=True,
                        )
            else:
                e2.error(str(delivery.get("error") or "Kort PDF-rapport er ikke tilgjengelig."))
            ensure_report_document(latest)
            render_durable_json_download(st, latest, label="{ } Last ned JSON", instance_key="latest")
            st.download_button("Last ned rapport som tekst", build_text_report(latest), file_name=safe_ascii_report_filename(latest, "txt"), mime="text/plain", width="stretch", key="mi_download_txt_v1914")
            latest_package_key = "mi_latest_report_package_bytes_v19220_rc16"
            latest_package_name_key = "mi_latest_report_package_name_v19220_rc16"
            if st.button("Bygg ZIP med PDF, JSON, tekst og revisjon", key="mi_build_latest_package_v19220_rc16", width="stretch"):
                try:
                    package_bytes, package_name = _build_report_package_with_visible_progress_v19220_rc1611(
                        st, latest,
                    )
                    st.session_state[latest_package_key] = package_bytes
                    st.session_state[latest_package_name_key] = package_name
                except Exception as exc:
                    st.error(f"Rapportpakken kunne ikke bygges: {exc}")
            if st.session_state.get(latest_package_key):
                st.download_button(
                    "Last ned komplett ZIP: PDF, TXT, JSON, snapshots, manifest og SHA-256",
                    data=st.session_state[latest_package_key],
                    file_name=st.session_state.get(latest_package_name_key) or "REPORT_PACKAGE.zip",
                    mime="application/zip",
                    key="mi_download_latest_package_v19220_rc16",
                    width="stretch",
                )
    with tab_reports:
        st.markdown("### 📚 Rapportarkiv")
        st.caption("Rapportene lagres i programmet og kan åpnes eller lastes ned fra PC og mobil. Favoritter beskyttes mot opprydding.")
        archive = _load_report_archive()
        st.markdown("#### Komplett rapport-, replay- og læringsarkiv")
        st.caption("Skrivebeskyttet offline-eksport med rapporter, replaydata, Autonomi-/læringsdata, manifest, avvik og SHA-256.")
        try:
            _replay_export_start_fragment_v19220_rc1616()
            _replay_export_status_fragment_v19220_rc16()
        except Exception as exc:
            st.error(f"Samlet ZIP kunne ikke startes: {exc}")
        st.divider()
        q1, q2, q3, q4 = st.columns([2.2, 1.1, 1.1, 1.1])
        search = q1.text_input("Søk", placeholder="Ticker, jobbnavn, marked eller rapport-ID", key="mi_archive_search_v1921").strip().casefold()
        type_filter = q2.selectbox(
            "Rapporttype",
            ["Alle", "MORGENRAPPORT", "DAGSRAPPORT", "KVELDSRAPPORT", "NATTRAPPORT", "MANUELL_RAPPORT", "UTKAST", "SHADOW_VALIDATION"],
            key="mi_archive_type_v1921",
        )
        market_options = ["Alle"] + sorted({str(market) for row in archive for market in (row.get("markets") or []) if market})
        market_filter = q3.selectbox("Marked", market_options, key="mi_archive_market_v1921")
        period_filter = q4.selectbox("Datoperiode", ["Alle", "Siste 7 dager", "Siste 30 dager", "Egendefinert"], key="mi_archive_period_v1921")

        custom_start = custom_end = None
        if period_filter == "Egendefinert":
            d1, d2 = st.columns(2)
            custom_start = d1.date_input("Fra dato", key="mi_archive_from_v1921")
            custom_end = d2.date_input("Til dato", key="mi_archive_to_v1921")
        f1, f2 = st.columns([1.3, 2.7])
        state_filter = f1.selectbox("Rapportstatus", ["Alle", "FINAL", "PROVISIONAL", "LEGACY"], key="mi_archive_state_v1921")
        flag_filter = f2.multiselect(
            "Vis bare rapporter med",
            ["Favoritt", "Feil", "Endret Top 3", "Kjøpsgodkjente kandidater", "Lav beslutningsstyrke", "Reserve-feed"],
            key="mi_archive_flags_v1921",
        )

        now_local = as_local(datetime.now(timezone.utc), DEFAULT_TIMEZONE)
        if period_filter == "Siste 7 dager":
            date_start = (now_local - timedelta(days=7)).date()
            date_end = now_local.date()
        elif period_filter == "Siste 30 dager":
            date_start = (now_local - timedelta(days=30)).date()
            date_end = now_local.date()
        elif period_filter == "Egendefinert":
            date_start, date_end = custom_start, custom_end
        else:
            date_start = date_end = None

        filtered = []
        for row in archive:
            hay = " ".join([
                str(row.get("run_id") or ""), str(row.get("job_name") or ""),
                " ".join(row.get("tickers") or []), " ".join(row.get("markets") or []),
                str(row.get("report_label") or ""), str(row.get("mission_label") or ""),
            ]).casefold()
            if search and search not in hay:
                continue
            if type_filter != "Alle" and row.get("report_type") != type_filter:
                continue
            if market_filter != "Alle" and market_filter not in (row.get("markets") or []):
                continue
            if state_filter != "Alle" and str(row.get("report_state") or "LEGACY").upper() != state_filter:
                continue
            if date_start or date_end:
                try:
                    row_date = as_local(row.get("created_at"), str(row.get("timezone_name") or DEFAULT_TIMEZONE)).date()
                except Exception:
                    row_date = None
                if row_date is None or (date_start and row_date < date_start) or (date_end and row_date > date_end):
                    continue
            if "Favoritt" in flag_filter and not row.get("favorite"):
                continue
            if "Feil" in flag_filter and not row.get("has_errors"):
                continue
            if "Endret Top 3" in flag_filter and not row.get("top3_changed"):
                continue
            if "Kjøpsgodkjente kandidater" in flag_filter and int(row.get("decision_ready_count") or 0) <= 0:
                continue
            if "Lav beslutningsstyrke" in flag_filter and not row.get("low_reliability"):
                continue
            if "Reserve-feed" in flag_filter and not row.get("reserve_feed_used"):
                continue
            filtered.append(row)
        if not filtered:
            st.info("Ingen rapporter matcher filteret.")
        archive_page_size_v19220_rc1617 = 20
        archive_page_count_v19220_rc1617 = max(
            1, (len(filtered) + archive_page_size_v19220_rc1617 - 1) // archive_page_size_v19220_rc1617
        )
        archive_page_key_v19220_rc1617 = "mi_archive_page_v19220_rc1617"
        current_archive_page_v19220_rc1617 = int(st.session_state.get(archive_page_key_v19220_rc1617, 1) or 1)
        if current_archive_page_v19220_rc1617 > archive_page_count_v19220_rc1617:
            st.session_state[archive_page_key_v19220_rc1617] = 1
        archive_page_v19220_rc1617 = st.selectbox(
            "Arkivside",
            options=list(range(1, archive_page_count_v19220_rc1617 + 1)),
            format_func=lambda value: f"Side {value} av {archive_page_count_v19220_rc1617}",
            key=archive_page_key_v19220_rc1617,
            disabled=not bool(filtered),
        )
        archive_start_v19220_rc1617 = (int(archive_page_v19220_rc1617) - 1) * archive_page_size_v19220_rc1617
        visible_archive_rows_v19220_rc1617 = filtered[
            archive_start_v19220_rc1617:archive_start_v19220_rc1617 + archive_page_size_v19220_rc1617
        ]
        if filtered:
            st.caption(
                f"Viser {archive_start_v19220_rc1617 + 1}–"
                f"{archive_start_v19220_rc1617 + len(visible_archive_rows_v19220_rc1617)} av {len(filtered)} rapporter. "
                "Rapportfiler lastes bare når «Last rapportdetaljer» aktiveres."
            )
        for row in visible_archive_rows_v19220_rc1617:
            shown_time = row.get("created_at_local") or local_display(row.get("created_at"), str(row.get("timezone_name") or DEFAULT_TIMEZONE))
            kind = "Revalidering" if str(row.get("history_kind") or row.get("trigger") or "").upper() == "REVALIDATION" else str(row.get("report_label") or "Rapport")
            job_label = str(row.get("job_name") or "-")
            label = f"{'⭐ ' if row.get('favorite') else ''}{kind} · {job_label} · {shown_time}"
            with st.expander(label, expanded=False):
                state_label = row.get("report_status_label") or row.get("report_state") or "Eldre rapport"
                st.caption(
                    f"Status: {state_label} · Revisjon: {row.get('report_revision_label') or 'R1'}"
                    + (f" · Erstatter {row.get('supersedes_run_id')}" if row.get("supersedes_run_id") else "")
                )
                m1,m2,m3,m4,m5,m6 = st.columns(6)
                m1.metric("Anbefalt", row.get("recommended",0))
                m2.metric("Topp", row.get("top_ticker") or "-")
                m3.metric("Score", row.get("top_score") or 0)
                m4.metric("Kjøpsgodkjente", row.get("decision_ready_count", 0))
                m5.metric("Beslutningsstyrke", f"{row.get('report_decision_strength', 0)}/100")
                m6.metric("Oppgaver", row.get("next_task_count", 0))
                flags = []
                if row.get("top3_changed"): flags.append("Endret Top 3")
                if row.get("has_errors"): flags.append(f"Feil {row.get('error_count', 0)}")
                if row.get("reserve_feed_used"): flags.append("Reserve-feed")
                if row.get("low_reliability"): flags.append("Lav beslutningsstyrke")
                if flags:
                    st.caption(" · ".join(flags))
                load_details_v19220_rc1617 = st.toggle(
                    "Last rapportdetaljer",
                    key=f"mi_load_archive_details_v19220_rc1617_{row.get('run_id')}",
                    help="Laster JSON, PDF, tekst, kjøringsspor og nedlastingshandlinger bare for denne rapporten.",
                )
                if not load_details_v19220_rc1617:
                    st.caption("Detaljer og rapportfiler er ikke lastet.")
                    continue
                saved_run = load_archived_run(row)
                trace_id = str((saved_run or {}).get("operations_trace_id") or row.get("operations_trace_id") or "")
                if trace_id and st.toggle("Vis komplett kjøringsspor", key=f"mi_trace_toggle_{row.get('run_id')}"):
                    try:
                        from operational_telemetry import load_run_trace
                        trace = load_run_trace(trace_id)
                        t1, t2, t3, t4 = st.columns(4)
                        t1.metric("Trace-ID", trace.get("trace_id") or trace_id)
                        t2.metric("Status", trace.get("status") or "-")
                        t3.metric("Siste steg", trace.get("current_stage") or "-")
                        t4.metric("Varighet", f"{trace.get('duration_seconds') or 0} s")
                        stage_rows = [{
                            "Tid": item.get("at"),
                            "Steg": item.get("stage"),
                            "Status": item.get("status"),
                            "Melding": item.get("message"),
                            "Feilkode": item.get("error_code") or "",
                            "Feil": item.get("error") or "",
                        } for item in trace.get("stages") or []]
                        if stage_rows:
                            st.dataframe(pd.DataFrame(stage_rows), width="stretch", hide_index=True)
                        else:
                            st.caption("Kjøringssporet har ingen registrerte delsteg.")
                    except Exception as trace_exc:
                        st.warning(f"Kjøringssporet kunne ikke leses: {trace_exc}")
                json_path = Path(str(row.get("json_path") or ""))
                a,b,c,d = st.columns(4)
                delivery = resolve_report_delivery(saved_run, row)
                json_data = json_path.read_bytes() if json_path.exists() else (json.dumps(saved_run, ensure_ascii=False, indent=2, default=str).encode("utf-8") if saved_run else None)
                technical_delivery = resolve_technical_report_delivery(saved_run, row)
                if technical_delivery.get("ok"):
                    a.download_button(
                        "📘 Full rapport med vedlegg",
                        data=technical_delivery["data"], file_name=technical_delivery["filename"],
                        mime="application/pdf", key=f"mi_dl_technical_pdf_{row.get('run_id')}", width="stretch", type="primary",
                    )
                if delivery.get("ok"):
                    a.download_button("📄 Kort rapport (3 sider)", data=delivery["data"], file_name=delivery["filename"],
                                      mime="application/pdf", key=f"mi_dl_pdf_{row.get('run_id')}", width="stretch")
                else:
                    a.error(str(delivery.get("error") or "PDF-en kan ikke gjenopprettes."))
                if json_data:
                    with b:
                        render_durable_json_download(
                            st, saved_run or row, label="{ } Last ned JSON",
                            instance_key=f"archive_{row.get('run_id')}",
                        )
                if saved_run:
                    c.download_button("Last ned tekst", data=build_text_report(saved_run), file_name=safe_ascii_report_filename(saved_run, "txt"), mime="text/plain", key=f"mi_dl_txt_{row.get('run_id')}", width="stretch")
                fav_label = "Fjern favoritt" if row.get("favorite") else "⭐ Favoritt"
                if d.button(fav_label, key=f"mi_fav_{row.get('run_id')}", width="stretch"):
                    set_report_favorite(str(row.get("run_id")), not bool(row.get("favorite"))); _rerun_reports_v19220_rc11(st)
                archive_run_id = str(row.get("run_id") or "unknown")
                package_state_key = f"mi_archive_package_bytes_{archive_run_id}_v19220_rc16"
                package_name_key = f"mi_archive_package_name_{archive_run_id}_v19220_rc16"
                p1, p2 = st.columns(2)
                if p1.button("Bygg ZIP med PDF, JSON, tekst og revisjon", key=f"mi_build_package_{archive_run_id}_v19220_rc16", width="stretch", disabled=not bool(saved_run)):
                    try:
                        package_bytes, package_name = _build_report_package_with_visible_progress_v19220_rc1611(
                            st, saved_run, archive_entry=row,
                        )
                        import io as _io_rc165, zipfile as _zipfile_rc165
                        with _zipfile_rc165.ZipFile(_io_rc165.BytesIO(package_bytes), "r") as _archive_rc165:
                            if _archive_rc165.testzip() is not None or not _archive_rc165.namelist():
                                raise RuntimeError("Rapportpakken feilet integritetskontrollen")
                        st.session_state[package_state_key] = package_bytes
                        st.session_state[package_name_key] = package_name
                    except Exception as exc:
                        st.error(f"Rapportpakken kunne ikke bygges: {exc}")
                if st.session_state.get(package_state_key):
                    p2.download_button(
                        "Last ned komplett ZIP",
                        data=st.session_state[package_state_key],
                        file_name=st.session_state.get(package_name_key) or f"REPORT_PACKAGE_{archive_run_id}.zip",
                        mime="application/zip",
                        key=f"mi_download_package_{archive_run_id}_v19220_rc16",
                        width="stretch",
                    )
                confirm = st.checkbox("Bekreft permanent sletting", key=f"mi_confirm_delete_{row.get('run_id')}")
                if st.button("🗑 Slett rapport", key=f"mi_delete_report_{row.get('run_id')}", disabled=not confirm, width="stretch"):
                    delete_archived_report(str(row.get("run_id"))); _rerun_reports_v19220_rc11(st)

    with tab_accuracy:
        from historical_learning import render_accuracy_analytics
        render_accuracy_analytics()

    with tab_history:
        job_history = load_job_history(limit=20)
        if job_history:
            st.markdown("**Siste jobbkjøringer**")
            st.dataframe(pd.DataFrame([{
                "Tidspunkt": local_display(item.get("started_at") or item.get("recorded_at"), DEFAULT_TIMEZONE),
                "Type": item.get("type"),
                "Jobb": item.get("job_name"),
                "Status": item.get("status"),
                "PDF": "Ja" if item.get("pdf") else "Nei",
                "Pushover": "Sendt" if item.get("pushover_sent") else ("Forsøkt" if item.get("pushover_attempted") else "Ikke forsøkt"),
                "Varighet": item.get("duration_seconds", "-"),
            } for item in job_history]), width="stretch", hide_index=True)
        else:
            st.caption("Ingen jobbkjøringer er registrert.")

        st.markdown("**Rapporthistorikk**")
        rows = []
        for archived in _load_report_archive()[:100]:
            r = load_run(str(archived.get("run_id") or "")) or archived
            identity = resolve_report_identity(r)
            rows.append({
                "Type": identity.get("label"),
                "Kjøring": r.get("run_id"),
                "Tid": local_display(r.get("created_at"), str(r.get("timezone_name") or DEFAULT_TIMEZONE)),
                "Jobb": r.get("job_name"),
                "Markeder": ", ".join(r.get("markets", [])),
                "Skannet": (r.get("summary") or {}).get("scanned", 0),
                "Foreløpige modellkandidater": (r.get("summary") or {}).get("proposals", 0),
                "Feil": len(r.get("errors") or []),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.caption("Ingen historiske rapporter.")
    with tab_ops:
        jobs = load_jobs(); active = [x for x in jobs if x.enabled]
        archive_rows_rc16 = _load_report_archive()
        archive_count = len(archive_rows_rc16); o1,o2,o3,o4 = st.columns(4); o1.metric("Jobber", len(jobs)); o2.metric("Aktive", len(active)); o3.metric("Kjøringer", archive_count); o4.metric("Regenererbare PDF-er", archive_count)

        try:
            from scheduled_runner import load_unattended_state
            unattended = load_unattended_state()
        except Exception as exc:
            unattended = {"state": "UNAVAILABLE", "error": str(exc)}
        st.markdown("#### Uavhengig planlegger")
        health = scheduler_health_snapshot(persist=False)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Status", unattended.get("state") or "ALDRI KJØRT")
        s2.metric("Sist forsøkt", local_display(unattended.get("started_at"), DEFAULT_TIMEZONE) if unattended.get("started_at") else "-")
        s3.metric("Sist fullført", local_display(unattended.get("completed_at"), DEFAULT_TIMEZONE) if unattended.get("completed_at") else "-")
        s4.metric("Mistet planlagt", len(health.get("missed") or []))
        if unattended.get("error"):
            st.error("Planleggeren rapporterte feil. Teknisk detalj ligger under utvidet visning.")
        if st.button("Kjør planleggersjekk nå", key="mi_run_scheduler_cycle_v1914", width="stretch"):
            from scheduler_background import run_scheduler_cycle
            result = run_scheduler_cycle()
            st.success(f"Planleggersjekk fullført. Kjøringer startet: {result.get('runs', 0)}")
            _rerun_reports_v19220_rc11(st)
        with st.expander("Planleggerdetaljer", expanded=False):
            st.json({"unattended": unattended, "health": health})
        latest_run = _read(LATEST_PATH, {})
        source_health = latest_run.get("source_health") if isinstance(latest_run.get("source_health"), Mapping) else {}
        if source_health:
            st.markdown("#### Kildehelse")
            budget = source_health.get("newsapi_budget") if isinstance(source_health.get("newsapi_budget"), Mapping) else {}
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Forringede kilder", source_health.get("degraded_sources", 0))
            h2.metric("NewsAPI brukt", budget.get("used_today", 0))
            h3.metric("NewsAPI igjen", budget.get("remaining_today", 0))
            h4.metric("Cachetreff", budget.get("cache_hits", 0))
            if source_health.get("sources"):
                st.dataframe(pd.DataFrame(source_health.get("sources")), width="stretch", hide_index=True)

        st.markdown("#### Evidenssøksdiagnostikk")
        evidence_summary = latest_run.get("evidence_search_summary") if isinstance(latest_run.get("evidence_search_summary"), Mapping) else {}
        if not evidence_summary and isinstance(latest_run.get("candidates"), list):
            try:
                from evidence_search_status import build_run_search_summary
                evidence_summary = build_run_search_summary(latest_run.get("candidates") or [])
            except Exception as exc:
                evidence_summary = {"diagnostic_error": str(exc)}
        if evidence_summary:
            evidence_budget = evidence_summary.get("source_budget") if isinstance(evidence_summary.get("source_budget"), Mapping) else {}
            e1, e2, e3 = st.columns(3)
            e1.metric("Planlagte kildesøk", evidence_budget.get("planned", 0))
            e2.metric("Forsøkte kildesøk", evidence_budget.get("attempted", 0))
            e3.metric("Fullførte kildesøk", evidence_budget.get("successful", 0))
            e4, e5, e6 = st.columns(3)
            e4.metric("Med resultater", evidence_budget.get("with_results", 0))
            e5.metric("Ikke søkt", evidence_budget.get("not_searched", 0))
            e6.metric("Søkefeil", evidence_budget.get("failed", 0))
            unknown_reasons = int(evidence_summary.get("unknown_reason_count") or 0)
            if unknown_reasons:
                st.error(f"{unknown_reasons} evidenssøk mangler en entydig årsakskode.")
            else:
                st.caption("Alle registrerte evidenssøk har en entydig status og årsakskode.")
            status_counts = evidence_summary.get("status_counts") if isinstance(evidence_summary.get("status_counts"), Mapping) else {}
            reason_counts = evidence_summary.get("reason_counts") if isinstance(evidence_summary.get("reason_counts"), Mapping) else {}
            if status_counts or reason_counts:
                diagnostics_rows = []
                diagnostics_rows.extend({"Type": "Søkestatus", "Kode": key, "Antall": value} for key, value in sorted(status_counts.items()))
                diagnostics_rows.extend({"Type": "Årsak", "Kode": key, "Antall": value} for key, value in sorted(reason_counts.items()))
                st.dataframe(pd.DataFrame(diagnostics_rows), width="stretch", hide_index=True)
            with st.expander("Kandidatdetaljer for evidenssøk", expanded=False):
                candidate_rows = []
                for candidate in evidence_summary.get("candidates") or []:
                    if not isinstance(candidate, Mapping):
                        continue
                    for area, area_data in (candidate.get("areas") or {}).items():
                        if not isinstance(area_data, Mapping):
                            continue
                        area_budget = area_data.get("source_budget") if isinstance(area_data.get("source_budget"), Mapping) else {}
                        candidate_rows.append({
                            "Kandidat": candidate.get("ticker") or "-",
                            "Marked": candidate.get("market") or "-",
                            "Område": area,
                            "Søkestatus": area_data.get("search_status") or "-",
                            "Planlagt": area_budget.get("planned", 0),
                            "Forsøkt": area_budget.get("attempted", 0),
                            "Feil": area_budget.get("failed", 0),
                            "Ikke søkt": area_budget.get("not_searched", 0),
                        })
                if candidate_rows:
                    st.dataframe(pd.DataFrame(candidate_rows), width="stretch", hide_index=True)
                else:
                    st.caption("Ingen kandidatdetaljer er tilgjengelige for siste kjøring.")
        else:
            st.caption("Ingen evidenssøksdiagnostikk er tilgjengelig før første rapportkjøring.")
        if evidence_summary.get("diagnostic_error"):
            st.warning("Evidenssøksdiagnostikken kunne ikke bygges. Teknisk detalj vises under.")
            st.code(str(evidence_summary.get("diagnostic_error")))

        st.code("Uavhengig kjøring: python scheduled_runner.py", language="bash")
        st.caption(f"Runtime-katalog: {ROOT}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-due", action="store_true")
    args = parser.parse_args()
    if args.run_due:
        print(json.dumps(run_due_jobs(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
