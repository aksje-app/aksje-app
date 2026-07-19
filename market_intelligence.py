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
from pathlib import Path
from typing import Any, Mapping, Sequence

from investment_pipeline import PipelineConfig, _load_candidate_rows_from_app, run_pipeline
from market_universe import BASE_MARKET_SCOPES, expand_market_scope
from storage_architecture import runtime_data_path
from persistent_config_store import read_persistent_json, write_persistent_json

VERSION = "v18.6.92"
ROOT = runtime_data_path("market_intelligence")
JOBS_PATH = ROOT / "jobs.json"
RUNS_DIR = ROOT / "runs"
SUMMARIES_DIR = ROOT / "summaries"
HISTORY_PATH = ROOT / "candidate_history.json"
NOTIFICATIONS_PATH = ROOT / "notifications.json"
LATEST_PATH = ROOT / "latest_run.json"
AUDIT_PATH = ROOT / "audit.jsonl"

MODULE_OPTIONS = [
    "Market Scanner", "AI Discovery", "AI Research Assistant", "Strategy Match",
    "Backtesting Validation", "Portfolio Optimizer", "Learning Advisor",
]
SCHEDULE_OPTIONS = ["Ved appstart", "08:30", "12:00", "15:00", "16:30", "22:30"]
DEFAULT_SCAN_WINDOWS = [{"start": "08:00", "end": "10:00", "interval_minutes": 30}]
WEEKDAY_NAMES = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]


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


@dataclass
class JobProfile:
    name: str
    markets: list[str] = field(default_factory=lambda: ["Alle"])
    schedules: list[str] = field(default_factory=lambda: ["08:30", "22:30"])
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    modules: list[str] = field(default_factory=lambda: list(MODULE_OPTIONS))
    scan_limit: int = 100
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
        row = {**cur[ticker], "score_delta": delta, "previous_rank": prev[ticker].get("rank")}
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


def build_pdf(run: Mapping[str, Any], report_type: str = "Market Intelligence Report") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=16*mm, bottomMargin=16*mm,
                            title=report_type, author="AI Aksje Analyzer Pro")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Cover", parent=styles["Title"], alignment=TA_CENTER, fontSize=24, leading=30, spaceAfter=18))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    story = [Spacer(1, 30*mm), Paragraph("AI Aksje Analyzer Pro", styles["Cover"]),
             Paragraph(report_type, styles["Heading1"]), Spacer(1, 8*mm),
             Paragraph(f"Rapport-ID: {run.get('run_id', '-')}", styles["BodyText"]),
             Paragraph(f"Generert: {run.get('created_at', '-')}", styles["BodyText"]),
             Paragraph(f"Markeder: {', '.join(run.get('markets') or run.get('market_expansion') or [])}", styles["BodyText"]), PageBreak()]
    summary = run.get("summary") or {}
    story += [Paragraph("Executive Summary", styles["Heading1"]),
              Table([["Skannet", summary.get("scanned", 0)], ["Grundig analysert", summary.get("deep_analyzed", 0)],
                     ["Investeringsforslag", summary.get("proposals", 0)], ["Anbefalt", summary.get("recommended", 0)]], colWidths=[70*mm, 35*mm]), Spacer(1, 6*mm)]
    changes = run.get("changes") or {}
    story += [Paragraph("Endringer siden forrige kjøring", styles["Heading2"]),
              Table([["Nye", len(changes.get("new", []))], ["Forbedret", len(changes.get("improved", []))],
                     ["Svekket", len(changes.get("weakened", []))], ["Utgått", len(changes.get("dropped", []))]], colWidths=[70*mm, 35*mm]), Spacer(1, 6*mm)]
    candidates = run.get("candidates") or []
    if candidates:
        data = [["#", "Ticker", "Marked", "Score", "Konf.", "Trend", "Risiko", "Status"]]
        for r in candidates[:30]:
            data.append([r.get("rank"), r.get("ticker"), r.get("market"), r.get("investment_score"), r.get("confidence_score"), r.get("trend"), r.get("risk_score"), str(r.get("status", ""))[:22]])
        table = Table(data, repeatRows=1, colWidths=[8*mm, 20*mm, 22*mm, 16*mm, 16*mm, 20*mm, 16*mm, 52*mm])
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E9EEF5")), ("GRID", (0,0), (-1,-1), .35, colors.grey),
                                   ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))
        story += [Paragraph("Rangert kandidatliste", styles["Heading1"]), table]
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


