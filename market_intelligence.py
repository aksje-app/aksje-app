"""Scheduled Market Intelligence & PDF Reports v18.6.87.

Job profiles combine multiple markets, schedules, pipeline modules and notification
rules. Jobs can run manually, when the Streamlit app is active, or from cron via
``python market_intelligence.py --run-due``. Analysis only: no trades are executed.
"""
from __future__ import annotations

import argparse
import io
import json
import uuid
import time as time_module
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Mapping, Sequence, Callable

from investment_pipeline import PipelineConfig, _load_candidate_rows_from_app, infer_market_from_ticker, normalize_candidate_identity, run_pipeline
from market_universe import BASE_MARKET_SCOPES, expand_market_scope
from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json
from durable_runtime import append_event, read_events, read_json as durable_read_json, write_json as durable_write_json

VERSION = "v18.7.7"
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
DRAFT_STORAGE_KEY = "market_intelligence/draft_job.json"
DRAFT_JOB_ID = "MI-DRAFT-AUTOSAVE"
RECENT_DRAFT_REUSE_MINUTES = 30

MODULE_OPTIONS = [
    "Market Scanner", "AI Discovery", "AI Research Assistant", "Strategy Match",
    "Backtesting Validation", "Portfolio Optimizer", "Learning Advisor", "Insider Intelligence", "News & Sentiment Intelligence",
]
SCHEDULE_OPTIONS = ["Ved appstart", "08:30", "12:00", "15:00", "16:30", "22:30"]
DEFAULT_SCAN_WINDOWS = [{"start": "08:00", "end": "10:00", "interval_minutes": 30}]
WEEKDAY_NAMES = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

SCAN_PROFILES = {"Rask (10)": 10, "Normal (25)": 25, "Grundig (50)": 50, "Egendefinert": None}


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
    ticker = str(candidate.get("ticker") or "").upper().strip()
    if ticker in COMPANY_TICKER_ALIASES:
        return COMPANY_TICKER_ALIASES[ticker]
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    name = str(candidate.get("name") or raw.get("longName") or raw.get("shortName") or ticker).upper()
    for suffix in (" CLASS A", " CLASS B", " CLASS C", " A-SHARE", " B-SHARE", " ADR", " PLC", " INC.", " INC", " CORP.", " CORP", " LTD.", " LTD"):
        name = name.replace(suffix, "")
    compact = "".join(ch for ch in name if ch.isalnum())
    return compact or ticker

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


def build_data_quality(refresh: Mapping[str, Any], candidate_count: int) -> dict[str, Any]:
    total = max(1, int(candidate_count or 0))
    success = int(refresh.get("live_count", 0))
    errors = int(refresh.get("error_count", 0))
    cache = int(refresh.get("cache_count", 0))
    coverage = max(0.0, min(100.0, 100.0 * (success + cache) / total))
    penalty = min(35.0, errors * 7.0 + (0 if refresh.get("latest_trade_dates") else 10.0))
    score = round(max(0.0, coverage - penalty), 1)
    label = "UTMERKET" if score >= 90 else "GODT" if score >= 75 else "BEGRENSET" if score >= 50 else "SVAKT"
    return {"score": score, "label": label, "candidate_count": candidate_count, "live": success, "cache": cache, "errors": errors, "latest_trade_dates": list(refresh.get("latest_trade_dates") or [])}


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


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
    row = {"at": _now_iso(), "event": event, **dict(payload)}
    append_event("market_intelligence/audit.jsonl", AUDIT_PATH, row)


def _durable_key(path: Path) -> str | None:
    if path == LATEST_PATH: return "market_intelligence/latest_run.json"
    if path == HISTORY_PATH: return "market_intelligence/candidate_history.json"
    if path == REPORT_ARCHIVE_PATH: return "market_intelligence/report_archive.json"
    if path.parent == RUNS_DIR: return f"market_intelligence/runs/{path.name}"
    if path.parent == SUMMARIES_DIR and path.suffix.lower() == ".json": return f"market_intelligence/summaries/{path.name}"
    return None


def load_audit(limit: int = 1000) -> list[dict[str, Any]]:
    return read_events("market_intelligence/audit.jsonl", AUDIT_PATH, limit=limit)


def load_run(run_id: str) -> dict[str, Any]:
    value = _read(RUNS_DIR / f"{run_id}.json", {})
    return dict(value) if isinstance(value, Mapping) else {}


def normalize_markets(markets: Sequence[str]) -> list[str]:
    chosen = [str(x) for x in markets if str(x)]
    if "Alle" in chosen:
        return list(BASE_MARKET_SCOPES)
    valid = set(BASE_MARKET_SCOPES)
    return [x for x in chosen if x in valid] or ["Norge"]


def report_identity(trigger: str, job_name: str = "", job_id: str = "") -> dict[str, str]:
    trigger_key = str(trigger or "").upper()
    job_key = str(job_name or "").casefold()
    if str(job_id or "").upper() == DRAFT_JOB_ID or "DRAFT" in trigger_key or "TEST" in trigger_key:
        return {"type": "UTKAST", "label": "Utkast", "slug": "UTKAST"}
    if trigger_key == "SCHEDULED" or (trigger_key == "MANUAL_FULL_CHAIN" and "morgen" in job_key):
        return {"type": "MORGENRAPPORT", "label": "Morgenrapport", "slug": "Morgenrapport"}
    return {"type": "MANUELL_RAPPORT", "label": "Manuell rapport", "slug": "Manuell_rapport"}


def resolve_report_identity(run: Mapping[str, Any]) -> dict[str, str]:
    """Resolve identity with the immutable draft job id as highest authority.

    Stored identity remains backwards compatible for ordinary reports, while a
    draft can never inherit a morning-report label from a stale or incorrect
    trigger during a Streamlit rerun.
    """
    trigger = str(run.get("trigger") or "")
    job_name = str(run.get("job_name") or "")
    job_id = str(run.get("job_id") or "")
    if job_id.upper() == DRAFT_JOB_ID:
        return report_identity(trigger, job_name, job_id)
    stored = run.get("report_identity")
    return dict(stored) if isinstance(stored, Mapping) else report_identity(trigger, job_name, job_id)


def safe_report_filename(run: Mapping[str, Any], extension: str = "pdf") -> str:
    identity = resolve_report_identity(run)
    job_name = str(run.get("job_name") or "Analyse").strip().replace("–", "-")
    clean = "_".join(part for part in "".join(ch if ch.isalnum() or ch in " _-" else " " for ch in job_name).split())
    stamp = str(run.get("created_at") or "").replace(":", "").replace("-", "")[:15] or str(run.get("run_id") or "latest")
    return f"{identity.get('slug','Rapport')}_{clean}_{stamp}.{extension}"


def job_fingerprint(job: "JobProfile") -> str:
    markets = normalize_markets(job.markets)
    return f"{job.scan_limit}|{job.deep_count}|{job.proposal_count}|{','.join(markets)}|{','.join(job.modules)}"


@dataclass
class JobProfile:
    name: str
    markets: list[str] = field(default_factory=lambda: ["Alle"])
    schedules: list[str] = field(default_factory=lambda: ["08:30", "22:30"])
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    modules: list[str] = field(default_factory=lambda: list(MODULE_OPTIONS))
    scan_limit: int = 25
    deep_count: int = 20
    proposal_count: int = 5
    min_alert_score: float = 80.0
    notify_pushover: bool = True
    notify_only_changes: bool = True
    include_report_link: bool = True
    include_top3_in_notification: bool = True
    allow_weekends: bool = False
    save_pdf: bool = True
    enabled: bool = True
    scan_windows: list[dict[str, Any]] = field(default_factory=list)
    run_autonomous_portfolio: bool = True
    run_controlled_learning: bool = True
    require_active_portfolio: bool = True
    job_id: str = field(default_factory=lambda: f"MIJ-{uuid.uuid4().hex[:10].upper()}")
    created_at: str = field(default_factory=_now_iso)
    last_run_at: str = ""
    last_status: str = "ALDRI KJØRT"

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
        return cls(**data)


