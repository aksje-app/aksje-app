"""Independent controlled observations and weekly trend reports.

This engine is descriptive only. It cannot authorise trades or apply production
parameters. Point-in-time inputs are frozen; prices and benchmarks are followed
independently from simulated portfolio exits and later report appearances.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from app_version import APP_VERSION
from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

SCHEMA_VERSION = "1.0"
ENGINE_VERSION = "v19.22.0-rc16.31aw"
CORE_MARKETS = ("NORGE", "SVERIGE", "USA")
BENCHMARKS = {"NORGE": "OSEBX.OL", "SVERIGE": "^OMX", "USA": "^GSPC"}
HORIZONS = (1, 5, 20, 60)
GROUP_TARGETS = {"STRICT": 30, "MODERATE": 30, "NEAR_THRESHOLD": 30, "MATCHED_CONTROL": 30}
MAX_ACTIVE_OBSERVATIONS = 120
MAX_ARCHIVED_OBSERVATIONS = 5000
OSLO = ZoneInfo("Europe/Oslo")

OBSERVATIONS_KEY = "controlled_learning/observation_cohorts.json"
OBSERVATIONS_PATH = runtime_data_path("controlled_learning", "observation_cohorts.json")
STATE_KEY = "controlled_learning/observation_engine_state.json"
STATE_PATH = runtime_data_path("controlled_learning", "observation_engine_state.json")
WEEKLY_KEY = "controlled_learning/weekly_reports.json"
WEEKLY_PATH = runtime_data_path("controlled_learning", "weekly_reports.json")


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _market(value: Any, ticker: str = "") -> str:
    text = str(value or "").strip().upper()
    text = {"NORWAY": "NORGE", "SWEDEN": "SVERIGE", "US": "USA", "UNITED STATES": "USA"}.get(text, text)
    if text:
        return text
    symbol = str(ticker or "").upper()
    return "NORGE" if symbol.endswith(".OL") else "SVERIGE" if symbol.endswith(".ST") else "USA"


def _candidate_price(row: Mapping[str, Any]) -> float | None:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for key in ("current_price", "price", "last_price", "regularMarketPrice", "close"):
        for source in (row, raw):
            value = _number(source.get(key))
            if value and value > 0:
                return value
    return None


def _score(row: Mapping[str, Any]) -> float:
    for key in ("investment_score", "final_score", "score"):
        value = _number(row.get(key))
        if value is not None:
            return value
    return 0.0


def _decision_group(row: Mapping[str, Any], threshold: float) -> str:
    code = str(row.get("autonomy_outcome_code") or "").upper()
    if code == "KJØPSKANDIDAT":
        return "STRICT"
    if code == "MODERAT_KJØPSANBEFALING":
        return "MODERATE"
    return "NEAR_THRESHOLD" if _score(row) >= threshold - 6.0 else "CONTROL_POOL"


def _frozen_snapshot(row: Mapping[str, Any], *, group: str, report_id: str, created_at: str) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    readiness = row.get("decision_readiness") if isinstance(row.get("decision_readiness"), Mapping) else {}
    snapshot = {
        "ticker": ticker, "market": _market(row.get("market") or row.get("country"), ticker),
        "sector": str(row.get("sector") or "Ukjent"),
        "strategy": str(row.get("strategy_match") or row.get("strategy") or "Uklassifisert"),
        "group": group, "score": round(_score(row), 4), "risk_score": _number(row.get("risk_score")),
        "data_quality": _number(row.get("data_quality_score") or row.get("data_quality")),
        "confidence_score": _number(row.get("confidence_score")),
        "technical_score": _number(row.get("technical_score")),
        "fundamental_score": _number(row.get("fundamental_score")),
        "news_score": _number(row.get("news_score")), "research_score": _number(row.get("research_score")),
        "validation_score": _number(row.get("validation_score")),
        "portfolio_fit_score": _number(row.get("portfolio_fit_score")),
        "valid_for_decision": row.get("valid_for_decision") is True,
        "evidence_valid_for_decision": row.get("evidence_valid_for_decision") is True,
        "outcome_code": str(row.get("autonomy_outcome_code") or ""),
        "portfolio_action": str(row.get("portfolio_action") or ""),
        "technical_entry_wait": row.get("technical_entry_wait") is True,
        "news_readiness": str(readiness.get("news") or ""),
        "insider_readiness": str(readiness.get("insider") or ""),
        "source_report_id": report_id, "source_created_at": created_at, "program_version": APP_VERSION,
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    snapshot["snapshot_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return snapshot


def load_observations() -> list[dict[str, Any]]:
    value = read_json(OBSERVATIONS_KEY, OBSERVATIONS_PATH, [])
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def save_observations(rows: Sequence[Mapping[str, Any]]) -> None:
    payload = [dict(row) for row in rows]
    active = [row for row in payload if str(row.get("status") or "ACTIVE").upper() == "ACTIVE"]
    archive = [row for row in payload if str(row.get("status") or "ACTIVE").upper() != "ACTIVE"]
    archive.sort(key=lambda row: str(row.get("completed_at") or row.get("registered_at") or ""), reverse=True)
    write_json(OBSERVATIONS_KEY, OBSERVATIONS_PATH, active + archive[:MAX_ARCHIVED_OBSERVATIONS])


def _eligible(row: Mapping[str, Any]) -> bool:
    ticker = str(row.get("ticker") or "").strip().upper()
    return bool(ticker and _market(row.get("market") or row.get("country"), ticker) in CORE_MARKETS
                and _candidate_price(row)
                and str(row.get("coverage_role") or "").upper() != "PORTFOLIO_ONLY_EXISTING_POSITION")


def _matched_controls(recommended: Sequence[Mapping[str, Any]], pool: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    remaining = list(pool); selected: list[Mapping[str, Any]] = []
    for target in sorted(recommended, key=_score, reverse=True):
        if not remaining:
            break
        target_market = _market(target.get("market") or target.get("country"), str(target.get("ticker") or ""))
        target_sector = str(target.get("sector") or "Ukjent")
        choice = min(remaining, key=lambda row: (
            _market(row.get("market") or row.get("country"), str(row.get("ticker") or "")) != target_market,
            str(row.get("sector") or "Ukjent") != target_sector,
            abs(_score(row) - _score(target)), str(row.get("ticker") or "")))
        selected.append(choice); remaining.remove(choice)
    selected.extend(sorted(remaining, key=lambda row: (-_score(row), str(row.get("ticker") or ""))))
    return selected


def register_report_observations(
    run: Mapping[str, Any], *, now: datetime | None = None, commit: bool = True,
) -> dict[str, Any]:
    """Select and optionally commit deterministic observations from one report."""
    report_id = str(run.get("run_id") or run.get("report_id") or "").strip()
    created_at = str(run.get("created_at") or _now_iso(now))
    summary = run.get("report_summary") if isinstance(run.get("report_summary"), Mapping) else {}
    threshold = _number(summary.get("production_buy_threshold"), 73.0) or 73.0
    candidates = [dict(row) for row in (run.get("candidates") or []) if isinstance(row, Mapping) and _eligible(row)]
    rows = load_observations()
    active = [row for row in rows if str(row.get("status") or "ACTIVE").upper() == "ACTIVE"]
    active_tickers = {str(row.get("ticker") or "").upper() for row in active}
    active_by_group: dict[str, int] = defaultdict(int)
    for row in active:
        active_by_group[str(row.get("group") or "UNKNOWN").upper()] += 1
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    pool: list[Mapping[str, Any]] = []; recommended: list[Mapping[str, Any]] = []
    for candidate in candidates:
        group = _decision_group(candidate, threshold)
        if group not in {"STRICT", "MODERATE"}:
            pool.append(candidate)
        if group != "CONTROL_POOL":
            grouped[group].append(candidate)
            if group in {"STRICT", "MODERATE"}:
                recommended.append(candidate)
    grouped["MATCHED_CONTROL"] = _matched_controls(recommended, pool)
    created: list[dict[str, Any]] = []
    for group in ("STRICT", "MODERATE", "NEAR_THRESHOLD", "MATCHED_CONTROL"):
        capacity = max(0, GROUP_TARGETS[group] - active_by_group[group])
        for candidate in sorted(grouped[group], key=lambda row: (-_score(row), str(row.get("ticker") or ""))):
            if capacity <= 0 or len(active) + len(created) >= MAX_ACTIVE_OBSERVATIONS:
                break
            ticker = str(candidate.get("ticker") or "").upper()
            if ticker in active_tickers or any(str(row.get("ticker") or "").upper() == ticker for row in created):
                continue
            snapshot = _frozen_snapshot(candidate, group=group, report_id=report_id, created_at=created_at)
            created.append({
                "schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
                "observation_id": f"LOW-{report_id}-{ticker}-{group}", "ticker": ticker,
                "market": snapshot["market"], "sector": snapshot["sector"], "strategy": snapshot["strategy"],
                "group": group, "benchmark_ticker": BENCHMARKS[snapshot["market"]],
                "registered_at": _now_iso(now), "entry_at": created_at, "entry_market_date": created_at[:10],
                "entry_price": round(float(_candidate_price(candidate) or 0), 6),
                "benchmark_entry_price": None, "benchmark_entry_policy": "PREVIOUS_OFFICIAL_CLOSE",
                "status": "ACTIVE", "decision_snapshot": snapshot, "horizon_measurements": {},
                "daily_marks": [], "source_health": {"status": "PENDING"},
                "production_applied": False, "trade_authorized": False,
            })
            capacity -= 1
    if created and commit:
        save_observations(created + rows)
    return {
        "status": "COMPLETED" if commit else "COMMIT_AFTER_FINAL_GATE", "report_id": report_id,
        "eligible_candidates": len(candidates), "created": len(created),
        "created_by_group": {group: sum(row["group"] == group for row in created) for group in GROUP_TARGETS},
        "active_after": len(active) + len(created), "capacity": MAX_ACTIVE_OBSERVATIONS,
        "committed": bool(commit), "production_changed": False,
    }


SeriesLoader = Callable[[Sequence[str], str], Mapping[str, Sequence[Mapping[str, Any]]]]


def _normalise_series(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, float] = {}
    for row in rows:
        day = str(row.get("date") or row.get("market_date") or "")[:10]
        close = _number(row.get("close") if row.get("close") is not None else row.get("price"))
        if day and close and close > 0:
            by_date[day] = close
    return [{"date": day, "close": by_date[day]} for day in sorted(by_date)]


def _price_on_or_before(series: Sequence[Mapping[str, Any]], day: str, *, strict: bool = False) -> float | None:
    values = [row for row in series if str(row.get("date") or "") < day or (not strict and str(row.get("date") or "") <= day)]
    return _number(values[-1].get("close")) if values else None


def yfinance_series_loader(symbols: Sequence[str], start_date: str) -> dict[str, list[dict[str, Any]]]:
    import yfinance as yf
    clean = sorted({str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()})
    output: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in clean}
    batch_size = max(5, min(30, int(os.getenv("LEARNING_PRICE_BATCH_SIZE", "20") or 20)))
    end = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    for offset in range(0, len(clean), batch_size):
        batch = clean[offset:offset + batch_size]
        frame = yf.download(batch, start=start_date, end=end, interval="1d", progress=False,
                            auto_adjust=True, threads=False, group_by="ticker", timeout=20)
        if frame is None or getattr(frame, "empty", True):
            continue
        for symbol in batch:
            try:
                close = frame["Close"] if len(batch) == 1 else (frame[symbol]["Close"] if symbol in frame.columns.get_level_values(0) else frame["Close"][symbol])
                if hasattr(close, "columns"):
                    close = close.iloc[:, 0]
                output[symbol] = [{"date": index.date().isoformat() if hasattr(index, "date") else str(index)[:10],
                                   "close": float(value)} for index, value in close.dropna().items()]
            except Exception:
                output[symbol] = []
        try:
            from runtime_memory import release_process_memory
            release_process_memory("learning_observation:price_batch")
        except Exception:
            pass
    return output


def load_engine_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def evaluate_observations(series_loader: SeriesLoader | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Backfill 1/5/20/60 trading-day measurements regardless of portfolio exit."""
    rows = load_observations()
    active = [row for row in rows if str(row.get("status") or "ACTIVE").upper() == "ACTIVE"]
    if not active:
        result = {"status": "COMPLETED", "active": 0, "updated": 0, "matured": 0, "missing": 0,
                  "completed_at": _now_iso(now), "production_changed": False}
        write_json(STATE_KEY, STATE_PATH, {**load_engine_state(), "daily": result})
        return result
    start = min(str(row.get("entry_market_date") or "9999-12-31") for row in active)
    start_date = (date.fromisoformat(start) - timedelta(days=10)).isoformat()
    symbols = sorted({str(row.get("ticker")) for row in active} | {str(row.get("benchmark_ticker")) for row in active})
    try:
        loaded = (series_loader or yfinance_series_loader)(symbols, start_date)
    except Exception as exc:
        result = {"status": "FAILED", "active": len(active), "updated": 0, "matured": 0,
                  "missing": len(active), "error": f"{type(exc).__name__}: {exc}",
                  "completed_at": _now_iso(now), "production_changed": False}
        write_json(STATE_KEY, STATE_PATH, {**load_engine_state(), "daily": result})
        return result
    series_map = {symbol: _normalise_series(list(loaded.get(symbol) or [])) for symbol in symbols}
    updated = matured = missing = 0; latest_dates: set[str] = set()
    for observation in active:
        ticker = str(observation.get("ticker") or ""); benchmark = str(observation.get("benchmark_ticker") or "")
        stock = series_map.get(ticker, []); bench = series_map.get(benchmark, [])
        entry_day = str(observation.get("entry_market_date") or "")[:10]
        forward = [row for row in stock if str(row.get("date") or "") > entry_day]
        if not forward or not bench:
            observation["source_health"] = {"status": "MISSING_SERIES", "checked_at": _now_iso(now),
                                             "stock_points": len(stock), "benchmark_points": len(bench)}
            missing += 1; continue
        benchmark_entry = _price_on_or_before(bench, entry_day, strict=True)
        if not benchmark_entry:
            observation["source_health"] = {"status": "MISSING_BENCHMARK_BASELINE", "checked_at": _now_iso(now)}
            missing += 1; continue
        observation["benchmark_entry_price"] = round(benchmark_entry, 6)
        entry_price = _number(observation.get("entry_price")) or 0.0
        measurements = dict(observation.get("horizon_measurements") or {})
        for horizon in HORIZONS:
            if len(forward) < horizon or str(horizon) in measurements:
                continue
            point = forward[horizon - 1]; point_day = str(point["date"]); price = float(point["close"])
            benchmark_price = _price_on_or_before(bench, point_day)
            if not benchmark_price or not entry_price:
                continue
            stock_return = (price / entry_price - 1.0) * 100.0
            benchmark_return = (benchmark_price / benchmark_entry - 1.0) * 100.0
            window = [float(row["close"]) for row in forward[:horizon]]
            measurements[str(horizon)] = {
                "horizon_days": horizon, "market_date": point_day, "measured_at": _now_iso(now),
                "price": round(price, 6), "benchmark_price": round(benchmark_price, 6),
                "return_pct": round(stock_return, 4), "benchmark_return_pct": round(benchmark_return, 4),
                "excess_return_pct": round(stock_return - benchmark_return, 4),
                "maximum_gain_pct": round((max(window) / entry_price - 1.0) * 100.0, 4),
                "maximum_drawdown_pct": round((min(window) / entry_price - 1.0) * 100.0, 4),
            }
            updated += 1
        observation["horizon_measurements"] = measurements
        latest = forward[-1]; latest_day = str(latest["date"]); latest_dates.add(latest_day)
        benchmark_latest = _price_on_or_before(bench, latest_day)
        stock_return = (float(latest["close"]) / entry_price - 1.0) * 100.0 if entry_price else 0.0
        benchmark_return = (benchmark_latest / benchmark_entry - 1.0) * 100.0 if benchmark_latest else 0.0
        marks = [dict(row) for row in (observation.get("daily_marks") or []) if str(row.get("market_date") or "") != latest_day]
        marks.append({"market_date": latest_day, "price": round(float(latest["close"]), 6),
                      "benchmark_price": round(float(benchmark_latest), 6) if benchmark_latest else None,
                      "return_pct": round(stock_return, 4), "benchmark_return_pct": round(benchmark_return, 4),
                      "excess_return_pct": round(stock_return - benchmark_return, 4), "recorded_at": _now_iso(now)})
        observation["daily_marks"] = marks[-70:]
        observation["last_market_date"] = latest_day; observation["last_evaluated_at"] = _now_iso(now)
        observation["source_health"] = {"status": "OK", "checked_at": _now_iso(now),
                                         "stock_points": len(stock), "benchmark_points": len(bench)}
        if "60" in measurements:
            observation["status"] = "MATURED"; observation["completed_at"] = _now_iso(now); matured += 1
    save_observations(rows)
    result = {"status": "COMPLETED" if not missing else "DEGRADED", "active": len(active),
              "updated": updated, "matured": matured, "missing": missing,
              "latest_market_dates": sorted(latest_dates), "completed_at": _now_iso(now), "production_changed": False}
    state = load_engine_state(); state["daily"] = result; write_json(STATE_KEY, STATE_PATH, state)
    return result