def run_job(job: JobProfile, trigger: str = "MANUAL") -> dict[str, Any]:
    previous = _read(LATEST_PATH, {})
    market_runs, all_candidates, all_proposals = [], [], []
    totals = {"scanned": 0, "deep_analyzed": 0, "proposals": 0, "recommended": 0, "rejected": 0}
    errors = []
    markets = normalize_markets(job.markets)
    for market in markets:
        cfg = PipelineConfig(market_scope=market, scan_limit=job.scan_limit, deep_analysis_count=job.deep_count,
                             proposal_count=job.proposal_count, use_research="AI Research Assistant" in job.modules,
                             use_backtest="Backtesting Validation" in job.modules,
                             use_portfolio_fit="Portfolio Optimizer" in job.modules,
                             use_learning_advisor="Learning Advisor" in job.modules).normalized()
        try:
            rows, source = _load_candidate_rows_from_app(cfg)
            if not rows:
                errors.append(f"{market}: ingen kandidater")
                continue
            result = run_pipeline(rows, cfg)
            result["candidate_source"] = source
            market_runs.append(result)
            all_candidates.extend(result.get("candidates") or [])
            all_proposals.extend(result.get("proposals") or [])
            for key in totals:
                totals[key] += int((result.get("summary") or {}).get(key, 0))
        except Exception as exc:
            errors.append(f"{market}: {exc}")
    all_candidates.sort(key=lambda x: float(x.get("investment_score", 0)), reverse=True)
    for idx, row in enumerate(all_candidates, 1):
        row["rank"] = idx
    all_proposals.sort(key=lambda x: float(x.get("investment_score", 0)), reverse=True)
    all_proposals = all_proposals[:job.proposal_count]
    run_id = f"MI-{_now().strftime('%Y%m%d-%H%M%S')}"
    run = {"version": VERSION, "run_id": run_id, "created_at": _now_iso(), "job_id": job.job_id, "job_name": job.name,
           "trigger": trigger, "markets": markets, "modules": job.modules, "summary": totals, "candidates": all_candidates,
           "proposals": all_proposals, "market_runs": market_runs, "errors": errors, "execution": "ANALYSIS_ONLY"}
    from advanced_investment_intelligence import build_portfolio_proposal
    run["portfolio_proposal"] = build_portfolio_proposal(all_candidates)
    run["changes"] = compare_runs(run, previous)
    _update_history(run)
    try:
        from autonomous_orchestrator import run_post_scan_chain
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
    notify_ok, notify_detail = _notification(job, run)
    run["notification"] = {"sent": notify_ok, "detail": notify_detail}
    if job.save_pdf:
        pdf_path = SUMMARIES_DIR / f"{run_id}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(build_pdf(run))
        run["pdf_path"] = str(pdf_path)
    _write(RUNS_DIR / f"{run_id}.json", run)
    _write(LATEST_PATH, run)
    _write(SUMMARIES_DIR / f"{run_id}.json", {k: run[k] for k in ("run_id", "created_at", "job_name", "markets", "summary", "changes", "errors")})
    job.last_run_at, job.last_status = run["created_at"], ("OK" if not errors else "FULLFØRT MED FEIL")
    upsert_job(job)
    _audit("JOB_RUN", {"job_id": job.job_id, "run_id": run_id, "trigger": trigger, "errors": errors})
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
            scan_limit = st.number_input("Maks kandidater", 10, 500, current.scan_limit if current else 100, 10, key="mi_scan_v18687")
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
        b1, b2, b3 = st.columns(3)
        if b1.button("Lagre jobb", type="primary", use_container_width=True, key="mi_save_v18687"):
            job = JobProfile(name=name.strip() or "Uten navn", markets=markets or ["Norge"], schedules=schedules or ["Ved appstart"],
                             weekdays=[WEEKDAY_NAMES.index(x) for x in weekday_names], modules=modules or ["Market Scanner"],
                             scan_limit=int(scan_limit), deep_count=int(deep), proposal_count=int(proposals), min_alert_score=float(min_score),
                             notify_pushover=notify, notify_only_changes=only_changes, save_pdf=save_pdf, enabled=enabled,
                             scan_windows=scan_windows, run_autonomous_portfolio=run_auto, run_controlled_learning=run_learning, require_active_portfolio=require_active,
                             job_id=current.job_id if current else f"MIJ-{uuid.uuid4().hex[:10].upper()}",
                             created_at=current.created_at if current else _now_iso(), last_run_at=current.last_run_at if current else "",
                             last_status=current.last_status if current else "ALDRI KJØRT")
            upsert_job(job); st.success("Jobben er lagret."); st.rerun()
        if current and b2.button("Kjør valgt jobb nå", use_container_width=True, key="mi_run_v18687"):
            with st.spinner("Kjører markedsetterretning..."):
                st.session_state["mi_latest_v18687"] = run_job(current, trigger="MANUAL")
            st.success("Jobben er fullført."); st.rerun()
        if current and b3.button("Slett jobb", use_container_width=True, key="mi_delete_v18687"):
            delete_job(current.job_id); st.success("Jobben er slettet."); st.rerun()
        if jobs:
            st.dataframe(pd.DataFrame([{"Jobb": x.name, "Markeder": ", ".join(x.markets), "Tid": ", ".join(x.schedules), "Tidsrom": "; ".join(f"{w.get('start')}-{w.get('end')} / {w.get('interval_minutes')}m" for w in x.scan_windows), "Autonom kjede": x.run_autonomous_portfolio, "Aktiv": x.enabled,
                                       "Sist kjørt": x.last_run_at or "-", "Status": x.last_status} for x in jobs]), use_container_width=True, hide_index=True)

    latest = st.session_state.get("mi_latest_v18687") or _read(LATEST_PATH, {})
    with tab_latest:
        if not latest:
            st.info("Ingen Scheduled Market Intelligence-rapport er generert ennå.")
        else:
            s = latest.get("summary") or {}; ch = latest.get("changes") or {}
            a,b,c,d = st.columns(4); a.metric("Skannet", s.get("scanned",0)); b.metric("Forslag", s.get("proposals",0)); c.metric("Nye", len(ch.get("new",[]))); d.metric("Forbedret", len(ch.get("improved",[])))
            if latest.get("errors"): st.warning(" | ".join(latest["errors"]))
            table = [{"Rang": x.get("rank"), "Ticker": x.get("ticker"), "Marked": x.get("market"), "Score": x.get("investment_score"), "Konfidens": x.get("confidence_score"), "Trend": x.get("trend"), "Endring": x.get("score_delta"), "Risiko": x.get("risk_score"), "Status": x.get("status")} for x in latest.get("candidates") or []]
            if table: st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
            pdf = build_pdf(latest)
            e1,e2 = st.columns(2)
            e1.download_button("Last ned PDF-rapport", pdf, file_name=f"market_intelligence_{latest.get('run_id','latest')}.pdf", mime="application/pdf", use_container_width=True, key="mi_download_pdf_v18687")
            e2.download_button("Last ned JSON", json.dumps(latest, ensure_ascii=False, indent=2, default=str), file_name=f"market_intelligence_{latest.get('run_id','latest')}.json", mime="application/json", use_container_width=True, key="mi_download_json_v18687")
    with tab_history:
        files = sorted(RUNS_DIR.glob("MI-*.json"), reverse=True)[:100] if RUNS_DIR.exists() else []
        rows = []
        for path in files:
            r = _read(path, {}); rows.append({"Kjøring": r.get("run_id"), "Tid": r.get("created_at"), "Jobb": r.get("job_name"), "Markeder": ", ".join(r.get("markets",[])), "Skannet": (r.get("summary") or {}).get("scanned",0), "Forslag": (r.get("summary") or {}).get("proposals",0), "Feil": len(r.get("errors") or [])})
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