def load_jobs() -> list[JobProfile]:
    data = read_persistent_json("market_intelligence/jobs.json", default=None)
    if data is None:
        data = _read(JOBS_PATH, [])
        if data:
            write_persistent_json("market_intelligence/jobs.json", data)
    jobs = [JobProfile.from_dict(x) for x in data if isinstance(x, Mapping)]
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
    if len(cleaned) != len(jobs):
        save_jobs(cleaned)
        _audit("DUPLICATE_JOB_PROFILES_REPAIRED", {"before": len(jobs), "after": len(cleaned)})
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
            return draft
        except Exception:
            pass
    return JobProfile(
        name="Normalanalyse – Alle markeder",
        markets=["Alle"],
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


def _candidate_map(run: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(x.get("ticker")): dict(x) for x in (run.get("candidates") or []) if x.get("ticker")}


def compare_runs(current: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    cur, prev = _candidate_map(current), _candidate_map(previous or {})
    new = [cur[t] for t in cur.keys() - prev.keys()]
    dropped = [prev[t] for t in prev.keys() - cur.keys()]
    improved, weakened, unchanged = [], [], []
    for ticker in cur.keys() & prev.keys():
        delta = round(float(cur[ticker].get("investment_score", 0)) - float(prev[ticker].get("investment_score", 0)), 2)
        component_labels = {
            "discovery_score": "AI Discovery", "fundamental_score": "Fundamentaler",
            "research_score": "Research", "validation_score": "Backtesting",
            "portfolio_fit_score": "Porteføljetilpasning", "risk_score": "Risiko",
        }
        drivers = []
        for key_name, label in component_labels.items():
            change = round(float(cur[ticker].get(key_name, 0) or 0) - float(prev[ticker].get(key_name, 0) or 0), 2)
            if abs(change) >= 0.5:
                drivers.append({"component": label, "delta": change})
        drivers.sort(key=lambda x: abs(float(x["delta"])), reverse=True)
        row = {**cur[ticker], "score_delta": delta, "previous_rank": prev[ticker].get("rank"), "change_drivers": drivers[:4]}
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
    rows = _read(REPORT_ARCHIVE_PATH, [])
    if not rows:
        legacy = read_persistent_json("market_intelligence/report_archive.json", default=[])
        if isinstance(legacy, list) and legacy:
            rows = legacy
            _write(REPORT_ARCHIVE_PATH, rows)
            _audit("REPORT_ARCHIVE_MIGRATED_TO_DURABLE_STORAGE", {"reports": len(rows)})
    return [dict(x) for x in rows if isinstance(x, Mapping)]


def _save_report_archive(rows: Sequence[Mapping[str, Any]]) -> None:
    payload = [dict(x) for x in rows]
    _write(REPORT_ARCHIVE_PATH, payload)
    write_persistent_json("market_intelligence/report_archive.json", payload)


def _archive_entry(run: Mapping[str, Any]) -> dict[str, Any]:
    candidates = list(run.get("candidates") or [])
    top = candidates[0] if candidates else {}
    identity = resolve_report_identity(run)
    return {
        "run_id": run.get("run_id"), "created_at": run.get("created_at"), "job_name": run.get("job_name"),
        "report_type": identity.get("type"), "report_label": identity.get("label"),
        "pdf_path": run.get("pdf_path"), "json_path": str(RUNS_DIR / f"{run.get('run_id')}.json"),
        "markets": list(run.get("markets") or []), "recommended": int((run.get("summary") or {}).get("recommended", 0)),
        "top_ticker": top.get("ticker"), "top_score": top.get("investment_score"),
        "tickers": [str(x.get("ticker")) for x in candidates if x.get("ticker")],
        "favorite": False, "analysis_aborted": bool(run.get("analysis_aborted")),
    }


def archive_report(run: Mapping[str, Any]) -> None:
    entry = _archive_entry(run)
    rows = [x for x in _load_report_archive() if x.get("run_id") != entry.get("run_id")]
    rows.insert(0, entry)
    _save_report_archive(rows[:1000])


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
    for key in ("pdf_path", "json_path"):
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
    import os
    base = str(os.getenv("REPORT_BASE_URL") or "").rstrip("/")
    if not base or not run.get("pdf_path"):
        return ""
    return f"{base}/{Path(str(run.get('pdf_path'))).name}"


def _notification(job: JobProfile, run: Mapping[str, Any]) -> tuple[bool, str]:
    changes = run.get("changes") or {}
    interesting = [x for x in changes.get("new", []) if float(x.get("investment_score", 0)) >= job.min_alert_score]
    interesting += [x for x in changes.get("improved", []) if float(x.get("investment_score", 0)) >= job.min_alert_score]
    if job.notify_only_changes and not interesting:
        return False, "Ingen kvalifiserende endringer"
    if not job.notify_pushover:
        return False, "Pushover er deaktivert for jobben"
    try:
        from notifier import send_pushover_alert
        top = (run.get("proposals") or run.get("candidates") or [{}])[0]
        lines = [
            f"Jobb: {job.name}", f"Markeder: {', '.join(run.get('markets', []))}",
            f"Analysert: {run.get('summary', {}).get('deep_analyzed', 0)}",
            f"Anbefalt: {run.get('summary', {}).get('recommended', 0)}",
            f"Nye: {len(changes.get('new', []))} | Forbedret: {len(changes.get('improved', []))}",
        ]
        if job.include_top3_in_notification:
            medals = run.get("diverse_top3") or select_diverse_candidates(run.get("candidates") or [], 3)
            for idx, item in enumerate(medals):
                lines.append(f"{('🥇','🥈','🥉')[idx]} {item.get('ticker','-')} {float(item.get('investment_score',0)):.2f}")
        else:
            lines.append(f"Topp: {top.get('ticker', '-')} ({top.get('investment_score', '-')})")
        url = report_public_url(run) if job.include_report_link else ""
        ok, err = send_pushover_alert("\n".join(lines), title="Scheduled Market Intelligence", url=url or None, url_title="Åpne rapport" if url else None)
        return bool(ok), str(err or "Sendt")
    except Exception as exc:
        return False, str(exc)


def build_pdf(run: Mapping[str, Any], report_type: str | None = None) -> bytes:
    """Build the compact professional market-intelligence report.

    The v18.7.5 layout deliberately avoids decorative cover/disclaimer pages and
    per-proposal page breaks.  No report data is removed; dense sections are
    arranged horizontally and allowed to flow naturally across A4 pages.
    """
    from html import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = resolve_report_identity(run)
    report_type = report_type or f"{identity.get('label', 'Rapport')} – Market Intelligence"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=13*mm, leftMargin=13*mm, topMargin=15*mm, bottomMargin=14*mm,
                            title=report_type, author="AI Aksje Analyzer Pro")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_LEFT, fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.HexColor("#102A43"), spaceAfter=2*mm))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#102A43"), spaceBefore=3*mm, spaceAfter=1.5*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="Subsection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=9.5, leading=11, textColor=colors.HexColor("#243B53"), spaceBefore=2.2*mm, spaceAfter=1*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="BodyCompact", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10, spaceAfter=.8*mm))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.2, leading=8.7, spaceAfter=.6*mm))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontName="Helvetica", fontSize=6.4, leading=7.5))
    styles.add(ParagraphStyle(name="Footer", parent=styles["BodyText"], fontName="Helvetica", fontSize=6.5, leading=8, textColor=colors.HexColor("#627D98")))

    header_bg = colors.HexColor("#D9EAF7")
    grid = colors.HexColor("#9FB3C8")
    stripe = colors.HexColor("#F5F8FA")

    def _table_style(font_size: float = 7, *, header: bool = True, padding: float = 2.5) -> TableStyle:
        commands = [
            ("GRID", (0, 0), (-1, -1), .3, grid),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 1.3),
            ("LEFTPADDING", (0, 0), (-1, -1), padding),
            ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, stripe]),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), header_bg), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        return TableStyle(commands)

    def _p(value: Any, style: str = "Tiny") -> Paragraph:
        return Paragraph(escape(str(value if value is not None else "-")), styles[style])

    def _fmt(value: Any, decimals: int = 2) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        try:
            return f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return value

    def _page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#BCCCDC"))
        canvas.setLineWidth(.35)
        canvas.line(13*mm, height-10*mm, width-13*mm, height-10*mm)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#627D98"))
        canvas.drawString(13*mm, height-8*mm, "AI Aksje Analyzer Pro")
        canvas.drawRightString(width-13*mm, height-8*mm, str(identity.get("label") or "Rapport"))
        canvas.line(13*mm, 9*mm, width-13*mm, 9*mm)
        canvas.drawString(13*mm, 6*mm, str(run.get("run_id") or "-"))
        canvas.drawRightString(width-13*mm, 6*mm, f"Side {document.page}")
        canvas.restoreState()

    markets_text = ", ".join(run.get("markets") or run.get("market_expansion") or [])
    meta = Table([
        [_p("Rapporttype", "Small"), _p(identity.get("type", "-"), "Small"), _p("Jobb", "Small"), _p(run.get("job_name", "-"), "Small")],
        [_p("Rapport-ID", "Small"), _p(run.get("run_id", "-"), "Small"), _p("Generert", "Small"), _p(run.get("created_at", "-"), "Small")],
        [_p("Markeder", "Small"), _p(markets_text, "Small"), "", ""],
    ], colWidths=[22*mm, 68*mm, 18*mm, 76*mm])
    meta.setStyle(_table_style(7, header=False, padding=2.5))
    meta.setStyle(TableStyle([("SPAN", (1, 2), (3, 2)), ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"), ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F5F8FA"))]))
    story = [Paragraph("AI Aksje Analyzer Pro", styles["ReportTitle"]), Paragraph(escape(report_type), styles["Section"]), meta, Spacer(1, 2*mm)]
    summary = run.get("summary") or {}
    intelligence = run.get("executive_intelligence") or executive_intelligence(run.get("candidates") or [])
    summary_items = [("Skannet", summary.get("scanned", 0)), ("Grundig analysert", summary.get("deep_analyzed", 0)),
                     ("Forslag", summary.get("proposals", 0)), ("Anbefalt", summary.get("recommended", 0)),
                     ("Unike selskaper", intelligence.get("unique_companies", 0)), ("Snittscore", intelligence.get("average_score", 0)),
                     ("Høyeste score", intelligence.get("highest_score", 0)), ("Markeder i Top 10", intelligence.get("markets_in_top10", 0)),
                     ("Sterke insidersignaler", sum(1 for x in (run.get("candidates") or []) if float((x.get("raw") or {}).get("insider_score", 50) or 50) >= 78))]
    summary_grid = []
    for index in range(0, len(summary_items), 3):
        cells = []
        for label, value in summary_items[index:index+3]:
            cells.append(Paragraph(f"<b>{escape(label)}</b><br/><font size='11'>{escape(str(value))}</font>", styles["Small"]))
        while len(cells) < 3: cells.append("")
        summary_grid.append(cells)
    summary_table = Table(summary_grid, colWidths=[61.3*mm]*3)
    summary_table.setStyle(_table_style(7, header=False, padding=4))
    story += [Paragraph("Executive Summary", styles["Section"]), summary_table]
    diagnostics = run.get("market_diagnostics") or []
    if diagnostics:
        diag_data = [["Marked", "Skannet", "Analysert", "Live", "Feil", "Status"]]
        for item in diagnostics:
            diag_data.append([item.get("market"), item.get("scanned", 0), item.get("analyzed", 0), item.get("live", 0), item.get("errors", 0), item.get("status", "-")])
        diag_table = Table(diag_data, repeatRows=1, colWidths=[30*mm, 24*mm, 27*mm, 20*mm, 20*mm, 40*mm])
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
        quality_table = Table([["Kvalitet", f"{quality.get('score', 0)} %", "Vurdering", quality.get("label", "-"), "Live", quality.get("live", 0), "Cache", quality.get("cache", 0), "Feil", quality.get("errors", 0)]], colWidths=[18*mm,13*mm,18*mm,29*mm,10*mm,10*mm,11*mm,10*mm,10*mm,10*mm])
        quality_table.setStyle(_table_style(6.8, header=False, padding=2))
        quality_table.setStyle(TableStyle([("FONTNAME", (0,0), (-1,0), "Helvetica"), ("FONTNAME", (0,0), (0,0), "Helvetica-Bold"), ("FONTNAME", (2,0), (2,0), "Helvetica-Bold"), ("FONTNAME", (4,0), (4,0), "Helvetica-Bold"), ("FONTNAME", (6,0), (6,0), "Helvetica-Bold"), ("FONTNAME", (8,0), (8,0), "Helvetica-Bold")]))
        story += [Paragraph("Datakvalitet", styles["Subsection"]), quality_table]
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
        trace_data = [["Ticker", "Marked / land", "Kilde", "Status", "Cache-bypass", "Siste handelsdato", "Endret"]]
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
            idata.append([item.get("ticker"), item.get("market"), raw.get("insider_signal"), _fmt(raw.get("insider_score")), ins.get("buy_count", 0), ins.get("sell_count", 0), _fmt(ins.get("net_value", 0), 0)])
        itable = Table(idata, repeatRows=1, colWidths=[24*mm, 24*mm, 31*mm, 17*mm, 17*mm, 17*mm, 32*mm])
        itable.setStyle(_table_style())
        story += [Paragraph("Insider Intelligence", styles["Section"]), Paragraph("Offentlig registrerte insidertransaksjoner. Manglende dekning gir nøytral score og skal ikke tolkes som fravær av handler.", styles["Small"]), itable]
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
            ndata.append([item.get("ticker"), item.get("market"), raw.get("news_sentiment"), _fmt(raw.get("news_score")), news.get("article_count", 0), news.get("high_impact_count", 0), _p(str(news.get("summary") or "")[:95])])
        ntable = Table(ndata, repeatRows=1, colWidths=[20*mm, 21*mm, 25*mm, 14*mm, 14*mm, 22*mm, 54*mm])
        ntable.setStyle(_table_style(6.4, padding=2))
        story += [Paragraph("News & Sentiment Intelligence", styles["Section"]), Paragraph("Unike, ferske nyhetssaker vektes etter sentiment, kildekvalitet, aktualitet og hendelsespåvirkning. Manglende dekning gir nøytral score.", styles["Small"]), ntable]
    if run.get("analysis_aborted"):
        story += [Paragraph("Analyse avbrutt – utilstrekkelige data", styles["Section"]),
                  Paragraph("Alle tilgjengelige live-hentinger feilet. Rangering, medaljer, anbefalinger og teoretisk portefølje er derfor deaktivert for denne kjøringen.", styles["BodyCompact"])]
    elif candidates:
        medal_labels = ["GULL · BESTE KANDIDAT", "SØLV · NUMMER TO", "BRONSE · NUMMER TRE"]
        medal_data = []
        medal_candidates = run.get("diverse_top3") or select_diverse_candidates(candidates, 3)
        for idx, r in enumerate(medal_candidates):
            strongest = max((("AI Discovery", r.get("discovery_score", 0)), ("Fundamentaler", r.get("fundamental_score", 0)), ("Research", r.get("research_score", 0)), ("Validering", r.get("validation_score", 0)), ("Porteføljetilpasning", r.get("portfolio_fit_score", 0)), ("Insider", (r.get("raw") or {}).get("insider_score", 50)), ("Nyheter", (r.get("raw") or {}).get("news_score", 50))), key=lambda x: float(x[1] or 0))
            display_name = str(r.get("name") or r.get("ticker") or "-")
            medal_data.append([Paragraph(f"<b>{medal_labels[idx]}</b><br/><b>{display_name}</b><br/>{r.get('ticker','-')} · {r.get('market','-')}<br/>Score {r.get('investment_score',0)} · Konf. {r.get('confidence_score',0)} %<br/>Risiko {r.get('risk_score',0)} · Vekt {r.get('proposed_position_pct',0)} %<br/>Sterkest: {strongest[0]} {float(strongest[1] or 0):.1f}", styles["Small"])])
        medal_table = Table([medal_data], colWidths=[55*mm]*len(medal_data))
        medal_styles = [("BOX", (0,0), (-1,-1), .8, colors.grey), ("INNERGRID", (0,0), (-1,-1), .35, colors.lightgrey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]
        medal_colors = ["#FFF4C2", "#EEF1F5", "#F6E1D3"]
        for medal_index in range(len(medal_data)):
            medal_styles.append(("BACKGROUND", (medal_index,0), (medal_index,-1), colors.HexColor(medal_colors[medal_index])))
        medal_table.setStyle(TableStyle(medal_styles))
        story += [Paragraph("Topp 3", styles["Section"]), medal_table]
        data = [["#", "Ticker", "Marked", "Score", "Konf.", "Trend", "Risiko", "Status"]]
        for r in candidates[:10]:
            data.append([r.get("rank"), r.get("ticker"), r.get("market"), _fmt(r.get("investment_score")), _fmt(r.get("confidence_score")), r.get("trend"), _fmt(r.get("risk_score")), _p(str(r.get("status", ""))[:35])])
        table = Table(data, repeatRows=1, colWidths=[8*mm, 20*mm, 22*mm, 16*mm, 16*mm, 20*mm, 16*mm, 52*mm])
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey),
                                   ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))
        story += [Paragraph("Top 10", styles["Section"]), table]
    for p in run.get("proposals") or []:
        raw = p.get("raw") or {}; insider = raw.get("insider_intelligence") or {}; news = raw.get("news_intelligence") or {}
        score_data = [
            ["AI Discovery", "Fundamentalt", "Research", "Backtesting", "Portefølje", "Insider", "Nyheter", "Risiko"],
            [_fmt(p.get("discovery_score")), _fmt(p.get("fundamental_score")), _fmt(p.get("research_score")), _fmt(p.get("validation_score")), _fmt(p.get("portfolio_fit_score")), _fmt(raw.get("insider_score", 50)), _fmt(raw.get("news_score", 50)), _fmt(p.get("risk_score"))],
        ]
        score_table = Table(score_data, colWidths=[23*mm]*8)
        score_table.setStyle(_table_style(6.5, padding=2))
        positives = " • ".join(str(x) for x in (p.get("positives") or [])) or "Ingen registrerte positive drivere."
        risks = " • ".join(str(x) for x in (p.get("risks") or [])) or "Ingen registrerte risikopunkter."
        proposal = [
            Paragraph(f"{escape(str(p.get('ticker') or '-'))} – investeringsforslag", styles["Section"]),
            Paragraph(f"<b>Status:</b> {escape(str(p.get('status') or '-'))} &nbsp; | &nbsp; <b>Investeringsscore:</b> {escape(str(_fmt(p.get('investment_score'))))} / 100 &nbsp; | &nbsp; <b>Konfidens:</b> {escape(str(_fmt(p.get('confidence_score', 0))))} / 100 &nbsp; | &nbsp; <b>Trend:</b> {escape(str(p.get('trend', 'NY')))}", styles["BodyCompact"]),
            score_table,
            Paragraph(f"<b>Insider:</b> {escape(str(raw.get('insider_signal', 'INGEN DATA')))} · score {escape(str(_fmt(raw.get('insider_score', 50))))} / 100 · nettoverdi {escape(str(_fmt(insider.get('net_value', 0), 0)))}", styles["Small"]),
            Paragraph(f"<b>Nyheter:</b> {escape(str(raw.get('news_sentiment', 'INGEN DATA')))} · score {escape(str(_fmt(raw.get('news_score', 50))))} / 100 · {escape(str(news.get('summary') or 'Ingen oppsummering.'))}", styles["Small"]),
            Paragraph(f"<b>Positive drivere:</b> {escape(positives)}", styles["Small"]),
            Paragraph(f"<b>Risiko:</b> {escape(risks)}", styles["Small"]),
            Paragraph(f"<b>Handelsramme:</b> Strategi {escape(str(p.get('strategy_match') or '-'))} · foreslått porteføljevekt {escape(str(p.get('proposed_position_pct', 0)))} %", styles["Small"]),
        ]
        story += [KeepTogether(proposal), Spacer(1, 1.2*mm)]
    portfolio_proposal = run.get("portfolio_proposal") or {}
    allocations = portfolio_proposal.get("allocations") or []
    if allocations:
        pdata = [["Ticker", "Marked", "Sektor", "Vekt %", "Score", "Konfidens", "Risiko"]]
        for a in allocations:
            pdata.append([a.get("ticker"), a.get("market"), a.get("sector"), _fmt(a.get("weight_pct")), _fmt(a.get("score")), _fmt(a.get("confidence")), _fmt(a.get("risk"))])
        ptable = Table(pdata, repeatRows=1, colWidths=[24*mm, 24*mm, 38*mm, 18*mm, 18*mm, 20*mm, 18*mm])
        ptable.setStyle(_table_style())
        story += [KeepTogether([Paragraph("Teoretisk porteføljeforslag", styles["Section"]),
                               Paragraph(f"Investert: {portfolio_proposal.get('invested_pct', 0)} % | Kontanter: {portfolio_proposal.get('cash_pct', 100)} %", styles["BodyCompact"]),
                               ptable])]
    story += [KeepTogether([Paragraph("Metode og ansvarsfraskrivelse", styles["Section"]),
                            Paragraph("Rapporten er automatisk beslutningsstøtte basert på tilgjengelige data. Den er ikke personlig investeringsrådgivning og utfører ingen handler. Alle forslag krever manuell kontroll.", styles["BodyCompact"])])]
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buf.getvalue()






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
    run_id = f"MI-{_now().strftime('%Y%m%d-%H%M%S')}"
    run.update({
        "version": VERSION,
        "run_id": run_id,
        "created_at": _now_iso(),
        "job_id": job.job_id,
        "job_name": job.name,
        "trigger": trigger,
        "report_identity": report_identity(trigger, job.name, job.job_id),
        "execution_mode": "PROMOTED_VALIDATED_DRAFT",
        "source_draft_run_id": source.get("run_id"),
        "configuration_handoff": dict(handoff),
    })
    validation = dict(run.get("validation") or {})
    validation.update({"unified_execution_pipeline": True, "promoted_from_validated_draft": True})
    run["validation"] = validation
    run["notification"] = {"sent": False, "detail": "Rapport promotert fra validert utkast; ingen ny API-kjøring"}
    pdf_path = SUMMARIES_DIR / safe_report_filename(run, "pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(build_pdf(run))
    run["pdf_path"] = str(pdf_path)
    _write(RUNS_DIR / f"{run_id}.json", run)
    _write(LATEST_PATH, run)
    _write(SUMMARIES_DIR / f"{run_id}.json", {k: run.get(k) for k in ("run_id", "created_at", "job_name", "markets", "summary", "changes", "errors")})
    job.last_run_at, job.last_status = run["created_at"], "OK"
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

def run_job(job: JobProfile, trigger: str = "MANUAL", progress_callback: Callable[[Mapping[str, Any]], None] | None = None, force_refresh: bool = False) -> dict[str, Any]:
    requested_job = job
    job, handoff = _effective_execution_job(job, trigger)
    previous = _read(LATEST_PATH, {})
    reusable = None if force_refresh else _recent_validated_draft(job, trigger)
    if reusable is not None:
        if progress_callback:
            progress_callback({"phase": "COMPLETE", "completed": 1, "total": 1, "message": "Validerte utkastdata gjenbrukes som endelig morgenrapport"})
        return _persist_promoted_run(reusable, job, trigger, handoff)
    def emit(phase: str, completed: int, total: int, message: str, **extra: Any) -> None:
        if progress_callback:
            progress_callback({"phase": phase, "completed": completed, "total": max(1, total), "message": message, **extra})
    emit("START", 0, 1, "Starter markedsskanning")
    market_runs, all_candidates, all_proposals = [], [], []
    market_diagnostics: list[dict[str, Any]] = []
    totals = {"scanned": 0, "deep_analyzed": 0, "proposals": 0, "recommended": 0, "rejected": 0}
    errors = []
    warnings = []
    markets = normalize_markets(job.markets)
    for market_index, market in enumerate(markets, start=1):
        cfg = PipelineConfig(market_scope=market, scan_limit=job.scan_limit, deep_analysis_count=job.deep_count,
                             proposal_count=job.proposal_count, use_research="AI Research Assistant" in job.modules,
                             use_backtest="Backtesting Validation" in job.modules,
                             use_portfolio_fit="Portfolio Optimizer" in job.modules,
                             use_learning_advisor="Learning Advisor" in job.modules,
                             use_insider_intelligence="Insider Intelligence" in job.modules,
                             use_news_intelligence="News & Sentiment Intelligence" in job.modules).normalized()
        try:
            emit("MARKET", market_index - 1, len(markets), f"Forbereder marked {market_index}/{len(markets)}: {market}", market=market)
            rows, source = _load_candidate_rows_from_app(cfg)
            if not rows:
                errors.append(f"{market}: ingen kandidater")
                continue
            def _pipeline_progress(event: Mapping[str, Any]) -> None:
                e = dict(event)
                e["market"] = market
                e["market_index"] = market_index
                e["market_total"] = len(markets)
                if progress_callback:
                    progress_callback(e)
            result = run_pipeline(rows, cfg, progress_callback=_pipeline_progress, force_refresh=force_refresh)
            result["candidate_source"] = source
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
                    market_refresh = retry_refresh
                    result["market_retry_used"] = True
            if market_index < len(markets):
                time_module.sleep(1.0)
            candidate_errors = list(result.get("candidate_errors") or [])
            skipped_count = int((result.get("loader_diagnostics") or {}).get("skipped_count", 0))
            market_diagnostics.append({
                "market": market,
                "scanned": int((result.get("summary") or {}).get("scanned", len(rows))),
                "analyzed": len(result.get("candidates") or []),
                "live": int(market_refresh.get("live_count", 0)),
                "errors": int(market_refresh.get("error_count", 0)) + skipped_count,
                "status": ("OK" if int(market_refresh.get("live_count", 0)) > 0 else "INGEN LIVE-DATA") + (f" · {skipped_count} kandidat(er) hoppet over" if skipped_count else ""),
                "candidate_errors": candidate_errors[:10],
            })
            for item in candidate_errors:
                warnings.append(f"{market}/{item.get('ticker') or 'ukjent'} ({item.get('stage')}): {item.get('error')}")
            market_runs.append(result)
            all_candidates.extend(result.get("candidates") or [])
            all_proposals.extend(result.get("proposals") or [])
            for key in totals:
                totals[key] += int((result.get("summary") or {}).get(key, 0))
        except Exception as exc:
            errors.append(f"{market}: {exc}")
            market_diagnostics.append({"market": market, "scanned": 0, "analyzed": 0, "live": 0, "errors": 1, "status": f"FEIL: {str(exc)[:80]}"})
    emit("DEDUP", 1, 1, "Fjerner duplikater og rangerer kandidater")
    # Global identity integrity: one ticker, one canonical market, one assessment.
    deduped: dict[str, dict[str, Any]] = {}
    identity_rejections: list[dict[str, Any]] = []
    for raw_candidate in all_candidates:
        candidate = normalize_candidate_identity(raw_candidate)
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
    for idx, row in enumerate(all_candidates, 1):
        row["rank"] = idx
    totals["deep_analyzed"] = len(all_candidates)
    totals["recommended"] = sum(1 for x in all_candidates if x.get("status") == "ANBEFALT FOR VURDERING")
    totals["rejected"] = sum(1 for x in all_candidates if x.get("status") in {"AVVIST AV RISIKOPORT", "UTILSTREKKELIGE DATA"})
    proposal_map: dict[str, dict[str, Any]] = {}
    for proposal in all_proposals:
        clean = normalize_candidate_identity(proposal)
        ticker = str(clean.get("ticker") or "").upper()
        if ticker and (ticker not in proposal_map or float(clean.get("investment_score", 0)) > float(proposal_map[ticker].get("investment_score", 0))):
            proposal_map[ticker] = clean
    all_proposals = sorted(proposal_map.values(), key=lambda x: float(x.get("investment_score", 0)), reverse=True)[:job.proposal_count]
    run_id = f"MI-{_now().strftime('%Y%m%d-%H%M%S')}"
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
    data_quality = build_data_quality(refresh_summary, len(all_candidates))
    run = {"version": VERSION, "run_id": run_id, "created_at": _now_iso(), "job_id": job.job_id, "job_name": job.name,
           "trigger": trigger, "markets": markets, "modules": job.modules, "summary": totals, "candidates": all_candidates,
           "proposals": all_proposals, "market_runs": market_runs, "errors": errors, "warnings": warnings, "execution": "ANALYSIS_ONLY",
           "data_refresh": refresh_summary, "market_status": market_status, "data_quality": data_quality,
           "analysis_aborted": analysis_aborted,
           "executive_intelligence": executive_intelligence(all_candidates),
           "diverse_top3": select_diverse_candidates(all_candidates, 3),
           "report_identity": report_identity(trigger, job.name, job.job_id),
           "execution_mode": "UNIFIED_PIPELINE",
           "configuration_handoff": handoff,
           "market_diagnostics": market_diagnostics,
           "validation": {
               "unique_tickers": len(all_candidates),
               "identity_rejections": identity_rejections,
               "duplicate_count_removed": max(0, sum(len(r.get("candidates") or []) for r in market_runs) - len(all_candidates)),
               "draft_handoff_fingerprint": job_fingerprint(job),
               "report_identity_present": True,
               "unified_execution_pipeline": True,
               "requested_job_fingerprint": job_fingerprint(requested_job),
               "effective_job_fingerprint": job_fingerprint(job),
               "valid_for_ranking": not analysis_aborted and bool(all_candidates),
           },
           "scan_configuration": {
               "per_market": job.scan_limit,
               "market_count": len(markets),
               "planned_maximum": job.scan_limit * len(markets),
               "actual_by_market": {
                   str(item.get("config", {}).get("market_scope") or "Ukjent"): int((item.get("summary") or {}).get("scanned", 0))
                   for item in market_runs
               },
           }}
    from advanced_investment_intelligence import build_portfolio_proposal
    emit("PORTFOLIO_PROPOSAL", 1, 1, "Beregner porteføljeforslag")
    run["portfolio_proposal"] = ({"positions": [], "allocations": [], "invested_pct": 0.0, "cash_pct": 100.0, "status": "AVBRUTT_UTILSTREKKELIGE_DATA"}
                                 if analysis_aborted else diversify_portfolio(build_portfolio_proposal(all_candidates)))
    if analysis_aborted:
        run["changes"] = {"new": [], "improved": [], "weakened": [], "unchanged": [], "dropped": []}
    else:
        run["changes"] = compare_runs(run, previous)
        _update_history(run)
    try:
        if analysis_aborted:
            run["autonomous_chain"] = {"status": "SKIPPED", "reason": "Utilstrekkelige markedsdata"}
        else:
            from autonomous_orchestrator import run_post_scan_chain
            emit("AUTONOMOUS", 0, 1, "Kjører teoretiske kjøps- og salgsbeslutninger")
            run["autonomous_chain"] = run_post_scan_chain(
            run,
            run_autonomous=job.run_autonomous_portfolio,
            run_learning=job.run_controlled_learning,
            require_active_portfolio=job.require_active_portfolio,
                trigger=trigger,
            )
    except Exception as exc:
        run["autonomous_chain"] = {"status": "ERROR", "errors": [str(exc)]}
        errors.append(f"Autonom orkestrering: {exc}")
    emit("REPORT", 0, 1, "Genererer rapport og lagrer resultat")
    if job.save_pdf:
        pdf_path = SUMMARIES_DIR / safe_report_filename(run, "pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(build_pdf(run))
        run["pdf_path"] = str(pdf_path)
    notify_ok, notify_detail = _notification(job, run)
    run["notification"] = {"sent": notify_ok, "detail": notify_detail, "report_url": report_public_url(run)}
    _write(RUNS_DIR / f"{run_id}.json", run)
    _write(LATEST_PATH, run)
    _write(SUMMARIES_DIR / f"{run_id}.json", {k: run[k] for k in ("run_id", "created_at", "job_name", "markets", "summary", "changes", "errors")})
    archive_report(run)
    try:
        from historical_learning import register_run
        run["historical_learning"] = {"snapshots_created": register_run(run), "mode": "DESCRIPTIVE_ONLY"}
        _write(RUNS_DIR / f"{run_id}.json", run)
    except Exception as exc:
        run["historical_learning"] = {"snapshots_created": 0, "error": str(exc), "mode": "DESCRIPTIVE_ONLY"}
    job.last_run_at = run["created_at"]
    job.last_status = "FULLFØRT MED FEIL" if errors else ("OK MED DATAVARSLER" if warnings else "OK")
    upsert_job(job)
    _audit("JOB_RUN", {"job_id": job.job_id, "run_id": run_id, "trigger": trigger, "errors": errors})
    emit("COMPLETE", 1, 1, "Hele kjeden er fullført", run_id=run_id)
    return run


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


def _slot_due(job: JobProfile, now: datetime) -> bool:
    if not job.enabled or now.weekday() not in job.weekdays:
        return False
    last = None
    try:
        last = datetime.fromisoformat(job.last_run_at) if job.last_run_at else None
    except Exception:
        pass
    if _window_slot_due(job, now, last):
        return True
    for slot in job.schedules:
        if slot == "Ved appstart":
            if not last or last.date() < now.date():
                return True
            continue
        parsed = _parse_hhmm(slot)
        if not parsed:
            continue
        scheduled = datetime.combine(now.date(), time(*parsed), tzinfo=now.tzinfo)
        if now >= scheduled and (not last or last < scheduled):
            return True
    return False


def run_due_jobs(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or _now()
    results = []
    for job in load_jobs():
        if _slot_due(job, now):
            results.append(run_job(job, trigger="SCHEDULED"))
    return results


def render_market_intelligence() -> None:
    import pandas as pd
    import streamlit as st

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
    }
    </style>""", unsafe_allow_html=True)
    st.markdown("#### ⏰ Scheduled Market Intelligence & PDF Reports")
    st.caption("Lag flere jobbprofiler med valgfri kombinasjon av markeder, tidspunkter, moduler og varsler. Jobbene kan kjøre analyse, teoretiske porteføljebeslutninger og kontrollert læring. Ingen ekte handler utføres.")
    try:
        from scheduler_background import kick_scheduler_background, scheduler_status
        kick_scheduler_background()
        background = scheduler_status()
        if background.get("state") == "RUNNING": st.caption("⏳ Scheduler kontrolleres i bakgrunnen. Jobbprofilene kan brukes mens kontrollen pågår.")
        elif background.get("state") == "ERROR": st.warning(f"Bakgrunnsscheduler feilet: {background.get('error')}")
        elif int(background.get("runs", 0)) > 0: st.success(f"{background.get('runs')} planlagt(e) jobb(er) ble kjørt i bakgrunnen.")
    except Exception as exc:
        st.warning(f"Bakgrunnsscheduler kunne ikke startes: {exc}")

    tab_jobs, tab_latest, tab_reports, tab_accuracy, tab_history, tab_ops = st.tabs(["Jobbprofiler", "Siste rapport", "Rapporter", "Accuracy Analytics", "Historikk", "Drift"])
    with tab_jobs:
        jobs = load_jobs()
        labels = ["Ny jobb"] + [f"{x.name} ({x.job_id})" for x in jobs]
        selected = st.selectbox("Rediger jobb", labels, key="mi_job_select_v18687")
        current = None if selected == "Ny jobb" else jobs[labels.index(selected)-1]
        name = st.text_input("Jobbnavn", value=current.name if current else "Morgenanalyse", key="mi_name_v18687")
        c1, c2 = st.columns(2)
        with c1:
            market_choices = ["Alle"] + list(BASE_MARKET_SCOPES)
            markets = st.multiselect("Markeder (kan kombineres)", market_choices, default=current.markets if current else ["Alle"], key="mi_markets_v18687")
            schedules = st.multiselect("Faste tidspunkter (kan kombineres)", SCHEDULE_OPTIONS, default=current.schedules if current else ["08:30", "22:30"], key="mi_schedules_v18690")
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
            if st.button("Velg mandag–fredag", key="mi_select_weekdays_v1870", use_container_width=True):
                st.session_state["mi_days_v1870"] = WEEKDAY_NAMES[:5]
            weekday_names = st.multiselect("Ukedager", day_options, default=default_days, key="mi_days_v1870")
        with c2:
            modules = st.multiselect("Pipeline-moduler", MODULE_OPTIONS, default=current.modules if current else MODULE_OPTIONS, key="mi_modules_v18687")
            current_limit = int(current.scan_limit if current else 25)
            reverse_profile = {10: "Rask (10)", 25: "Normal (25)", 50: "Grundig (50)"}
            default_profile = reverse_profile.get(current_limit, "Egendefinert")
            scan_profile = st.selectbox("Skanneprofil per marked", list(SCAN_PROFILES), index=list(SCAN_PROFILES).index(default_profile), key="mi_scan_profile_v18693")
            scan_limit = SCAN_PROFILES[scan_profile]
            if scan_limit is None:
                scan_limit = st.number_input("Egendefinert antall per marked", 10, 250, current_limit, 5, key="mi_scan_custom_v18693")
            st.caption(f"Planlagt maksimum: {int(scan_limit) * len(normalize_markets(markets or ['Norge']))} aksjer ({int(scan_limit)} per marked).")
            deep = st.number_input("Grundig analyse av topp", 1, 100, current.deep_count if current else 20, 1, key="mi_deep_v18687")
            proposals = st.number_input("Antall forslag", 1, 30, current.proposal_count if current else 5, 1, key="mi_prop_v18687")
        n1, n2, n3, n4 = st.columns(4)
        notify = n1.checkbox("Pushover", value=current.notify_pushover if current else True, key="mi_push_v18687")
        only_changes = n2.checkbox("Bare ved endringer", value=current.notify_only_changes if current else True, key="mi_changes_v18687")
        save_pdf = n3.checkbox("Lagre PDF", value=current.save_pdf if current else True, key="mi_pdf_v18687")
        enabled = n4.checkbox("Aktiv jobb", value=current.enabled if current else True, key="mi_enabled_v18687")
        p1, p2 = st.columns(2)
        include_report_link = p1.checkbox("Lenke til siste rapport", value=current.include_report_link if current else True, key="mi_report_link_v1870", help="Krever REPORT_BASE_URL i miljøvariabler.")
        include_top3 = p2.checkbox("Top 3 i varsel", value=current.include_top3_in_notification if current else True, key="mi_top3_push_v1870")
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        min_score = st.number_input("Minste score for varsel", 0, 100, int(current.min_alert_score if current else 80), 1, key="mi_min_score_v1870", help="Tallfelt brukes på mobil for å unngå utilsiktet endring av slider.")
        r1, r2 = st.columns(2)
        reset_alerts = r1.button("↺ Tilbakestill varselstandard", key="mi_reset_alerts_v1870", use_container_width=True)
        reset_all = r2.button("↺ Tilbakestill hele jobbprofilen", key="mi_reset_all_v1870", use_container_width=True)
        if reset_alerts:
            for key, value in {"mi_push_v18687": True, "mi_changes_v18687": True, "mi_pdf_v18687": True, "mi_min_score_v1870": 80, "mi_report_link_v1870": True, "mi_top3_push_v1870": True}.items(): st.session_state[key] = value
            st.rerun()
        if reset_all:
            defaults = load_draft_job()
            defaults.name = "Morgenanalyse"; defaults.markets=["Alle"]; defaults.schedules=["08:30"]; defaults.weekdays=[0,1,2,3,4]; defaults.scan_limit=25; defaults.deep_count=20; defaults.proposal_count=5; defaults.min_alert_score=80; defaults.allow_weekends=False
            write_persistent_json(DRAFT_STORAGE_KEY, asdict(defaults))
            for key in list(st.session_state):
                if str(key).startswith("mi_"): del st.session_state[key]
            st.rerun()
        st.markdown("##### Etter skanningen")
        o1,o2,o3 = st.columns(3)
        run_auto = o1.checkbox("Kjør teoretisk portefølje", value=current.run_autonomous_portfolio if current else True, key="mi_auto_port_v18690")
        run_learning = o2.checkbox("Kjør kontrollert læring", value=current.run_controlled_learning if current else True, key="mi_auto_learning_v18690")
        require_active = o3.checkbox("Krev aktiv portefølje", value=current.require_active_portfolio if current else True, key="mi_require_active_v18690", help="Når valgt hoppes simulerte handler over dersom porteføljen er pauset.")
        draft_job = JobProfile(
            name=name.strip() or "Uten navn", markets=markets or ["Norge"], schedules=schedules or [],
            weekdays=[WEEKDAY_NAMES.index(x) for x in weekday_names], modules=modules or ["Market Scanner"],
            scan_limit=int(scan_limit), deep_count=int(deep), proposal_count=int(proposals), min_alert_score=float(min_score),
            notify_pushover=notify, notify_only_changes=only_changes, include_report_link=include_report_link,
            include_top3_in_notification=include_top3, allow_weekends=allow_weekends, save_pdf=save_pdf, enabled=False,
            scan_windows=scan_windows, run_autonomous_portfolio=run_auto, run_controlled_learning=run_learning, require_active_portfolio=require_active,
            job_id=DRAFT_JOB_ID, created_at=current.created_at if current else _now_iso(),
            last_run_at=current.last_run_at if current else "", last_status="UTKAST",
        )
        save_draft_job(draft_job)
        st.caption("💾 Utkastet lagres automatisk. Testkjøring oppretter ikke eller aktiverer en tidsplan.")

        b1, b2, b3 = st.columns(3)
        if b1.button("▶ Test gjeldende oppsett", type="primary", use_container_width=True, key="mi_test_draft_v18692a"):
            with st.spinner("Kjører test fra automatisk lagret utkast..."):
                st.session_state["mi_latest_v18687"] = run_job(draft_job, trigger="MANUAL_DRAFT_TEST")
            st.success("Testkjøringen er fullført. Oppsettet er fortsatt bare et utkast.")
            st.rerun()
        if b2.button("Lagre og aktiver tidsplan", use_container_width=True, key="mi_save_activate_v18692a"):
            same_name = next((x for x in jobs if x.name.strip().casefold() == draft_job.name.strip().casefold()), None)
            target = current or same_name
            job = JobProfile(**{**asdict(draft_job),
                              "job_id": target.job_id if target else f"MIJ-{uuid.uuid4().hex[:10].upper()}",
                              "created_at": target.created_at if target else _now_iso(),
                              "last_run_at": target.last_run_at if target else "",
                              "last_status": target.last_status if target else "ALDRI KJØRT",
                              "enabled": bool(enabled)})
            upsert_job(job)
            st.success("Jobben er lagret. Tidsplanen er aktivert dersom «Aktiv jobb» er valgt.")
            st.rerun()
        if current and b3.button("Slett lagret jobb", use_container_width=True, key="mi_delete_v18692a"):
            delete_job(current.job_id); st.success("Jobben er slettet. Det automatisk lagrede utkastet beholdes."); st.rerun()
        if jobs:
            st.dataframe(pd.DataFrame([{"Jobb": x.name, "Markeder": ", ".join(x.markets), "Tid": ", ".join(x.schedules), "Tidsrom": "; ".join(f"{w.get('start')}-{w.get('end')} / {w.get('interval_minutes')}m" for w in x.scan_windows), "Autonom kjede": x.run_autonomous_portfolio, "Aktiv": x.enabled,
                                       "Sist kjørt": x.last_run_at or "-", "Status": x.last_status} for x in jobs]), use_container_width=True, hide_index=True)

    latest = st.session_state.get("mi_latest_v18687") or _read(LATEST_PATH, {})
    with tab_latest:
        if not latest:
            st.info("Ingen Scheduled Market Intelligence-rapport er generert ennå.")
        else:
            identity = resolve_report_identity(latest)
            st.markdown(f"### {identity.get('label', 'Rapport')} · {latest.get('job_name', '-')}")
            st.caption(f"Rapporttype: {identity.get('type', '-')} · Kjøring: {latest.get('run_id', '-')}")
            if latest.get("analysis_aborted"):
                st.error("Analyse avbrutt – utilstrekkelige data. Medaljer, anbefalinger og porteføljeforslag er deaktivert for denne kjøringen.")
            s = latest.get("summary") or {}; ch = latest.get("changes") or {}
            scan_cfg = latest.get("scan_configuration") or {}
            a,b,c,d,e = st.columns(5)
            a.metric("Skannet", s.get("scanned",0), f"Planlagt maks {scan_cfg.get('planned_maximum', 0)}")
            b.metric("Grundig analysert", s.get("deep_analyzed",0))
            c.metric("Forslag", s.get("proposals",0))
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
            candidates = [] if latest.get("analysis_aborted") else list(latest.get("candidates") or [])
            if candidates:
                st.markdown("#### 🏅 Topp 3")
                medals = ["🥇 GULL", "🥈 SØLV", "🥉 BRONSE"]
                medal_candidates = latest.get("diverse_top3") or select_diverse_candidates(candidates, 3)
                cols = st.columns(min(3, len(medal_candidates)))
                for idx, candidate in enumerate(medal_candidates):
                    strengths = {"AI Discovery": candidate.get("discovery_score",0), "Fundamentaler": candidate.get("fundamental_score",0), "Research": candidate.get("research_score",0), "Validering": candidate.get("validation_score",0), "Porteføljetilpasning": candidate.get("portfolio_fit_score",0), "Insider": (candidate.get("raw") or {}).get("insider_score",50)}
                    strongest = max(strengths, key=lambda k: float(strengths[k] or 0))
                    display_name = str(candidate.get("name") or candidate.get("ticker") or "-")
                    with cols[idx]:
                        st.markdown(f"**{medals[idx]}**")
                        st.markdown(f"### {display_name}")
                        st.caption(f"{candidate.get('ticker','-')} · {candidate.get('market','-')}")
                        st.metric("Score", f"{float(candidate.get('investment_score',0)):.2f}", f"Konf. {float(candidate.get('confidence_score',0)):.1f}%")
                        st.caption(f"Risiko {float(candidate.get('risk_score',0)):.1f} · Vekt {float(candidate.get('proposed_position_pct',0)):.2f}% · {strongest} {float(strengths[strongest] or 0):.1f}")
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
                action = "BUY" if x.get("status") == "ANBEFALT FOR VURDERING" else "WATCH" if x.get("status") == "OBSERVASJONSLISTE" else "REVIEW" if x.get("status") == "KREVER MANUELL VURDERING" else "SKIP"
                table.append({
                    "Rang": x.get("rank"), "Ticker": x.get("ticker"), "Marked": x.get("market"),
                    "Sektor": x.get("sector"), "Score": x.get("investment_score"),
                    "Konfidens": x.get("confidence_score"), "Trend": x.get("trend"),
                    "Endring": x.get("score_delta"), "Risiko": x.get("risk_score"),
                    "Sterkeste faktor": f"{strongest} {float(strengths[strongest] or 0):.1f}",
                    "Handling": action, "Status": x.get("status"),
                })
            if table: st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
            pdf = build_pdf(latest)
            e1,e2 = st.columns(2)
            e1.download_button("Last ned PDF-rapport", pdf, file_name=safe_report_filename(latest, "pdf"), mime="application/pdf", use_container_width=True, key="mi_download_pdf_v18687")
            e2.download_button("Last ned JSON", json.dumps(latest, ensure_ascii=False, indent=2, default=str), file_name=safe_report_filename(latest, "json"), mime="application/json", use_container_width=True, key="mi_download_json_v18687")
    with tab_reports:
        st.markdown("### 📚 Rapportarkiv")
        st.caption("Rapportene lagres i programmet og kan åpnes eller lastes ned fra PC og mobil. Favoritter beskyttes mot opprydding.")
        archive = _load_report_archive()
        q1, q2, q3 = st.columns([2,1,1])
        search = q1.text_input("Søk", placeholder="Ticker, jobbnavn eller rapport-ID", key="mi_archive_search_v1870").strip().casefold()
        type_filter = q2.selectbox("Rapporttype", ["Alle", "MORGENRAPPORT", "UTKAST", "MANUELL_RAPPORT"], key="mi_archive_type_v1870")
        favorites_only = q3.checkbox("Bare favoritter", key="mi_archive_fav_only_v1870")
        filtered = []
        for row in archive:
            hay = " ".join([str(row.get("run_id") or ""), str(row.get("job_name") or ""), " ".join(row.get("tickers") or [])]).casefold()
            if search and search not in hay: continue
            if type_filter != "Alle" and row.get("report_type") != type_filter: continue
            if favorites_only and not row.get("favorite"): continue
            filtered.append(row)
        if not filtered:
            st.info("Ingen rapporter matcher filteret.")
        for row in filtered[:200]:
            label = f"{'⭐ ' if row.get('favorite') else ''}{row.get('report_label','Rapport')} · {row.get('job_name','-')} · {row.get('created_at','-')}"
            with st.expander(label, expanded=False):
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("Anbefalt", row.get("recommended",0)); m2.metric("Topp", row.get("top_ticker") or "-"); m3.metric("Score", row.get("top_score") or 0); m4.metric("Markeder", len(row.get("markets") or []))
                saved_run = load_run(str(row.get("run_id") or ""))
                pdf_path = Path(str(row.get("pdf_path") or ""))
                json_path = Path(str(row.get("json_path") or ""))
                a,b,c = st.columns(3)
                pdf_data = pdf_path.read_bytes() if pdf_path.exists() else (build_pdf(saved_run) if saved_run else None)
                json_data = json_path.read_bytes() if json_path.exists() else (json.dumps(saved_run, ensure_ascii=False, indent=2, default=str).encode("utf-8") if saved_run else None)
                if pdf_data:
                    a.download_button("📄 Last ned PDF", data=pdf_data, file_name=safe_report_filename(saved_run or row, "pdf"), mime="application/pdf", key=f"mi_dl_pdf_{row.get('run_id')}", use_container_width=True)
                if json_data:
                    b.download_button("{ } Last ned JSON", data=json_data, file_name=safe_report_filename(saved_run or row, "json"), mime="application/json", key=f"mi_dl_json_{row.get('run_id')}", use_container_width=True)
                fav_label = "Fjern favoritt" if row.get("favorite") else "⭐ Favoritt"
                if c.button(fav_label, key=f"mi_fav_{row.get('run_id')}", use_container_width=True):
                    set_report_favorite(str(row.get("run_id")), not bool(row.get("favorite"))); st.rerun()
                confirm = st.checkbox("Bekreft permanent sletting", key=f"mi_confirm_delete_{row.get('run_id')}")
                if st.button("🗑 Slett rapport", key=f"mi_delete_report_{row.get('run_id')}", disabled=not confirm, use_container_width=True):
                    delete_archived_report(str(row.get("run_id"))); st.rerun()

    with tab_accuracy:
        from historical_learning import render_accuracy_analytics
        render_accuracy_analytics()

    with tab_history:
        rows = []
        for archived in _load_report_archive()[:100]:
            r = load_run(str(archived.get("run_id") or "")) or archived; identity = resolve_report_identity(r); rows.append({"Type": identity.get("label"), "Kjøring": r.get("run_id"), "Tid": r.get("created_at"), "Jobb": r.get("job_name"), "Markeder": ", ".join(r.get("markets",[])), "Skannet": (r.get("summary") or {}).get("scanned",0), "Forslag": (r.get("summary") or {}).get("proposals",0), "Feil": len(r.get("errors") or [])})
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.caption("Ingen historiske kjøringer.")
    with tab_ops:
        jobs = load_jobs(); active = [x for x in jobs if x.enabled]
        archive_count = len(_load_report_archive()); o1,o2,o3,o4 = st.columns(4); o1.metric("Jobber", len(jobs)); o2.metric("Aktive", len(active)); o3.metric("Kjøringer", archive_count); o4.metric("Regenererbare PDF-er", archive_count)
        st.code("Ekstern scheduler/cron: python market_intelligence.py --run-due", language="bash")
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
