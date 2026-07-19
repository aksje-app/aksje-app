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
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Mapping, Sequence, Callable

from investment_pipeline import PipelineConfig, _load_candidate_rows_from_app, infer_market_from_ticker, normalize_candidate_identity, run_pipeline
from market_universe import BASE_MARKET_SCOPES, expand_market_scope
from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json

VERSION = "v18.6.93d"
ROOT = runtime_data_path("market_intelligence")
JOBS_PATH = ROOT / "jobs.json"
RUNS_DIR = ROOT / "runs"
SUMMARIES_DIR = ROOT / "summaries"
HISTORY_PATH = ROOT / "candidate_history.json"
NOTIFICATIONS_PATH = ROOT / "notifications.json"
LATEST_PATH = ROOT / "latest_run.json"
AUDIT_PATH = ROOT / "audit.jsonl"
DRAFT_STORAGE_KEY = "market_intelligence/draft_job.json"
DRAFT_JOB_ID = "MI-DRAFT-AUTOSAVE"

MODULE_OPTIONS = [
    "Market Scanner", "AI Discovery", "AI Research Assistant", "Strategy Match",
    "Backtesting Validation", "Portfolio Optimizer", "Learning Advisor",
]
SCHEDULE_OPTIONS = ["Ved appstart", "08:30", "12:00", "15:00", "16:30", "22:30"]
DEFAULT_SCAN_WINDOWS = [{"start": "08:00", "end": "10:00", "interval_minutes": 30}]
WEEKDAY_NAMES = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

SCAN_PROFILES = {"Rask (10)": 10, "Normal (25)": 25, "Grundig (50)": 50, "Egendefinert": None}
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
        weekday_open = local.weekday() < 5
        within_hours = open_at <= local.time().replace(tzinfo=None) <= close_at
        status = "ÅPEN" if weekday_open and within_hours else "STENGT"
        reason = "Innenfor ordinær åpningstid" if status == "ÅPEN" else ("Helg" if not weekday_open else "Utenfor ordinær åpningstid")
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
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _audit(event: str, payload: Mapping[str, Any]) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": _now_iso(), "event": event, **dict(payload)}
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def normalize_markets(markets: Sequence[str]) -> list[str]:
    chosen = [str(x) for x in markets if str(x)]
    if "Alle" in chosen:
        return list(BASE_MARKET_SCOPES)
    valid = set(BASE_MARKET_SCOPES)
    return [x for x in chosen if x in valid] or ["Norge"]


def report_identity(trigger: str) -> dict[str, str]:
    trigger_key = str(trigger or "").upper()
    if "DRAFT" in trigger_key or "TEST" in trigger_key:
        return {"type": "UTKAST", "label": "Utkast", "slug": "UTKAST"}
    if trigger_key == "SCHEDULED":
        return {"type": "MORGENRAPPORT", "label": "Morgenrapport", "slug": "Morgenrapport"}
    return {"type": "MANUELL_RAPPORT", "label": "Manuell rapport", "slug": "Manuell_rapport"}


def safe_report_filename(run: Mapping[str, Any], extension: str = "pdf") -> str:
    identity = run.get("report_identity") or report_identity(str(run.get("trigger") or ""))
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
        return cls(**{k: v for k, v in dict(value).items() if k in allowed})


def load_jobs() -> list[JobProfile]:
    data = read_persistent_json("market_intelligence/jobs.json", default=None)
    if data is None:
        data = _read(JOBS_PATH, [])
        if data:
            write_persistent_json("market_intelligence/jobs.json", data)
    return [JobProfile.from_dict(x) for x in data if isinstance(x, Mapping)]


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
        top = (run.get("proposals") or [{}])[0]
        message = (
            f"Jobb: {job.name}\nMarkeder: {', '.join(run.get('markets', []))}\n"
            f"Analysert: {run.get('summary', {}).get('scanned', 0)}\n"
            f"Nye: {len(changes.get('new', []))} | Forbedret: {len(changes.get('improved', []))}\n"
            f"Topp: {top.get('ticker', '-')} ({top.get('investment_score', '-')})"
        )
        ok, err = send_pushover_alert(message, title="Scheduled Market Intelligence")
        return bool(ok), str(err or "Sendt")
    except Exception as exc:
        return False, str(exc)


