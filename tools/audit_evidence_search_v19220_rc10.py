#!/usr/bin/env python3
"""Detailed evidence-search audit for report JSONs and historical Autonomy trades.

The tool does not generate reports and does not change production parameters.
It normalizes source-search outcomes, counts unique source-area gaps, validates
budget counters against the actual log, and uses autonomous_trades as a
historical reference for previously functioning BUY decisions.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import statistics
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence_search_status import (  # noqa: E402
    CANONICAL_SEARCH_STATUSES,
    NOT_APPLICABLE,
    NOT_SEARCHED_BUDGET,
    NOT_SEARCHED_DISABLED,
    NOT_SEARCHED_POLICY,
    NOT_SEARCHED_UNSUPPORTED,
    SEARCHED_NO_RESULTS,
    SEARCHED_RESULTS_FOUND,
    SEARCH_FAILED,
    normalize_evidence_payload,
)

SCHEMA = "evidence-search-audit-v19.22.0-rc10"
MISSING_SEARCH_STATUSES = {
    NOT_SEARCHED_BUDGET,
    NOT_SEARCHED_DISABLED,
    NOT_SEARCHED_UNSUPPORTED,
    NOT_SEARCHED_POLICY,
}


def _json_values(path: Path) -> Iterable[tuple[str, Any]]:
    if path.is_dir():
        for child in sorted(path.rglob("*.json")):
            yield from _json_values(child)
        return
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith(".json"):
                    continue
                try:
                    value = json.loads(archive.read(name).decode("utf-8"))
                except Exception:
                    continue
                yield f"{path.name}:{name}", value
        return
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        yield str(path), value


def _report_documents(paths: Sequence[Path]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    seen: set[str] = set()
    for path in paths:
        for source, value in _json_values(path):
            if not isinstance(value, Mapping):
                continue
            if not (value.get("candidates") or value.get("decision_funnel") or value.get("run_id")):
                continue
            run_id = str(value.get("run_id") or source)
            if run_id in seen:
                continue
            seen.add(run_id)
            yield source, value


def _candidate_rows(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = [row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    if rows:
        return rows
    funnel = run.get("decision_funnel") if isinstance(run.get("decision_funnel"), Mapping) else {}
    return [row for row in (funnel.get("candidates") or []) if isinstance(row, Mapping)]


def _raw_candidate(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = candidate.get("raw")
    return raw if isinstance(raw, Mapping) else candidate


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _budget_expected(log: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    statuses = Counter(str(row.get("search_status") or "") for row in log)
    return {
        "planned": len(log),
        "attempted": sum(bool(row.get("attempted")) for row in log),
        "successful": statuses[SEARCHED_RESULTS_FOUND] + statuses[SEARCHED_NO_RESULTS],
        "with_facts": statuses[SEARCHED_RESULTS_FOUND],
        "no_events": statuses[SEARCHED_NO_RESULTS],
        "failed": statuses[SEARCH_FAILED],
        "not_searched": sum(statuses[s] for s in MISSING_SEARCH_STATUSES),
        "not_applicable": statuses[NOT_APPLICABLE],
        "unknown_reason": sum(str(row.get("reason_code") or "") == "UNKNOWN_REASON" for row in log),
    }


def _budget_issues(stored: Mapping[str, Any], expected: Mapping[str, int]) -> list[str]:
    issues: list[str] = []
    aliases = {"failed": "errors"}
    for key, expected_value in expected.items():
        stored_value = stored.get(key)
        if stored_value is None and key in aliases:
            stored_value = stored.get(aliases[key])
        if stored_value is None:
            continue
        if _safe_int(stored_value) != expected_value:
            issues.append(f"{key}: lagret={_safe_int(stored_value)}, beregnet={expected_value}")
    return issues


def _status_precedence(status: str) -> int:
    order = {
        SEARCHED_RESULTS_FOUND: 8,
        SEARCHED_NO_RESULTS: 7,
        SEARCH_FAILED: 6,
        NOT_SEARCHED_BUDGET: 5,
        NOT_SEARCHED_POLICY: 4,
        NOT_SEARCHED_DISABLED: 3,
        NOT_SEARCHED_UNSUPPORTED: 2,
        NOT_APPLICABLE: 1,
    }
    return order.get(status, 0)


def _trade_score(row: Mapping[str, Any]) -> float | None:
    for key in ("autonomy_adjusted_investment_score", "autonomy_base_investment_score", "investment_score", "score"):
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    reason = str(row.get("reason") or "")
    match = re.search(r"(?:Justert score|Score)\s+([0-9]+(?:[.,][0-9]+)?)", reason, re.I)
    return float(match.group(1).replace(",", ".")) if match else None


def _load_trades(path: Path | None) -> list[Mapping[str, Any]]:
    if path is None:
        return []
    values: list[Mapping[str, Any]] = []
    for _source, value in _json_values(path):
        if isinstance(value, list):
            values.extend(row for row in value if isinstance(row, Mapping))
        elif isinstance(value, Mapping):
            rows = value.get("trades") if isinstance(value.get("trades"), list) else []
            values.extend(row for row in rows if isinstance(row, Mapping))
    return values


def audit(report_paths: Sequence[Path], trades_path: Path | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    area_summaries: list[dict[str, Any]] = []
    budget_issues: list[dict[str, Any]] = []
    source_status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    candidate_gap_counts: Counter[str] = Counter()
    report_summaries: list[dict[str, Any]] = []
    unique_records: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    candidate_count = 0

    for source, run in _report_documents(report_paths):
        run_id = str(run.get("run_id") or source)
        app_version = str(run.get("app_version") or (run.get("report_metadata") or {}).get("app_version") or "")
        candidates = _candidate_rows(run)
        candidate_count += len(candidates)
        report_max_score = max(
            (_safe_float(row.get("investment_score") or row.get("score")) or 0.0 for row in candidates),
            default=0.0,
        )
        threshold = _safe_float((run.get("decision_funnel") or {}).get("production_threshold"))
        if threshold is None:
            threshold = _safe_float((run.get("autonomous_decision_summary") or {}).get("minimum_score"))
        if threshold is None:
            threshold = 73.0
        report_record_count = 0
        report_unknown = 0
        report_gaps = 0
        for candidate_index, candidate in enumerate(candidates):
            raw = _raw_candidate(candidate)
            ticker = str(candidate.get("ticker") or raw.get("ticker") or "UNKNOWN").upper()
            market = str(candidate.get("market") or raw.get("market") or "")
            if market:
                market_counts[market] += 1
            candidate_has_gap = False
            candidate_has_failure = False
            candidate_has_unknown = False
            for area in ("news", "insider"):
                key = f"{area}_intelligence"
                original = raw.get(key) if isinstance(raw.get(key), Mapping) else {}
                payload = normalize_evidence_payload(original, area=area)
                log = [row for row in (payload.get("search_log") or []) if isinstance(row, Mapping)]
                expected_budget = _budget_expected(log)
                issues = _budget_issues(original.get("source_budget") if isinstance(original.get("source_budget"), Mapping) else {}, expected_budget)
                if issues:
                    budget_issues.append({
                        "run_id": run_id,
                        "ticker": ticker,
                        "area": area,
                        "issues": issues,
                    })
                area_summary = {
                    "run_id": run_id,
                    "ticker": ticker,
                    "market": market,
                    "area": area,
                    "json_path": f"candidates[{candidate_index}].raw.{key}",
                    "evidence_status": str(payload.get("canonical_evidence_status") or payload.get("coverage") or payload.get("status") or ""),
                    "search_status": str(payload.get("search_status") or NOT_SEARCHED_POLICY),
                    "reason_counts": dict(payload.get("search_reason_counts") or {}),
                    "unknown_reason_count": _safe_int(payload.get("search_unknown_reason_count")),
                    "source_budget": expected_budget,
                    "budget_consistent": not issues,
                }
                area_summaries.append(area_summary)
                if area_summary["search_status"] in MISSING_SEARCH_STATUSES:
                    candidate_has_gap = True
                if area_summary["search_status"] == SEARCH_FAILED:
                    candidate_has_failure = True
                if area_summary["unknown_reason_count"]:
                    candidate_has_unknown = True

                for log_index, row in enumerate(log):
                    source_name = str(row.get("source") or row.get("source_id") or row.get("source_type") or "AREA_SUMMARY")
                    search_status = str(row.get("search_status") or NOT_SEARCHED_POLICY)
                    reason_code = str(row.get("reason_code") or "UNKNOWN_REASON")
                    legacy_status = str(row.get("legacy_status") or row.get("status") or "UNSPECIFIED")
                    record = {
                        "run_id": run_id,
                        "app_version": app_version,
                        "report_source": source,
                        "ticker": ticker,
                        "market": market,
                        "area": area,
                        "source": source_name,
                        "source_type": str(row.get("source_type") or ""),
                        "json_path": f"candidates[{candidate_index}].raw.{key}.search_log[{log_index}]",
                        "attempted": bool(row.get("attempted")),
                        "legacy_status": legacy_status,
                        "search_status": search_status,
                        "reason_code": reason_code,
                        "results": _safe_int(row.get("results")),
                        "checked_at": str(row.get("checked_at") or row.get("retrieved_at") or ""),
                        "error_or_reason": str(row.get("error") or row.get("reason") or "")[:500],
                        "url": str(row.get("url") or ""),
                        "budget_consistent": not issues,
                    }
                    records.append(record)
                    report_record_count += 1
                    source_status_counts[search_status] += 1
                    reason_counts[reason_code] += 1
                    if reason_code == "UNKNOWN_REASON":
                        report_unknown += 1
                    if search_status in MISSING_SEARCH_STATUSES:
                        report_gaps += 1
                    unique_key = (run_id, ticker, area, source_name.casefold())
                    previous = unique_records.get(unique_key)
                    if previous is None or _status_precedence(search_status) > _status_precedence(str(previous.get("search_status") or "")):
                        unique_records[unique_key] = record
            if candidate_has_gap:
                candidate_gap_counts["not_searched"] += 1
            if candidate_has_failure:
                candidate_gap_counts["search_failed"] += 1
            if candidate_has_unknown:
                candidate_gap_counts["unknown_reason"] += 1
            if bool(candidate.get("evidence_valid_for_decision")):
                candidate_gap_counts["evidence_valid"] += 1
            else:
                candidate_gap_counts["evidence_not_valid"] += 1
        report_summaries.append({
            "run_id": run_id,
            "source": source,
            "app_version": app_version,
            "markets": list(run.get("markets") or []),
            "candidate_count": len(candidates),
            "highest_score": round(report_max_score, 2),
            "production_threshold": threshold,
            "source_log_records": report_record_count,
            "not_searched_source_records": report_gaps,
            "unknown_reason_records": report_unknown,
        })

    unique_list = list(unique_records.values())
    unique_status_counts = Counter(str(row.get("search_status") or "") for row in unique_list)
    unique_reason_counts = Counter(str(row.get("reason_code") or "") for row in unique_list)
    unknown_records = [row for row in unique_list if row.get("reason_code") == "UNKNOWN_REASON"]
    unique_missing = [row for row in unique_list if row.get("search_status") in MISSING_SEARCH_STATUSES]
    unique_failures = [row for row in unique_list if row.get("search_status") == SEARCH_FAILED]

    trades = _load_trades(trades_path)
    buys = [row for row in trades if str(row.get("action") or "").upper() == "BUY"]
    sells = [row for row in trades if str(row.get("action") or "").upper() == "SELL"]
    buy_scores = [score for score in (_trade_score(row) for row in buys) if score is not None]
    historical_reference = {
        "source": str(trades_path or ""),
        "trade_count": len(trades),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "run_count": len({str(row.get("run_id") or "") for row in trades if row.get("run_id")}),
        "first_trade_at": min((str(row.get("timestamp") or "") for row in trades), default=""),
        "last_trade_at": max((str(row.get("timestamp") or "") for row in trades), default=""),
        "buy_score_min": round(min(buy_scores), 3) if buy_scores else None,
        "buy_score_max": round(max(buy_scores), 3) if buy_scores else None,
        "buy_score_median": round(statistics.median(buy_scores), 3) if buy_scores else None,
        "buy_tickers": sorted({str(row.get("ticker") or "") for row in buys}),
        "strategy_roles": dict(Counter(str(row.get("strategy_role") or "LEGACY_UNSPECIFIED") for row in trades)),
        "modes": dict(Counter(str(row.get("mode") or "") for row in trades)),
    }

    code_defects: list[dict[str, Any]] = []
    if unknown_records:
        code_defects.append({
            "code": "UNKNOWN_NOT_SEARCHED_REASON",
            "severity": "ERROR",
            "count": len(unknown_records),
            "description": "Kildesøk mangler maskinlesbar årsak.",
        })
    if budget_issues:
        code_defects.append({
            "code": "SOURCE_BUDGET_COUNTER_MISMATCH",
            "severity": "ERROR",
            "count": len(budget_issues),
            "description": "Lagret kildebudsjett samsvarer ikke med den faktiske søkeloggen.",
        })
    attempted_success_inconsistency = [
        row for row in unique_list
        if not row.get("attempted") and row.get("search_status") in {SEARCHED_RESULTS_FOUND, SEARCHED_NO_RESULTS, SEARCH_FAILED}
    ]
    if attempted_success_inconsistency:
        code_defects.append({
            "code": "ATTEMPT_FLAG_INCONSISTENT",
            "severity": "ERROR",
            "count": len(attempted_success_inconsistency),
            "description": "Søkestatus sier at kilden ble søkt eller feilet, men attempted=false.",
        })

    return {
        "schema": SCHEMA,
        "mode": "DIAGNOSTIC_ONLY",
        "production_parameters_changed": False,
        "reports_analyzed": len(report_summaries),
        "candidates_analyzed": candidate_count,
        "source_log_records": len(records),
        "unique_source_area_records": len(unique_list),
        "unique_not_searched_records": len(unique_missing),
        "unique_search_failed_records": len(unique_failures),
        "unknown_reason_records": len(unknown_records),
        "status_counts": dict(sorted(source_status_counts.items())),
        "unique_status_counts": dict(sorted(unique_status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "unique_reason_counts": dict(sorted(unique_reason_counts.items())),
        "candidate_counts": dict(sorted(candidate_gap_counts.items())),
        "market_candidate_counts": dict(sorted(market_counts.items())),
        "budget_issue_count": len(budget_issues),
        "budget_issues": budget_issues,
        "code_defects": code_defects,
        "report_summaries": report_summaries,
        "historical_autonomy_reference": historical_reference,
        "area_summaries": area_summaries,
        "records": records,
        "unique_records": unique_list,
        "acceptance": {
            "all_records_have_canonical_search_status": all(row.get("search_status") in CANONICAL_SEARCH_STATUSES for row in records),
            "unknown_not_searched_is_zero": len(unknown_records) == 0,
            "source_budgets_match_logs": not budget_issues,
            "plain_not_searched_is_not_used_as_canonical_status": all(row.get("search_status") != "NOT_SEARCHED" for row in records),
            "historical_buy_reference_loaded": bool(buys),
        },
        "interpretation": (
            "Search status is separated from evidence status. SEARCHED_NO_RESULTS is a completed search, "
            "not a source failure. NOT_SEARCHED_* records are counted uniquely by run, candidate, area and source."
        ),
    }


def _write_csv(result: Mapping[str, Any], path: Path) -> None:
    rows = list(result.get("records") or [])
    fields = [
        "run_id", "app_version", "report_source", "ticker", "market", "area", "source", "source_type",
        "json_path", "attempted", "legacy_status", "search_status", "reason_code", "results", "checked_at",
        "error_or_reason", "url", "budget_consistent",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _markdown(result: Mapping[str, Any]) -> str:
    hist = result.get("historical_autonomy_reference") or {}
    acceptance = result.get("acceptance") or {}
    lines = [
        "# Evidenssøkaudit v19.22.0 RC10",
        "",
        "Auditen er diagnostisk og endrer ingen produksjonsparametere.",
        "",
        "## Omfang",
        "",
        f"- Rapporter: {result.get('reports_analyzed', 0)}",
        f"- Kandidater: {result.get('candidates_analyzed', 0)}",
        f"- Rå kildeloggrader: {result.get('source_log_records', 0)}",
        f"- Unike kombinasjoner av kjøring, kandidat, område og kilde: {result.get('unique_source_area_records', 0)}",
        "",
        "## Resultat",
        "",
        f"- Unike ikke-søkte kilder/områder: {result.get('unique_not_searched_records', 0)}",
        f"- Unike søkefeil: {result.get('unique_search_failed_records', 0)}",
        f"- Ukjent årsak: {result.get('unknown_reason_records', 0)}",
        f"- Budsjettavvik: {result.get('budget_issue_count', 0)}",
        "",
        "### Normaliserte statuser",
        "",
    ]
    for key, value in (result.get("unique_status_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines += ["", "### Årsaker", ""]
    for key, value in (result.get("unique_reason_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Historisk Autonomi-referanse",
        "",
        f"- Handler: {hist.get('trade_count', 0)}",
        f"- Kjøp: {hist.get('buy_count', 0)}",
        f"- Salg: {hist.get('sell_count', 0)}",
        f"- Kjøpsscore: {hist.get('buy_score_min')} til {hist.get('buy_score_max')}",
        f"- Siste registrerte handel: {hist.get('last_trade_at') or '-'}",
        "",
        "## Akseptanse",
        "",
    ]
    for key, value in acceptance.items():
        lines.append(f"- {'BESTÅTT' if value else 'IKKE BESTÅTT'}: {key}")
    defects = result.get("code_defects") or []
    lines += ["", "## Faktiske avvik", ""]
    if defects:
        for item in defects:
            lines.append(f"- {item.get('severity')}: {item.get('code')} ({item.get('count')}) - {item.get('description')}")
    else:
        lines.append("- Ingen strukturelle avvik funnet i det analyserte materialet.")
    lines += [
        "",
        "## Tolkning",
        "",
        "Et gjennomført søk uten funn er gyldig kontroll og skal ikke blandes med ikke søkt. "
        "Ikke-søkte poster telles kun én gang per kjøring, kandidat, evidensområde og kilde.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(result: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = "EVIDENCE_SEARCH_AUDIT_v19.22.0_RC10"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_csv(result, csv_path)
    md_path.write_text(_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path, help="Report JSON files, directories or ZIP bundles")
    parser.add_argument("--trades", type=Path, default=None, help="autonomous_trades.json or ZIP")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inputs, args.trades)
    outputs = write_outputs(result, args.output_dir)
    print(json.dumps({
        "reports_analyzed": result["reports_analyzed"],
        "candidates_analyzed": result["candidates_analyzed"],
        "unique_not_searched_records": result["unique_not_searched_records"],
        "unknown_reason_records": result["unknown_reason_records"],
        "budget_issue_count": result["budget_issue_count"],
        "outputs": outputs,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
