"""Controlled Discovery Learning: evidence, Challenger, explicit promotion only."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from services.storage_service import get_storage_service

VERSION = "v18.9.4"
ANALYSES_KEY = "autonomi_core/discovery_learning/analyses.json"
PROPOSALS_KEY = "autonomi_core/discovery_learning/proposals.json"
AUDIT_KEY = "autonomi_core/discovery_learning/audit.jsonl"


def _num(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default


def _group(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        values = row.get(field) or "Ukjent"
        if not isinstance(values, (list, tuple, set)): values = [values]
        for value in values: groups.setdefault(str(value or "Ukjent"), []).append(row)
    result = []
    for name, items in groups.items():
        returns = [_num(x.get("return_pct")) for x in items if x.get("return_pct") is not None]
        result.append({"name": name, "candidates": len(items), "evaluated": len(returns),
                       "average_return_pct": round(sum(returns)/len(returns), 3) if returns else None,
                       "hit_rate_pct": round(100*sum(v > 0 for v in returns)/len(returns), 2) if returns else None,
                       "false_positives": sum(v <= 0 for v in returns)})
    return sorted(result, key=lambda x: (x["average_return_pct"] is not None, x["average_return_pct"] or -999), reverse=True)


def measure_discovery_learning(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure only observed Shadow cohorts; no setting is changed here."""
    rows = []
    for record in records:
        outcomes = ((record.get("comparison") or {}).get("outcomes") or {})
        ready = next((outcomes.get(h) for h in ("90", "30", "5") if (outcomes.get(h) or {}).get("status") == "READY"), {}) or {}
        shadow_return = ((ready.get("shadow") or {}).get("average_return_pct"))
        for candidate in record.get("shadow_candidates") or []:
            row = dict(candidate); row["return_pct"] = shadow_return; rows.append(row)
    new_rows = [x for x in rows if str(x.get("discovery_bucket") or "").upper() in {"NEW", "EXPERIMENTAL"}]
    repeated = [x for x in rows if x not in new_rows]
    exploration = [x for x in rows if str(x.get("discovery_bucket") or "").upper() == "EXPERIMENTAL"]
    false_positive = sum(x.get("return_pct") is not None and _num(x.get("return_pct")) <= 0 and str(x.get("action")) in {"BUY", "REVIEW"} for x in rows)
    return {
        "version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(), "validation_runs": len(records), "candidates": len(rows),
        "sources": _group(rows, "source"), "strategies": _group(rows, "strategies"),
        "novelty": {"new_or_experimental": len(new_rows), "repeated": len(repeated), "new_share_pct": round(100*len(new_rows)/max(1, len(rows)), 2)},
        "markets": _group(rows, "market"), "sectors": _group(rows, "sector"),
        "false_positives": {"count": false_positive, "rate_pct": round(100*false_positive/max(1, len(rows)), 2)},
        "exploration_value": {"candidates": len(exploration), "share_pct": round(100*len(exploration)/max(1, len(rows)), 2),
                              "average_return_pct": next((x.get("average_return_pct") for x in _group(rows, "discovery_bucket") if x.get("name") == "EXPERIMENTAL"), None)},
        "production_changed": False,
    }


