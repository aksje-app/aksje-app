"""Evidence passports, confidence separation and immutable report revisions."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


CRITICAL_STATES = {
    "PARTIAL_SOURCE_FAILURE", "NOT_CONFIGURED", "RATE_LIMITED",
    "DAILY_QUOTA_EXCEEDED", "SOURCE_ERROR", "NOT_SEARCHED", "STALE", "ERROR",
}
STATUS_QUALITY = {
    "VERIFIED_FACTS_FOUND": 100.0,
    "AVAILABLE": 100.0,
    "SUCCESS_WITH_RESULTS": 95.0,
    "CHECKED_NO_EVENTS": 82.0,
    "SUCCESS_NO_RESULTS": 82.0,
    "DISCOVERY_ONLY": 55.0,
    "PARTIAL_SOURCE_FAILURE": 48.0,
    "STALE": 38.0,
    "NOT_CONFIGURED": 30.0,
    "RATE_LIMITED": 24.0,
    "DAILY_QUOTA_EXCEEDED": 20.0,
    "SOURCE_ERROR": 18.0,
    "ERROR": 18.0,
    "NOT_SEARCHED": 0.0,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_payload(candidate: Mapping[str, Any], key: str) -> dict[str, Any]:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    value = raw.get(key) if isinstance(raw.get(key), Mapping) else {}
    return dict(value)


def _coverage(candidate: Mapping[str, Any], area: str, payload: Mapping[str, Any]) -> str:
    records = candidate.get("evidence_coverage") if isinstance(candidate.get("evidence_coverage"), Mapping) else {}
    record = records.get(area) if isinstance(records.get(area), Mapping) else {}
    return str(record.get("status") or payload.get("canonical_evidence_status") or payload.get("coverage") or "NOT_SEARCHED").upper()


def _fact_rows(payload: Mapping[str, Any], area: str) -> list[dict[str, Any]]:
    source_rows = payload.get("evidence") if area == "insider" else payload.get("events")
    facts: list[dict[str, Any]] = []
    for row in source_rows or []:
        if not isinstance(row, Mapping):
            continue
        facts.append({
            "fact_id": row.get("fact_id") or row.get("document_id") or "",
            "title": row.get("title") or row.get("insider") or row.get("subject") or "",
            "source": row.get("source") or row.get("publisher") or payload.get("source") or "",
            "source_url": row.get("source_url") or row.get("url") or "",
            "published_at": row.get("published_at") or row.get("date") or "",
            "retrieved_at": row.get("retrieved_at") or payload.get("fetched_at") or "",
            "verification": row.get("verification") or "UKJENT",
            "age_hours": row.get("age_hours"),
        })
    return facts


def build_evidence_passport(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return exact sources, timestamps, facts and ranking influence."""
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    formula = raw.get("score_formula") if isinstance(raw.get("score_formula"), Mapping) else {}
    contributions = formula.get("weighted_contributions") if isinstance(formula.get("weighted_contributions"), Mapping) else {}
    areas: dict[str, Any] = {}
    for area, key in (("insider", "insider_intelligence"), ("news", "news_intelligence")):
        payload = _candidate_payload(candidate, key)
        status = _coverage(candidate, area, payload)
        facts = _fact_rows(payload, area)
        source_attempts = []
        for item in payload.get("search_log") or []:
            if not isinstance(item, Mapping):
                continue
            source_attempts.append({
                "source": item.get("source") or item.get("source_type") or "Ukjent",
                "source_type": item.get("source_type") or "",
                "attempted": bool(item.get("attempted")),
                "status": str(item.get("status") or "NOT_SEARCHED").upper(),
                "results": int(item.get("results") or 0),
                "checked_at": item.get("checked_at") or item.get("retrieved_at") or "",
                "url": item.get("url") or "",
                "error": str(item.get("error") or item.get("reason") or "")[:240],
                "direct_primary": str(item.get("source_type") or "").upper() in {
                    "PRIMARY_STRUCTURED", "PRIMARY_REGULATORY",
                    "PRIMARY_OR_DIRECT_RSS", "OFFICIAL_PRIMARY",
                },
            })
        contribution = contributions.get(area)
        areas[area] = {
            "status": status,
            "quality_score": STATUS_QUALITY.get(status, 15.0),
            "facts": facts,
            "fact_count": len(facts),
            "sources": source_attempts,
            "source_count": len(source_attempts),
            "fetched_at": payload.get("fetched_at") or "",
            "ranking_contribution": contribution,
            "affected_ranking": bool(contribution not in (None, 0, 0.0)),
        }
    fingerprint = hashlib.sha256(
        json.dumps(areas, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return {
        "version": "v19.0.11",
        "ticker": candidate.get("ticker") or "",
        "generated_at": _now_iso(),
        "areas": areas,
        "fingerprint": fingerprint,
    }


def build_confidence_profile(candidate: Mapping[str, Any]) -> dict[str, Any]:
    passport = candidate.get("evidence_passport") if isinstance(candidate.get("evidence_passport"), Mapping) else build_evidence_passport(candidate)
    areas = passport.get("areas") if isinstance(passport.get("areas"), Mapping) else {}
    insider_quality = _f((areas.get("insider") or {}).get("quality_score"), 0.0)
    news_quality = _f((areas.get("news") or {}).get("quality_score"), 0.0)
    contract = candidate.get("data_contract") if isinstance(candidate.get("data_contract"), Mapping) else {}
    validity = str(contract.get("validity") or contract.get("status") or "").upper()
    market_quality = 100.0 if candidate.get("valid_for_decision") or validity in {"VALID", "GYLDIG"} else 35.0
    data_coverage = round(market_quality * 0.45 + news_quality * 0.30 + insider_quality * 0.25, 2)
    model_confidence = _f(
        candidate.get("confidence_before_evidence_policy"),
        _f(candidate.get("confidence_before_data_contract"), _f(candidate.get("confidence_score"), 0.0)),
    )
    calibrated = _f(candidate.get("confidence_score"), model_confidence)
    decision_confidence = round(min(calibrated, model_confidence * 0.55 + data_coverage * 0.45), 2)
    return {
        "model_confidence": round(model_confidence, 2),
        "data_coverage": data_coverage,
        "calibrated_confidence": round(calibrated, 2),
        "decision_confidence": decision_confidence,
        "mode": "REPORT_ONLY",
        "changes_trading_rules": False,
        "explanation": "Beslutningskonfidens kombinerer modellens sikkerhet med dokumentert datadekning uten å endre produksjonsterskler.",
    }


def build_source_health(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        passport = candidate.get("evidence_passport") if isinstance(candidate.get("evidence_passport"), Mapping) else build_evidence_passport(candidate)
        for area, payload in (passport.get("areas") or {}).items():
            for row in payload.get("sources") or []:
                source = str(row.get("source") or "Ukjent")
                item = sources.setdefault(source, {
                    "source": source, "areas": set(), "attempts": 0, "successes": 0,
                    "with_results": 0, "rate_limited": 0, "quota_exceeded": 0,
                    "errors": 0, "last_status": "NOT_SEARCHED", "last_checked_at": "",
                })
                item["areas"].add(area)
                if row.get("attempted"):
                    item["attempts"] += 1
                status = str(row.get("status") or "").upper()
                if status in {"SUCCESS_WITH_RESULTS", "SUCCESS_NO_RESULTS"}:
                    item["successes"] += 1
                if status == "SUCCESS_WITH_RESULTS":
                    item["with_results"] += 1
                if status == "RATE_LIMITED":
                    item["rate_limited"] += 1
                if status == "DAILY_QUOTA_EXCEEDED":
                    item["quota_exceeded"] += 1
                if status in {"ERROR", "SOURCE_ERROR", "PARTIAL_SOURCE_FAILURE"}:
                    item["errors"] += 1
                checked = str(row.get("checked_at") or "")
                if checked >= str(item.get("last_checked_at") or ""):
                    item["last_checked_at"] = checked
                    item["last_status"] = status or "NOT_SEARCHED"
    rows = []
    for item in sources.values():
        clean = dict(item)
        clean["areas"] = sorted(clean["areas"])
        attempts = int(clean.get("attempts") or 0)
        clean["success_rate_pct"] = round(int(clean.get("successes") or 0) * 100.0 / attempts, 1) if attempts else 0.0
        rows.append(clean)
    try:
        from newsapi_budget import health_snapshot
        newsapi = health_snapshot()
    except Exception as exc:
        newsapi = {"source": "NewsAPI", "configured": False, "last_status": "HEALTH_ERROR", "error": str(exc)[:160]}
    operational_rows: list[dict[str, Any]] = []
    try:
        from news_source_registry import SOURCE_REGISTRY
        from operational_telemetry import source_health_snapshot as operational_source_health_snapshot
        for source in operational_source_health_snapshot(SOURCE_REGISTRY):
            operational_rows.append({
                "source": source.get("publisher") or source.get("source_id") or "Ukjent",
                "source_id": source.get("source_id") or source.get("id"),
                "market": source.get("market") or "",
                "source_role": source.get("source_role") or "",
                "attempts": 1 if source.get("last_attempt_at") else 0,
                "successes": 1 if source.get("last_success_at") else 0,
                "with_results": 1 if int(source.get("article_count") or 0) > 0 else 0,
                "rate_limited": 0,
                "quota_exceeded": 0,
                "errors": int(source.get("consecutive_failures") or 0),
                "last_status": "ALERT" if source.get("alert") else ("OK" if source.get("last_success_at") else "NOT_TESTED"),
                "last_checked_at": source.get("last_attempt_at") or "",
                "last_success_at": source.get("last_success_at") or "",
                "last_response_ms": source.get("last_response_ms"),
                "fallback_used": bool(source.get("fallback_used")),
                "parser_status": source.get("parser_status") or "",
                "article_count": int(source.get("article_count") or 0),
                "relevant_count": int(source.get("relevant_count") or 0),
                "duplicate_count": int(source.get("duplicate_count") or 0),
                "filtered_commercial_count": int(source.get("filtered_commercial_count") or 0),
                "health_score": int(source.get("health_score") or 0),
                "volume_anomaly": bool(source.get("volume_anomaly")),
                "error_code": source.get("error_code") or "",
                "last_error": source.get("last_error") or "",
                "operational_health": True,
                "areas": ["news"],
                "success_rate_pct": 100.0 if source.get("last_success_at") and not source.get("consecutive_failures") else 0.0,
            })
    except Exception:
        operational_rows = []
    merged: dict[str, dict[str, Any]] = {str(row.get("source") or "").casefold(): dict(row) for row in rows}
    for row in operational_rows:
        key = str(row.get("source") or "").casefold()
        if key in merged:
            merged[key].update({k: v for k, v in row.items() if k not in {"areas", "attempts", "successes", "with_results", "errors"}})
        else:
            merged[key] = row
    final_rows = sorted(merged.values(), key=lambda row: (str(row.get("source") or "").casefold()))
    return {
        "generated_at": _now_iso(),
        "sources": final_rows,
        "newsapi_budget": newsapi,
        "degraded_sources": sum(
            1 for row in final_rows
            if row.get("rate_limited") or row.get("quota_exceeded") or row.get("errors") or row.get("volume_anomaly") or row.get("last_status") == "ALERT"
        ),
    }


def build_integrity_preflight(job: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, detail: str, blocking: bool = False) -> None:
        checks.append({"name": name, "status": status, "detail": detail, "blocking": bool(blocking)})

    markets = list(getattr(job, "markets", []) or [])
    add("Markeder", "PASS" if markets else "BLOCK", ", ".join(markets) if markets else "Ingen markeder valgt", not markets)
    modules = list(getattr(job, "modules", []) or [])
    add("Pipeline-moduler", "PASS" if modules else "BLOCK", f"{len(modules)} moduler valgt", not modules)
    if bool(getattr(job, "save_pdf", True)):
        try:
            import reportlab  # noqa: F401
            add("PDF-motor", "PASS", "ReportLab tilgjengelig")
        except Exception:
            add("PDF-motor", "BLOCK", "ReportLab mangler", True)
    try:
        from newsapi_budget import health_snapshot
        budget = health_snapshot()
        if not budget.get("configured"):
            add("NewsAPI", "WARN", "Ikke konfigurert; direkte og åpne kilder brukes")
        elif int(budget.get("remaining_today") or 0) <= 0:
            add("NewsAPI", "WARN", "Døgnbudsjett brukt; direkte og åpne kilder brukes")
        else:
            add("NewsAPI", "PASS", f"{budget.get('remaining_today')} av {budget.get('daily_budget')} lokale kall gjenstår")
    except Exception as exc:
        add("NewsAPI", "WARN", f"Kvotehelse kunne ikke leses: {str(exc)[:120]}")
    sec_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if "USA" in markets or "Alle" in markets:
        add("SEC-identitet", "PASS" if "@" in sec_agent else "WARN",
            "Kontaktidentitet konfigurert" if "@" in sec_agent else "SEC_USER_AGENT bør inneholde kontakt-e-post")
    database = bool(os.getenv("DATABASE_URL", "").strip())
    add("Varig database", "PASS" if database else "WARN", "DATABASE_URL konfigurert" if database else "Lokal lagring/fallback")
    blockers = [row for row in checks if row["blocking"]]
    warnings = [row for row in checks if row["status"] == "WARN"]
    return {
        "checked_at": _now_iso(),
        "status": "BLOCKED" if blockers else ("WARNING" if warnings else "PASS"),
        "checks": checks,
        "blockers": len(blockers),
        "warnings": len(warnings),
        "can_run": not blockers,
    }


def _same_series(current: Mapping[str, Any], previous: Mapping[str, Any]) -> bool:
    if not previous:
        return False
    current_identity = current.get("report_identity") if isinstance(current.get("report_identity"), Mapping) else {}
    previous_identity = previous.get("report_identity") if isinstance(previous.get("report_identity"), Mapping) else {}
    return bool(
        str(current.get("job_id") or "") == str(previous.get("job_id") or "")
        and str(current_identity.get("type") or "") == str(previous_identity.get("type") or "")
        and (
            str(current.get("trigger") or "").upper() == "REVALIDATION"
            or str(current.get("created_at") or "")[:10] == str(previous.get("created_at") or "")[:10]
        )
    )


def _revision(current: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    previous = previous or {}
    previous_revision = previous.get("report_revision") if isinstance(previous.get("report_revision"), Mapping) else {}
    same = _same_series(current, previous)
    identity = current.get("report_identity") if isinstance(current.get("report_identity"), Mapping) else {}
    seed = f"{current.get('job_id')}|{identity.get('type')}|{str(current.get('created_at') or '')[:10]}"
    series_id = str(previous_revision.get("series_id") or "") if same else ""
    if not series_id:
        series_id = "SERIES-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()
    number = int(previous_revision.get("revision") or 0) + 1 if same else 1
    return {
        "series_id": series_id,
        "revision": number,
        "revision_label": f"R{number}",
        "supersedes_run_id": previous.get("run_id") if same else "",
        "immutable_original": True,
        "created_at": current.get("created_at") or _now_iso(),
    }


def _change_summary(run: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    changes = run.get("changes") if isinstance(run.get("changes"), Mapping) else {}
    previous = previous or {}
    previous_top = [str(row.get("ticker") or "") for row in previous.get("raw_top3") or previous.get("candidates", [])[:3]]
    current_top = [str(row.get("ticker") or "") for row in run.get("raw_top3") or run.get("candidates", [])[:3]]
    current_sources = (run.get("source_health") or {}).get("degraded_sources", 0)
    previous_sources = (previous.get("source_health") or {}).get("degraded_sources", 0)
    return {
        "new_candidates": len(changes.get("new") or []),
        "improved_candidates": len(changes.get("improved") or []),
        "weakened_candidates": len(changes.get("weakened") or []),
        "dropped_candidates": len(changes.get("dropped") or []),
        "top3_changed": current_top != previous_top if previous else False,
        "previous_top3": previous_top,
        "current_top3": current_top,
        "degraded_source_delta": int(current_sources or 0) - int(previous_sources or 0),
        "material_change": bool(
            (previous and current_top != previous_top)
            or changes.get("new") or changes.get("improved") or changes.get("weakened")
            or int(current_sources or 0) != int(previous_sources or 0)
        ),
    }


def finalize_run_integrity(run: dict[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Attach report-only integrity metadata before canonical persistence."""
    candidates = [row for row in run.get("candidates") or [] if isinstance(row, dict)]
    for candidate in candidates:
        candidate["evidence_passport"] = build_evidence_passport(candidate)
        candidate["confidence_profile"] = build_confidence_profile(candidate)
    by_ticker = {str(row.get("ticker") or ""): row for row in candidates}
    for key in ("raw_top3", "decision_ready_top3", "diverse_top3"):
        if isinstance(run.get(key), list):
            run[key] = [
                by_ticker.get(str(row.get("ticker") or ""), dict(row))
                for row in run.get(key) or [] if isinstance(row, Mapping)
            ]
    run["source_health"] = build_source_health(candidates)
    critical = []
    top = list(run.get("raw_top3") or candidates[:3])
    for candidate in top:
        passport = candidate.get("evidence_passport") if isinstance(candidate.get("evidence_passport"), Mapping) else {}
        for area, payload in (passport.get("areas") or {}).items():
            status = str(payload.get("status") or "NOT_SEARCHED").upper()
            if status in CRITICAL_STATES:
                critical.append({"ticker": candidate.get("ticker"), "area": area, "status": status})
                continue
            direct_primary = any(bool(row.get("direct_primary")) for row in payload.get("sources") or [])
            if area == "insider" and not payload.get("fact_count") and not direct_primary:
                critical.append({
                    "ticker": candidate.get("ticker"),
                    "area": area,
                    "status": "PRIMARY_SOURCE_NOT_CHECKED",
                })
    preflight = run.get("integrity_preflight") if isinstance(run.get("integrity_preflight"), Mapping) else {}
    provisional = bool(critical or int(preflight.get("blockers") or 0) or run.get("analysis_aborted"))
    run["report_status"] = {
        "state": "PROVISIONAL" if provisional else "FINAL",
        "label": "FORELØPIG – KILDEKONTROLL UFULLSTENDIG" if provisional else "ENDELIG",
        "critical_gaps": critical,
        "revalidation_required": provisional,
        "revalidation_after_hours": max(1, int(os.getenv("REPORT_REVALIDATION_HOURS", "6") or 6)),
    }
    run["report_revision"] = _revision(run, previous)
    run["change_since_previous"] = _change_summary(run, previous)
    fingerprint_payload = {
        "run_id": run.get("run_id"),
        "revision": run["report_revision"],
        "status": run["report_status"],
        "top": [{
            "ticker": row.get("ticker"),
            "score": row.get("investment_score"),
            "confidence": row.get("confidence_profile"),
            "passport": (row.get("evidence_passport") or {}).get("fingerprint"),
        } for row in top],
    }
    run["report_revision"]["content_sha256"] = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return run


__all__ = [
    "build_confidence_profile",
    "build_evidence_passport",
    "build_integrity_preflight",
    "build_source_health",
    "finalize_run_integrity",
]