def build_pdf(run: Mapping[str, Any], report_type: str | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = run.get("report_identity") or report_identity(str(run.get("trigger") or ""))
    report_type = report_type or f"{identity.get('label', 'Rapport')} – Market Intelligence"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=16*mm, bottomMargin=16*mm,
                            title=report_type, author="AI Aksje Analyzer Pro")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Cover", parent=styles["Title"], alignment=TA_CENTER, fontSize=24, leading=30, spaceAfter=18))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    story = [Spacer(1, 30*mm), Paragraph("AI Aksje Analyzer Pro", styles["Cover"]),
             Paragraph(report_type, styles["Heading1"]), Spacer(1, 3*mm),
             Paragraph(f"<b>Rapporttype: {identity.get('type', '-')}</b>", styles["Heading2"]), Spacer(1, 5*mm),
             Paragraph(f"Jobb: {run.get('job_name', '-')}", styles["BodyText"]),
             Paragraph(f"Rapport-ID: {run.get('run_id', '-')}", styles["BodyText"]),
             Paragraph(f"Generert: {run.get('created_at', '-')}", styles["BodyText"]),
             Paragraph(f"Markeder: {', '.join(run.get('markets') or run.get('market_expansion') or [])}", styles["BodyText"]), PageBreak()]
    summary = run.get("summary") or {}
    story += [Paragraph("Executive Summary", styles["Heading1"]),
              Table([["Skannet", summary.get("scanned", 0)], ["Grundig analysert", summary.get("deep_analyzed", 0)],
                     ["Investeringsforslag", summary.get("proposals", 0)], ["Anbefalt", summary.get("recommended", 0)]], colWidths=[70*mm, 35*mm]), Spacer(1, 6*mm)]
    diagnostics = run.get("market_diagnostics") or []
    if diagnostics:
        diag_data = [["Marked", "Skannet", "Analysert", "Live", "Feil", "Status"]]
        for item in diagnostics:
            diag_data.append([item.get("market"), item.get("scanned", 0), item.get("analyzed", 0), item.get("live", 0), item.get("errors", 0), item.get("status", "-")])
        diag_table = Table(diag_data, repeatRows=1, colWidths=[30*mm, 24*mm, 27*mm, 20*mm, 20*mm, 40*mm])
        diag_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7)]))
        story += [Paragraph("Analysefordeling per marked", styles["Heading2"]), diag_table, Spacer(1, 5*mm)]
    market_status = run.get("market_status") or []
    if market_status:
        ms_data = [["Marked", "Status", "Lokal tid", "Forklaring", "Siste handelsdato"]]
        for item in market_status:
            ms_data.append([item.get("market"), item.get("status"), item.get("local_time"), item.get("reason"), item.get("latest_trade_date") or "Ukjent"])
        ms_table = Table(ms_data, repeatRows=1, colWidths=[24*mm, 20*mm, 20*mm, 55*mm, 38*mm])
        ms_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7)]))
        story += [Paragraph("Markedsstatus", styles["Heading2"]), ms_table, Spacer(1, 4*mm)]
    quality = run.get("data_quality") or {}
    if quality:
        story += [Paragraph("Datakvalitet", styles["Heading2"]), Table([["Kvalitetsscore", f"{quality.get('score', 0)} %"], ["Vurdering", quality.get("label", "-")], ["Live", quality.get("live", 0)], ["Cache", quality.get("cache", 0)], ["Feil", quality.get("errors", 0)]], colWidths=[70*mm, 55*mm]), Spacer(1, 5*mm)]
    refresh = run.get("data_refresh") or {}
    story += [Paragraph("Datainnhenting og cachekontroll", styles["Heading2"]),
              Table([
                  ["Full ny analyse valgt", "JA" if refresh.get("force_refresh_requested") else "NEI"],
                  ["Cache-bypass verifisert", "JA" if refresh.get("cache_bypass_verified") else ("IKKE RELEVANT" if not refresh.get("force_refresh_requested") else "NEI")],
                  ["Live-forsøk", refresh.get("live_attempt_count", 0)],
                  ["Vellykkede live-hentinger", refresh.get("live_count", 0)],
                  ["Cache-hentinger", refresh.get("cache_count", 0)],
                  ["Feilede hentinger", refresh.get("error_count", 0)],
                  ["Nyeste handelsdato(er)", ", ".join(refresh.get("latest_trade_dates") or []) or "Ukjent"],
                  ["Uendrede markedsdata", f"{refresh.get('unchanged_market_data_count', 0)} av {refresh.get('comparable_market_data_count', 0)} sammenlignbare"],
                  ["Verifikasjon", refresh.get("verification_reason", "-")],
              ], colWidths=[70*mm, 85*mm]), Spacer(1, 6*mm)]
    trace_rows = refresh.get("execution_trace") or []
    if trace_rows:
        trace_data = [["Ticker", "Kilde", "Status", "Cache-bypass", "Siste handelsdato", "Endret"]]
        for item in trace_rows[:30]:
            changed = item.get("market_data_changed")
            trace_data.append([item.get("ticker"), item.get("data_source"), item.get("data_fetch_status"),
                               "JA" if item.get("cache_bypass_applied") else "NEI", item.get("latest_trade_date") or "Ukjent",
                               "JA" if changed is True else ("NEI" if changed is False else "IKKE SAMMENLIGNBAR")])
        trace_table = Table(trace_data, repeatRows=1, colWidths=[22*mm, 30*mm, 24*mm, 25*mm, 34*mm, 30*mm])
        trace_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey),
                                         ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 6.5), ("VALIGN", (0,0), (-1,-1), "TOP")]))
        story += [Paragraph("Kjøringsbevis per ticker", styles["Heading2"]), trace_table, Spacer(1, 6*mm)]
    changes = run.get("changes") or {}
    story += [Paragraph("Endringer siden forrige kjøring", styles["Heading2"]),
              Table([["Nye", len(changes.get("new", []))], ["Forbedret", len(changes.get("improved", []))],
                     ["Svekket", len(changes.get("weakened", []))], ["Utgått", len(changes.get("dropped", []))]], colWidths=[70*mm, 35*mm]), Spacer(1, 6*mm)]
    candidates = run.get("candidates") or []
    if run.get("analysis_aborted"):
        story += [Paragraph("Analyse avbrutt – utilstrekkelige data", styles["Heading1"]),
                  Paragraph("Alle tilgjengelige live-hentinger feilet. Rangering, medaljer, anbefalinger og teoretisk portefølje er derfor deaktivert for denne kjøringen.", styles["BodyText"])]
    elif candidates:
        medal_labels = ["1. BESTE KANDIDAT", "2. NUMMER TO", "3. NUMMER TRE"]
        medal_data = []
        for idx, r in enumerate(candidates[:3]):
            strongest = max((("AI Discovery", r.get("discovery_score", 0)), ("Fundamentaler", r.get("fundamental_score", 0)), ("Research", r.get("research_score", 0)), ("Validering", r.get("validation_score", 0)), ("Porteføljetilpasning", r.get("portfolio_fit_score", 0))), key=lambda x: float(x[1] or 0))
            medal_data.append([Paragraph(f"<b>{medal_labels[idx]}</b><br/>{r.get('ticker','-')} · {r.get('market','-')}<br/>Score {r.get('investment_score',0)} · Konf. {r.get('confidence_score',0)} %<br/>Sterkest: {strongest[0]} {float(strongest[1] or 0):.1f}", styles["Small"])])
        medal_table = Table([medal_data], colWidths=[55*mm]*len(medal_data))
        medal_table.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .6, colors.grey), ("INNERGRID", (0,0), (-1,-1), .35, colors.lightgrey), ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F9FC")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
        story += [Paragraph("Topp 3", styles["Heading1"]), medal_table, Spacer(1, 6*mm)]
        data = [["#", "Ticker", "Marked", "Score", "Konf.", "Trend", "Risiko", "Status"]]
        for r in candidates[:10]:
            data.append([r.get("rank"), r.get("ticker"), r.get("market"), r.get("investment_score"), r.get("confidence_score"), r.get("trend"), r.get("risk_score"), str(r.get("status", ""))[:22]])
        table = Table(data, repeatRows=1, colWidths=[8*mm, 20*mm, 22*mm, 16*mm, 16*mm, 20*mm, 16*mm, 52*mm])
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey),
                                   ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))
        story += [Paragraph("Top 10", styles["Heading1"]), table]
    for p in run.get("proposals") or []:
        story += [PageBreak(), Paragraph(f"{p.get('ticker')} - investeringsforslag", styles["Heading1"]),
                  Paragraph(f"Status: {p.get('status')} | Investment Score: {p.get('investment_score')}/100 | Konfidens: {p.get('confidence_score', 0)}/100 | Trend: {p.get('trend', 'NY')}", styles["BodyText"]),
                  Spacer(1, 3*mm), Paragraph("Scorekort", styles["Heading2"]),
                  Table([["AI Discovery", p.get("discovery_score")], ["Fundamentalt", p.get("fundamental_score")],
                         ["Research", p.get("research_score")], ["Backtesting", p.get("validation_score")],
                         ["Porteføljetilpasning", p.get("portfolio_fit_score")], ["Risiko", p.get("risk_score")]], colWidths=[70*mm, 35*mm]),
                  Paragraph("Positive drivere", styles["Heading2"])]
        story += [Paragraph("- " + str(x), styles["BodyText"]) for x in p.get("positives") or []]
        story += [Paragraph("Risiko", styles["Heading2"])] + [Paragraph("- " + str(x), styles["BodyText"]) for x in p.get("risks") or []]
        story += [Paragraph("Handelsramme", styles["Heading2"]), Paragraph(f"Strategi: {p.get('strategy_match')} | Foreslått porteføljevekt: {p.get('proposed_position_pct')} %", styles["BodyText"])]
    portfolio_proposal = run.get("portfolio_proposal") or {}
    allocations = portfolio_proposal.get("allocations") or []
    if allocations:
        story += [PageBreak(), Paragraph("Teoretisk porteføljeforslag", styles["Heading1"]),
                  Paragraph(f"Investert: {portfolio_proposal.get('invested_pct', 0)} % | Kontanter: {portfolio_proposal.get('cash_pct', 100)} %", styles["BodyText"])]
        pdata = [["Ticker", "Marked", "Sektor", "Vekt %", "Score", "Konfidens", "Risiko"]]
        for a in allocations:
            pdata.append([a.get("ticker"), a.get("market"), a.get("sector"), a.get("weight_pct"), a.get("score"), a.get("confidence"), a.get("risk")])
        ptable = Table(pdata, repeatRows=1, colWidths=[24*mm, 24*mm, 38*mm, 18*mm, 18*mm, 20*mm, 18*mm])
        ptable.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7)]))
        story += [ptable]
    story += [PageBreak(), Paragraph("Metode og ansvarsfraskrivelse", styles["Heading1"]),
              Paragraph("Rapporten er automatisk beslutningsstøtte basert på tilgjengelige data. Den er ikke personlig investeringsrådgivning og utfører ingen handler. Alle forslag krever manuell kontroll.", styles["BodyText"])]
    doc.build(story)
    return buf.getvalue()




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
    previous = _read(LATEST_PATH, {})
    def emit(phase: str, completed: int, total: int, message: str, **extra: Any) -> None:
        if progress_callback:
            progress_callback({"phase": phase, "completed": completed, "total": max(1, total), "message": message, **extra})
    emit("START", 0, 1, "Starter markedsskanning")
    market_runs, all_candidates, all_proposals = [], [], []
    market_diagnostics: list[dict[str, Any]] = []
    totals = {"scanned": 0, "deep_analyzed": 0, "proposals": 0, "recommended": 0, "rejected": 0}
    errors = []
    markets = normalize_markets(job.markets)
    for market_index, market in enumerate(markets, start=1):
        cfg = PipelineConfig(market_scope=market, scan_limit=job.scan_limit, deep_analysis_count=job.deep_count,
                             proposal_count=job.proposal_count, use_research="AI Research Assistant" in job.modules,
                             use_backtest="Backtesting Validation" in job.modules,
                             use_portfolio_fit="Portfolio Optimizer" in job.modules,
                             use_learning_advisor="Learning Advisor" in job.modules).normalized()
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
                errors.append(f"{market}/{item.get('ticker') or 'ukjent'} ({item.get('stage')}): {item.get('error')}")
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
           "proposals": all_proposals, "market_runs": market_runs, "errors": errors, "execution": "ANALYSIS_ONLY",
           "data_refresh": refresh_summary, "market_status": market_status, "data_quality": data_quality,
           "analysis_aborted": analysis_aborted,
           "report_identity": report_identity(trigger),
           "market_diagnostics": market_diagnostics,
           "validation": {
               "unique_tickers": len(all_candidates),
               "identity_rejections": identity_rejections,
               "duplicate_count_removed": max(0, sum(len(r.get("candidates") or []) for r in market_runs) - len(all_candidates)),
               "draft_handoff_fingerprint": job_fingerprint(job),
               "report_identity_present": True,
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
    run["portfolio_proposal"] = ({"positions": [], "invested_pct": 0.0, "cash_pct": 100.0, "status": "AVBRUTT_UTILSTREKKELIGE_DATA"}
                                 if analysis_aborted else build_portfolio_proposal(all_candidates))
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
    notify_ok, notify_detail = _notification(job, run)
    run["notification"] = {"sent": notify_ok, "detail": notify_detail}
    if job.save_pdf:
        pdf_path = SUMMARIES_DIR / safe_report_filename(run, "pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(build_pdf(run))
        run["pdf_path"] = str(pdf_path)
    _write(RUNS_DIR / f"{run_id}.json", run)
    _write(LATEST_PATH, run)
    _write(SUMMARIES_DIR / f"{run_id}.json", {k: run[k] for k in ("run_id", "created_at", "job_name", "markets", "summary", "changes", "errors")})
    job.last_run_at, job.last_status = run["created_at"], ("OK" if not errors else "FULLFØRT MED FEIL")
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
    </style>""", unsafe_allow_html=True)
    st.markdown("#### ⏰ Scheduled Market Intelligence & PDF Reports")
    st.caption("Lag flere jobbprofiler med valgfri kombinasjon av markeder, tidspunkter, moduler og varsler. Jobbene kan kjøre analyse, teoretiske porteføljebeslutninger og kontrollert læring. Ingen ekte handler utføres.")
    try:
        due = run_due_jobs()
        if due:
            st.success(f"{len(due)} planlagt(e) jobb(er) ble kjørt.")
    except Exception as exc:
        st.warning(f"Planlagt jobbkontroll kunne ikke fullføres: {exc}")

    tab_jobs, tab_latest, tab_history, tab_ops = st.tabs(["Jobbprofiler", "Siste rapport", "Historikk", "Drift"])
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
            weekday_names = st.multiselect("Ukedager", WEEKDAY_NAMES, default=[WEEKDAY_NAMES[i] for i in (current.weekdays if current else [0,1,2,3,4])], key="mi_days_v18687")
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
        min_score = st.slider("Minste score for varsel", 0, 100, int(current.min_alert_score if current else 80), key="mi_min_score_v18687")
        st.markdown("##### Etter skanningen")
        o1,o2,o3 = st.columns(3)
        run_auto = o1.checkbox("Kjør teoretisk portefølje", value=current.run_autonomous_portfolio if current else True, key="mi_auto_port_v18690")
        run_learning = o2.checkbox("Kjør kontrollert læring", value=current.run_controlled_learning if current else True, key="mi_auto_learning_v18690")
        require_active = o3.checkbox("Krev aktiv portefølje", value=current.require_active_portfolio if current else True, key="mi_require_active_v18690", help="Når valgt hoppes simulerte handler over dersom porteføljen er pauset.")
        draft_job = JobProfile(
            name=name.strip() or "Uten navn", markets=markets or ["Norge"], schedules=schedules or [],
            weekdays=[WEEKDAY_NAMES.index(x) for x in weekday_names], modules=modules or ["Market Scanner"],
            scan_limit=int(scan_limit), deep_count=int(deep), proposal_count=int(proposals), min_alert_score=float(min_score),
            notify_pushover=notify, notify_only_changes=only_changes, save_pdf=save_pdf, enabled=False,
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
            identity = latest.get("report_identity") or report_identity(str(latest.get("trigger") or ""))
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
                medals = ["🥇", "🥈", "🥉"]
                cols = st.columns(min(3, len(candidates)))
                for idx, candidate in enumerate(candidates[:3]):
                    strengths = {"AI Discovery": candidate.get("discovery_score",0), "Fundamentaler": candidate.get("fundamental_score",0), "Research": candidate.get("research_score",0), "Validering": candidate.get("validation_score",0), "Porteføljetilpasning": candidate.get("portfolio_fit_score",0)}
                    strongest = max(strengths, key=lambda k: float(strengths[k] or 0))
                    cols[idx].metric(f"{medals[idx]} {candidate.get('ticker','-')} · {candidate.get('market','-')}", f"{float(candidate.get('investment_score',0)):.2f}", f"Konf. {float(candidate.get('confidence_score',0)):.1f}% · {strongest} {float(strengths[strongest] or 0):.1f}")
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
    with tab_history:
        files = sorted(RUNS_DIR.glob("MI-*.json"), reverse=True)[:100] if RUNS_DIR.exists() else []
        rows = []
        for path in files:
            r = _read(path, {}); identity = r.get("report_identity") or report_identity(str(r.get("trigger") or "")); rows.append({"Type": identity.get("label"), "Kjøring": r.get("run_id"), "Tid": r.get("created_at"), "Jobb": r.get("job_name"), "Markeder": ", ".join(r.get("markets",[])), "Skannet": (r.get("summary") or {}).get("scanned",0), "Forslag": (r.get("summary") or {}).get("proposals",0), "Feil": len(r.get("errors") or [])})
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.caption("Ingen historiske kjøringer.")
    with tab_ops:
        jobs = load_jobs(); active = [x for x in jobs if x.enabled]
        o1,o2,o3,o4 = st.columns(4); o1.metric("Jobber", len(jobs)); o2.metric("Aktive", len(active)); o3.metric("Kjøringer", len(list(RUNS_DIR.glob('*.json'))) if RUNS_DIR.exists() else 0); o4.metric("PDF-rapporter", len(list(SUMMARIES_DIR.glob('*.pdf'))) if SUMMARIES_DIR.exists() else 0)
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