def _proposal(kind: str, path: str, before: Any, after: Any, reason: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(f"{kind}|{path}|{after}".encode()).hexdigest()[:12].upper()
    return {"proposal_id": f"DCL-{digest}", "version": VERSION, "type": kind, "path": path, "before": before, "after": after,
            "reason": reason, "evidence": dict(evidence), "status": "CHALLENGER_TESTING", "production_active": False,
            "approval_required": True, "created_at": datetime.now(timezone.utc).isoformat()}


def create_challenger_proposals(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create bounded hypotheses; insufficient evidence creates no weight change."""
    if int(analysis.get("validation_runs") or 0) < 3 or int(analysis.get("candidates") or 0) < 10: return []
    proposals = []
    exploration = dict(analysis.get("exploration_value") or {}); value = exploration.get("average_return_pct")
    current = round(_num(exploration.get("share_pct"), 10))
    if value is not None:
        target = max(5, min(25, current + (5 if _num(value) > 0 else -5)))
        from autonomi_core.configuration.registry import read
        before_composition = read("discovery.composition", {"documented_pct": 70, "new_pct": 20, "experimental_pct": 10})
        after_composition = dict(before_composition); delta = target - int(after_composition.get("experimental_pct", 10))
        after_composition["experimental_pct"] = target
        after_composition["documented_pct"] = max(0, int(after_composition.get("documented_pct", 70)) - delta)
        proposals.append(_proposal("EXPLORATION_SHARE", "discovery.composition", before_composition, after_composition, "Observerte resultater tilsier kontrollert test av utforskningsandelen.", exploration))
    best_source = next((x for x in analysis.get("sources") or [] if int(x.get("evaluated") or 0) >= 3), None)
    if best_source: proposals.append(_proposal("SOURCE_PRIORITY", "discovery.challenger.source_priority", {}, {best_source["name"]: 1}, "Kilden har best modnet kandidatresultat i observasjonsperioden.", best_source))
    best_strategy = next((x for x in analysis.get("strategies") or [] if int(x.get("evaluated") or 0) >= 3), None)
    if best_strategy: proposals.append(_proposal("STRATEGY_WEIGHT", "analysis.challenger.strategy_weights", {}, {best_strategy["name"]: 1.05}, "Strategien testes med en liten Challenger-overvekt.", best_strategy))
    best_segment = next((x for x in (analysis.get("sectors") or []) + (analysis.get("markets") or []) if int(x.get("evaluated") or 0) >= 3), None)
    if best_segment: proposals.append(_proposal("SEARCH_HYPOTHESIS", "discovery.challenger.search_hypotheses", [], [f"Undersøk flere kandidater i {best_segment['name']}"], "Modnet segmentresultat støtter en ny, avgrenset søkehypotese.", best_segment))
    storage = get_storage_service(); existing = storage.read_json(PROPOSALS_KEY, default=[]) or []
    known = {x.get("proposal_id") for x in existing}; created = [x for x in proposals if x["proposal_id"] not in known]
    if created: storage.write_json(PROPOSALS_KEY, (created + existing)[:500])
    return created


def queue_challenger_approval(proposal_id: str) -> dict[str, Any]:
    """Move a tested Challenger into the central explicit approval queue."""
    storage = get_storage_service(); rows = storage.read_json(PROPOSALS_KEY, default=[]) or []
    item = next((x for x in rows if x.get("proposal_id") == proposal_id), None)
    if not item or item.get("status") != "CHALLENGER_TESTING": raise ValueError("Challenger finnes ikke eller er allerede behandlet")
    from autonomi_core.configuration.registry import propose
    approval = propose({str(item["path"]): item.get("after")}, reason=f"Controlled Discovery Learning {proposal_id}: {item.get('reason')}", actor="DISCOVERY_CHALLENGER")
    item["status"] = "PENDING_APPROVAL"; item["central_approval_id"] = approval.get("approval_id"); item["queued_at"] = datetime.now(timezone.utc).isoformat()
    storage.write_json(PROPOSALS_KEY, rows); storage.append_jsonl(AUDIT_KEY, {"event": "APPROVAL_QUEUED", "proposal_id": proposal_id, "approval_id": approval.get("approval_id")})
    return dict(item)


def run_controlled_discovery_learning(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    analysis = measure_discovery_learning(records); created = create_challenger_proposals(analysis)
    storage = get_storage_service(); history = storage.read_json(ANALYSES_KEY, default=[]) or []
    storage.write_json(ANALYSES_KEY, ([analysis] + history)[:500])
    return {"version": VERSION, "analysis": analysis, "created_challengers": created,
            "approval_rule": "Challenger krever eksplisitt godkjenning før produksjon", "production_changed": False}
