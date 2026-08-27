"""Canonical cross-channel report projection.

PDF, TXT, JSON, Pushover and UI must expose the same immutable report id,
rank order and decision labels. Renderers may add presentation details, but
must not independently recompute these fields.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping

CONTRACT = "AI_AKSJE_ANALYZER_CHANNEL_CONSISTENCY"
VERSION = "1.0"


def build_channel_projection(document: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(document.get("metadata") or {})
    sections = {
        str(row.get("key") or ""): row.get("payload")
        for row in list(document.get("sections") or [])
        if isinstance(row, Mapping)
    }
    candidates = list(sections.get("candidate_decisions") or [])
    ranking: list[dict[str, Any]] = []
    for index, row in enumerate(candidates, start=1):
        item = dict(row or {})
        ranking.append({
            "rank": int(item.get("rank") or index),
            "ticker": str(item.get("ticker") or ""),
            "market": str(item.get("market") or ""),
            "decision": str(item.get("action") or item.get("status") or ""),
            # ReportDocument stores the machine code in ``action`` and the
            # human-facing label in ``status``.  Every public channel must
            # compare the display label with the display label, never the
            # internal enum with translated PDF text.
            "decision_label": str(item.get("decision_label") or item.get("action_label") or item.get("status") or item.get("action") or ""),
            "score": item.get("score"),
        })
    ranking.sort(key=lambda row: (int(row["rank"]), row["ticker"]))
    for index, row in enumerate(ranking, start=1):
        row["rank"] = index
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "report_id": str(metadata.get("report_id") or metadata.get("run_id") or ""),
        "run_id": str(metadata.get("run_id") or ""),
        "report_label": str(metadata.get("report_label") or "Rapport"),
        "ranking": ranking,
        "decision_count": len(ranking),
    }


def attach_channel_projection(run: MutableMapping[str, Any], document: Mapping[str, Any]) -> dict[str, Any]:
    projection = build_channel_projection(document)
    run["channel_consistency"] = deepcopy(projection)
    # The public JSON contract uses the same projection verbatim.
    run["public_report_contract"] = deepcopy(projection)
    return projection


def projection_from_run(run: Mapping[str, Any]) -> dict[str, Any]:
    stored = run.get("channel_consistency")
    if isinstance(stored, Mapping) and stored.get("contract") == CONTRACT:
        projection = deepcopy(dict(stored))
    else:
        document = run.get("report_document")
        if isinstance(document, Mapping):
            projection = build_channel_projection(document)
        else:
            from report_contracts import ensure_report_document
            projection = build_channel_projection(ensure_report_document(run))
    reduction = run.get("autonomous_decision_reduction") or {}
    review = list(run.get("priority_top3") or reduction.get("priority_top3") or [])[:3]
    projection["review_ranking"] = [
        {"rank": index, "ticker": str(row.get("ticker") or ""), "market": str(row.get("market") or ""),
         "decision": str(row.get("portfolio_action") or row.get("autonomy_outcome_code") or ""),
         "decision_label": str(row.get("autonomy_outcome_label") or row.get("decision_label") or ""),
         "score": row.get("investment_score", row.get("score"))}
        for index, row in enumerate(review, 1) if isinstance(row, Mapping)
    ]
    projection["review_count"] = len(projection["review_ranking"])
    return projection


def validate_channel_projection(run: Mapping[str, Any]) -> dict[str, Any]:
    from report_contracts import ensure_report_document
    expected = build_channel_projection(ensure_report_document(run))
    actual = projection_from_run(run)
    errors = []
    for key in ("report_id", "ranking", "decision_count"):
        if actual.get(key) != expected.get(key):
            errors.append(f"{key} avviker mellom kanalprojeksjon og rapportdokument")
    return {"ok": not errors, "errors": errors, "projection": expected}
