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
            "decision_label": str(item.get("decision_label") or item.get("action_label") or item.get("action") or item.get("status") or ""),
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
        return deepcopy(dict(stored))
    document = run.get("report_document")
    if isinstance(document, Mapping):
        return build_channel_projection(document)
    from report_contracts import ensure_report_document
    return build_channel_projection(ensure_report_document(run))


def validate_channel_projection(run: Mapping[str, Any]) -> dict[str, Any]:
    from report_contracts import ensure_report_document
    expected = build_channel_projection(ensure_report_document(run))
    actual = projection_from_run(run)
    errors = []
    for key in ("report_id", "ranking", "decision_count"):
        if actual.get(key) != expected.get(key):
            errors.append(f"{key} avviker mellom kanalprojeksjon og rapportdokument")
    return {"ok": not errors, "errors": errors, "projection": expected}