def _maturity(count: int) -> str:
    if count < 10: return "FOR_TIDLIG"
    if count < 30: return "FORELØPIG"
    if count < 100: return "UNDER_OPPBYGGING"
    return "MER_ROBUST"


def _stats(values: Sequence[float]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return {"count": len(clean), "average": round(sum(clean) / len(clean), 4) if clean else None,
            "median": round(median(clean), 4) if clean else None,
            "hit_rate_pct": round(sum(value > 0 for value in clean) / len(clean) * 100.0, 2) if clean else None,
            "maturity": _maturity(len(clean))}


def build_weekly_analysis(rows: Sequence[Mapping[str, Any]] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    observations = [dict(row) for row in (rows if rows is not None else load_observations()) if isinstance(row, Mapping)]
    active = [row for row in observations if str(row.get("status") or "ACTIVE").upper() == "ACTIVE"]
    horizon_rows = []
    for horizon in HORIZONS:
        measured = [dict((row.get("horizon_measurements") or {}).get(str(horizon)) or {})
                    for row in observations if isinstance(row.get("horizon_measurements"), Mapping)]
        measured = [row for row in measured if row.get("return_pct") is not None]
        horizon_rows.append({"horizon_days": horizon,
                             "return": _stats([float(row["return_pct"]) for row in measured]),
                             "benchmark_return": _stats([float(row["benchmark_return_pct"]) for row in measured if row.get("benchmark_return_pct") is not None]),
                             "excess_return": _stats([float(row["excess_return_pct"]) for row in measured if row.get("excess_return_pct") is not None])})
    group_rows = []
    for group in GROUP_TARGETS:
        members = [row for row in observations if str(row.get("group") or "") == group]
        for horizon in (5, 20, 60):
            values = [_number(((row.get("horizon_measurements") or {}).get(str(horizon)) or {}).get("excess_return_pct")) for row in members]
            group_rows.append({"group": group, "horizon_days": horizon, **_stats([v for v in values if v is not None])})
    dimension_rows = []
    for dimension in ("market", "sector", "strategy"):
        by_name: dict[str, list[float]] = defaultdict(list)
        for row in observations:
            value = _number(((row.get("horizon_measurements") or {}).get("20") or {}).get("excess_return_pct"))
            if value is not None: by_name[str(row.get(dimension) or "Ukjent")].append(value)
        for name, values in by_name.items(): dimension_rows.append({"dimension": dimension, "name": name, **_stats(values)})
    missing = [row for row in active if str((row.get("source_health") or {}).get("status") or "PENDING") != "OK"]
    proposals = []
    moderate = next((row for row in group_rows if row["group"] == "MODERATE" and row["horizon_days"] == 20), {})
    near = next((row for row in group_rows if row["group"] == "NEAR_THRESHOLD" and row["horizon_days"] == 20), {})
    if int(moderate.get("count") or 0) >= 10 and int(near.get("count") or 0) >= 10:
        difference = (_number(moderate.get("average"), 0) or 0) - (_number(near.get("average"), 0) or 0)
        proposals.append({"proposal": "Test moderat terskel mot nær-terskel i Challenger",
                          "evidence": f"20d forskjell i gjennomsnittlig meravkastning: {difference:+.2f} prosentpoeng",
                          "status": "PROPOSED_SHADOW", "approval_required": True, "production_applied": False,
                          "uncertainty": _maturity(min(int(moderate["count"]), int(near["count"])))})
    if not proposals:
        proposals.append({"proposal": "Fortsett datainnsamling uten parameterendring",
                          "evidence": "For få sammenlignbare modne observasjoner til et forsvarlig Challenger-forslag.",
                          "status": "OBSERVE", "approval_required": True, "production_applied": False,
                          "uncertainty": "FOR_TIDLIG"})
    return {"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION, "generated_at": _now_iso(now),
            "cohort": APP_VERSION, "observation_count": len(observations), "active_count": len(active),
            "matured_count": sum(str(row.get("status") or "").upper() == "MATURED" for row in observations),
            "group_counts": {group: sum(str(row.get("group") or "") == group for row in observations) for group in GROUP_TARGETS},
            "horizons": horizon_rows, "groups": group_rows,
            "dimensions_20d": sorted(dimension_rows, key=lambda row: (row["dimension"], -(row.get("average") or -9999))),
            "health": {"status": "OK" if not missing else "DEGRADED", "missing_or_stale": len(missing),
                       "missing_tickers": [str(row.get("ticker") or "") for row in missing[:30]],
                       "all_measurements_accounted": not missing,
                       "benchmark_mapping_complete": all(str(row.get("benchmark_ticker") or "") in set(BENCHMARKS.values()) for row in observations),
                       "production_mutations": 0},
            "shadow_proposals": proposals, "strategy_readiness": "NOT_VALIDATED",
            "production_parameters_changed": False,
            "note": "Foreløpige trender er beskrivende. Ingen regel eller vekt endres automatisk."}


def _register_pdf_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    regular, bold = "LearningSans", "LearningSans-Bold"
    if regular not in pdfmetrics.getRegisteredFontNames():
        root = Path(__file__).resolve().parent / "assets" / "fonts"
        pdfmetrics.registerFont(TTFont(regular, str(root / "NotoSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(bold, str(root / "NotoSans-Bold.ttf")))
    return regular, bold


def build_weekly_pdf(analysis: Mapping[str, Any], *, technical: bool = False) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    regular, bold = _register_pdf_fonts(); buffer = BytesIO(); pagesize = landscape(A4) if technical else A4
    doc = SimpleDocTemplate(buffer, pagesize=pagesize, rightMargin=14*mm, leftMargin=14*mm, topMargin=13*mm, bottomMargin=13*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("LearningTitle", parent=styles["Title"], fontName=bold, fontSize=19, leading=23,
                           textColor=colors.HexColor("#0f766e"), alignment=TA_CENTER)
    heading = ParagraphStyle("LearningHeading", parent=styles["Heading2"], fontName=bold, fontSize=12, leading=15,
                             textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("LearningBody", parent=styles["BodyText"], fontName=regular, fontSize=8.5, leading=11)
    small = ParagraphStyle("LearningSmall", parent=body, fontSize=7, leading=9)
    story = [Paragraph("Ukentlig foreløpig læringsrapport", title), Spacer(1, 4*mm),
             Paragraph(f"Kohort {analysis.get('cohort')} | Observasjoner {analysis.get('observation_count')} | Aktive {analysis.get('active_count')} | Modne {analysis.get('matured_count')} | Strategistatus {analysis.get('strategy_readiness')}", body),
             Paragraph("Ingen produksjonsregel, vekt eller handelsfullmakt er endret.", body),
             Paragraph("Målepunkter", heading)]
    horizon_data = [["Dager", "Antall", "Gj.snitt", "Median", "Treff", "Meravkastning", "Modenhet"]]
    for row in analysis.get("horizons") or []:
        ret, excess = row.get("return") or {}, row.get("excess_return") or {}
        horizon_data.append([row.get("horizon_days"), ret.get("count"), "-" if ret.get("average") is None else f"{ret['average']:+.2f}%",
                             "-" if ret.get("median") is None else f"{ret['median']:+.2f}%",
                             "-" if ret.get("hit_rate_pct") is None else f"{ret['hit_rate_pct']:.1f}%",
                             "-" if excess.get("average") is None else f"{excess['average']:+.2f}%", excess.get("maturity") or "FOR_TIDLIG"])
    table = Table(horizon_data, repeatRows=1, colWidths=[14*mm,16*mm,22*mm,22*mm,18*mm,28*mm,31*mm])
    table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,0),bold),("FONTNAME",(0,1),(-1,-1),regular),("FONTSIZE",(0,0),(-1,-1),7.5),
                               ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#ccfbf1")),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#94a3b8")),
                               ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.extend([table, Paragraph("Foreløpige grupper", heading)])
    group_data = [["Gruppe", "Horisont", "Antall", "Gj.snitt meravkastning", "Treff", "Modenhet"]]
    for row in analysis.get("groups") or []:
        group_data.append([row.get("group"),row.get("horizon_days"),row.get("count"),
                           "-" if row.get("average") is None else f"{row['average']:+.2f}%",
                           "-" if row.get("hit_rate_pct") is None else f"{row['hit_rate_pct']:.1f}%",row.get("maturity")])
    groups = Table(group_data, repeatRows=1)
    groups.setStyle(TableStyle([("FONTNAME",(0,0),(-1,0),bold),("FONTNAME",(0,1),(-1,-1),regular),("FONTSIZE",(0,0),(-1,-1),7),
                                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e2e8f0")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#94a3b8"))]))
    story.extend([groups, Paragraph("Shadow-forslag", heading)])
    for proposal in analysis.get("shadow_proposals") or []:
        story.append(Paragraph(f"<b>{proposal.get('status')}</b>: {proposal.get('proposal')}<br/>{proposal.get('evidence')} Usikkerhet: {proposal.get('uncertainty')}. Manuell godkjenning kreves.", body))
    if technical: story.append(PageBreak())
    health = analysis.get("health") or {}
    story.extend([Paragraph("Helsekontroll", heading), Paragraph(f"Status {health.get('status')} | Manglende/foreldede {health.get('missing_or_stale')} | Benchmark komplett {health.get('benchmark_mapping_complete')} | Produksjonsmutasjoner {health.get('production_mutations')}", body)])
    if technical:
        story.append(Paragraph("Teknisk trendgrunnlag", title))
        dim_data = [["Dimensjon","Navn","Antall","Gj.snitt 20d meravkastning","Median","Treff","Modenhet"]]
        for row in analysis.get("dimensions_20d") or []:
            dim_data.append([row.get("dimension"),row.get("name"),row.get("count"),
                             "-" if row.get("average") is None else f"{row['average']:+.2f}%",
                             "-" if row.get("median") is None else f"{row['median']:+.2f}%",
                             "-" if row.get("hit_rate_pct") is None else f"{row['hit_rate_pct']:.1f}%",row.get("maturity")])
        dimensions = Table(dim_data, repeatRows=1, colWidths=[24*mm,52*mm,16*mm,38*mm,22*mm,18*mm,34*mm])
        dimensions.setStyle(TableStyle([("FONTNAME",(0,0),(-1,0),bold),("FONTNAME",(0,1),(-1,-1),regular),("FONTSIZE",(0,0),(-1,-1),6.5),
                                         ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#ccfbf1")),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#94a3b8"))]))
        story.extend([dimensions, Spacer(1,4*mm), Paragraph(json.dumps(dict(health),ensure_ascii=False,separators=(",",":")),small)])
    def footer(canvas, document):
        canvas.saveState(); canvas.setFont(regular,7); canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(14*mm,7*mm,f"{APP_VERSION} - teoretisk læring - ingen automatisk produksjonsendring")
        canvas.drawRightString(pagesize[0]-14*mm,7*mm,f"Side {document.page}"); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()


def load_weekly_reports(limit: int = 52) -> list[dict[str, Any]]:
    value = read_json(WEEKLY_KEY, WEEKLY_PATH, [])
    rows = [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []
    return rows[:max(0, int(limit))]


def generate_weekly_report(*, now: datetime | None = None, notify: bool = True) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(OSLO); week_key = current.strftime("%G-W%V")
    previous = load_weekly_reports()
    existing = next((row for row in previous if str(row.get("week_key") or "") == week_key), None)
    if existing: return {"status":"ALREADY_COMPLETED","week_key":week_key,"report_id":existing.get("report_id")}
    analysis = build_weekly_analysis(now=now); main_pdf = build_weekly_pdf(analysis); technical_pdf = build_weekly_pdf(analysis,technical=True)
    report_id = f"LWR-{week_key}-{current.strftime('%Y%m%d%H%M%S')}"
    record: dict[str, Any] = {"schema_version":SCHEMA_VERSION,"report_id":report_id,"run_id":report_id,
        "week_key":week_key,"created_at":_now_iso(now),"analysis":analysis,
        "public_pdf_name":f"Ukentlig_laeringsrapport_{week_key}.pdf",
        "technical_pdf_name":f"Ukentlig_laeringsrapport_{week_key}_technical.pdf",
        "notification":{"attempted":False,"sent":False}}
    from public_report_store import publish_durable_pdf
    publish_durable_pdf(record,main_pdf)
    publish_durable_pdf(record,technical_pdf,token_field="technical_report_token",filename_field="technical_pdf_name",document_kind="learning_technical")
    if notify:
        try:
            from notifier import send_pushover_alert
            from report_delivery import public_report_url
            first=(analysis.get("horizons") or [{}])[0]; count=((first.get("excess_return") or {}).get("count") or 0)
            ok,detail=send_pushover_alert(
                f"Observasjoner: {analysis.get('observation_count')} | modne: {analysis.get('matured_count')}\n"
                f"1d benchmarkmålinger: {count} | helse: {(analysis.get('health') or {}).get('status')}\n"
                "Foreløpige trender endrer ingen produksjonsregel.",title="Ukentlig læringsrapport",
                url=public_report_url(record) or None,url_title="Åpne læringsrapport")
            record["notification"]={"attempted":True,"sent":bool(ok),"detail":str(detail or "")[:500]}
        except Exception as exc:
            record["notification"]={"attempted":True,"sent":False,"detail":f"{type(exc).__name__}: {str(exc)[:420]}"}
    record["pdf_sizes"]={"main":len(main_pdf),"technical":len(technical_pdf)}
    record["public_json_name"]=f"Ukentlig_laeringsrapport_{week_key}.json"
    payload=json.dumps(record,ensure_ascii=False,separators=(",",":"),default=str).encode("utf-8")
    from public_report_store import publish_durable_file
    record["public_json_token"]=publish_durable_file(payload,filename=record["public_json_name"],mime="application/json",report_id=report_id)
    write_json(WEEKLY_KEY,WEEKLY_PATH,[record]+previous[:51])
    state=load_engine_state(); state["weekly"]={"status":"COMPLETED","week_key":week_key,"report_id":report_id,"completed_at":_now_iso(now)}
    write_json(STATE_KEY,STATE_PATH,state)
    return {"status":"COMPLETED","week_key":week_key,"report_id":report_id,"notification":record["notification"],"pdf_sizes":record["pdf_sizes"]}


def _daily_due(now: datetime) -> bool:
    local=now.astimezone(OSLO)
    if local.weekday()>=5 or (local.hour,local.minute)<(6,30): return False
    daily=dict(load_engine_state().get("daily") or {}); completed=str(daily.get("completed_at") or "")
    if completed[:10]!=now.astimezone(timezone.utc).date().isoformat(): return True
    status=str(daily.get("status") or "").upper(); retry_minutes=60 if status=="FAILED" else 360 if status=="DEGRADED" else 0
    if not retry_minutes: return False
    try:
        last=datetime.fromisoformat(completed.replace("Z","+00:00")).astimezone(timezone.utc)
        return (now.astimezone(timezone.utc)-last).total_seconds()>=retry_minutes*60
    except Exception: return True


def _weekly_due(now: datetime) -> bool:
    local=now.astimezone(OSLO)
    if not ((local.weekday()==4 and (local.hour,local.minute)>=(23,10)) or local.weekday() in {5,6}): return False
    return not any(str(row.get("week_key") or "")==local.strftime("%G-W%V") for row in load_weekly_reports())


def run_learning_maintenance(*,now:datetime|None=None,series_loader:SeriesLoader|None=None)->dict[str,Any]:
    current=now or datetime.now(timezone.utc)
    result={"status":"COMPLETED","daily":{"status":"NOT_DUE"},"weekly":{"status":"NOT_DUE"},"production_changed":False}
    if _daily_due(current): result["daily"]=evaluate_observations(series_loader,now=current)
    if _weekly_due(current):
        result["weekly_refresh"]=evaluate_observations(series_loader,now=current)
        result["weekly"]=generate_weekly_report(now=current)
    if result["daily"].get("status")=="FAILED" or result["weekly"].get("status")=="FAILED": result["status"]="DEGRADED"
    return result


def diagnostics()->dict[str,Any]:
    rows=load_observations(); state=load_engine_state(); reports=load_weekly_reports(3)
    return {"schema_version":SCHEMA_VERSION,"engine_version":ENGINE_VERSION,
        "active":sum(str(row.get("status") or "ACTIVE").upper()=="ACTIVE" for row in rows),
        "matured":sum(str(row.get("status") or "").upper()=="MATURED" for row in rows),
        "groups":{group:sum(str(row.get("group") or "")==group for row in rows) for group in GROUP_TARGETS},
        "latest_daily":dict(state.get("daily") or {}),"latest_weekly":dict(state.get("weekly") or {}),
        "recent_weekly_reports":[{key:row.get(key) for key in ("report_id","week_key","created_at","notification")} for row in reports],
        "production_parameters_changed":False}


def render_weekly_learning_reports()->None:
    import streamlit as st
    from mobile_file_delivery import render_mobile_file_delivery
    from public_report_store import load_public_pdf
    from report_delivery import public_report_url
    st.markdown("##### Ukentlig kontrollert observasjonslæring")
    reports=load_weekly_reports(12)
    if not reports:
        st.info("Ingen ukentlig læringsrapport er produsert ennå. Første rapport opprettes etter fredagens sluttkurser."); return
    latest=reports[0]; analysis=latest.get("analysis") if isinstance(latest.get("analysis"),Mapping) else {}; health=analysis.get("health") or {}
    a,b,c,d=st.columns(4); a.metric("Observasjoner",int(analysis.get("observation_count") or 0)); b.metric("Aktive",int(analysis.get("active_count") or 0)); c.metric("Modne",int(analysis.get("matured_count") or 0)); d.metric("Helse",str(health.get("status") or "UKJENT"))
    st.caption("Foreløpige trender er dokumentasjon og Shadow-grunnlag. De endrer aldri produksjonsstrategien automatisk.")
    main=load_public_pdf(str(latest.get("public_report_token") or "")); technical=load_public_pdf(str(latest.get("technical_report_token") or ""))
    if main:
        url=public_report_url(latest) or f"/?public_report_token={latest.get('public_report_token')}"
        render_mobile_file_delivery(st,url=url,filename=str(main.get("filename") or "ukentlig_laeringsrapport.pdf"),label="Åpne ukentlig læringsrapport",mime="application/pdf",data=bytes(main["data"]),key=f"weekly_main_{latest.get('report_id')}")
    if technical:
        with st.expander("Teknisk læringsrapport",expanded=False):
            trun={**latest,"public_report_token":latest.get("technical_report_token")}; url=public_report_url(trun) or f"/?public_report_token={latest.get('technical_report_token')}"
            render_mobile_file_delivery(st,url=url,filename=str(technical.get("filename") or "ukentlig_laeringsrapport_technical.pdf"),label="Åpne teknisk læringsrapport",mime="application/pdf",data=bytes(technical["data"]),key=f"weekly_tech_{latest.get('report_id')}")
    token=str(latest.get("public_json_token") or "")
    if token:
        from urllib.parse import urlencode
        base=str(os.getenv("RENDER_EXTERNAL_URL") or os.getenv("REPORT_PUBLIC_BASE_URL") or "").rstrip("/")
        url=f"{base}/?{urlencode({'public_file_token':token})}" if base else f"/?{urlencode({'public_file_token':token})}"
        payload=json.dumps(latest,ensure_ascii=False,separators=(",",":"),default=str).encode("utf-8")
        render_mobile_file_delivery(st,url=url,filename=str(latest.get("public_json_name") or "ukentlig_laeringsrapport.json"),label="Åpne læringsrapport JSON",mime="application/json",data=payload,key=f"weekly_json_{latest.get('report_id')}")


__all__=["BENCHMARKS","GROUP_TARGETS","HORIZONS","MAX_ACTIVE_OBSERVATIONS","build_weekly_analysis","build_weekly_pdf","diagnostics","evaluate_observations","generate_weekly_report","load_observations","register_report_observations","render_weekly_learning_reports","run_learning_maintenance","yfinance_series_loader"]
