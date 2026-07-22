"""Governed discovery, source control and candidate rotation for Autonomy v18.8.7."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from services.storage_service import get_storage_service


STATE_KEY = "autonomi_core/discovery_data/state.json"
HISTORY_KEY = "autonomi_core/discovery_data/history.json"
SOURCE_PROPOSALS_KEY = "autonomi_core/discovery_data/source_proposals.json"
LAYER_VERSION = "v18.8.7"


@dataclass(frozen=True)
class DiscoveryComposition:
    documented_pct: int = 70
    new_pct: int = 20
    experimental_pct: int = 10

    def validate(self) -> None:
        if self.documented_pct + self.new_pct + self.experimental_pct != 100:
            raise ValueError("Discovery-fordelingen må summere til 100 prosent")


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").strip().upper()


def _fingerprint(row: Mapping[str, Any]) -> str:
    evidence = {
        "ticker": _ticker(row), "source": row.get("source"),
        "news": row.get("news_updated_at") or row.get("latest_news_at"),
        "insider": row.get("insider_updated_at") or row.get("latest_insider_at"),
        "research": row.get("research_updated_at") or row.get("research_version"),
        "score": row.get("score") or row.get("smart_score") or row.get("ai_score"),
    }
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _rotated(rows: Sequence[dict[str, Any]], *, seed: str) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: _ticker(row))
    if not ordered:
        return []
    offset = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(ordered)
    return ordered[offset:] + ordered[:offset]


def _take_unique(target: list[dict[str, Any]], pool: Sequence[dict[str, Any]], count: int, seen: set[str]) -> None:
    for row in pool:
        ticker = _ticker(row)
        if not ticker or ticker in seen:
            continue
        target.append(dict(row)); seen.add(ticker)
        if count > 0 and len(target) >= count:
            return


def select_discovery_candidates(
    primary: Sequence[Mapping[str, Any]], fallback: Sequence[Mapping[str, Any]], *,
    market: str, limit: int, mission_id: str = "", configuration_version: str = "",
    composition: DiscoveryComposition | None = None, run_date: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a traceable, rotating universe without changing downstream scoring."""
    if composition is None:
        try:
            from autonomi_core.configuration.registry import read
            configured = read("discovery.composition", {}) or {}
            composition = DiscoveryComposition(
                documented_pct=int(configured.get("documented_pct", 70)),
                new_pct=int(configured.get("new_pct", 20)),
                experimental_pct=int(configured.get("experimental_pct", 10)),
            )
        except Exception:
            composition = DiscoveryComposition()
    composition.validate()
    limit = max(1, int(limit)); run_date = run_date or datetime.now(timezone.utc).date()
    storage = get_storage_service()
    state = storage.read_json(STATE_KEY, default={}) or {}
    market_state = dict((state.get("markets") or {}).get(market) or {})
    previous = [str(x).upper() for x in market_state.get("tickers") or []]
    previous_set = set(previous)
    previous_fingerprints = dict(market_state.get("fingerprints") or {})

    merged: dict[str, dict[str, Any]] = {}
    for origin, rows in (("DOCUMENTED", primary), ("EXPLORE", fallback)):
        for raw in rows:
            row = dict(raw); ticker = _ticker(row)
            if not ticker or ticker in merged:
                continue
            row["ticker"] = ticker; row["symbol"] = ticker
            row["discovery_origin"] = origin
            merged[ticker] = row

    known = [row for ticker, row in merged.items() if ticker in previous_set]
    documented = [row for row in merged.values() if row["discovery_origin"] == "DOCUMENTED" and _ticker(row) not in previous_set]
    fresh = [row for row in merged.values() if _ticker(row) not in previous_set and row["discovery_origin"] != "DOCUMENTED"]
    experimental_pool = fresh[max(1, len(fresh) // 2):] or documented[-max(1, len(documented) // 4):]
    new_pool = documented + fresh[:max(1, len(fresh) // 2)]
    if not known:  # first run: established provider rows form the documented baseline
        known = documented

    seed = f"{run_date.isoformat()}|{market}|{mission_id}|{configuration_version}"
    known = _rotated(known, seed=seed + "|documented")
    new_pool = _rotated(new_pool, seed=seed + "|new")
    experimental_pool = _rotated(experimental_pool, seed=seed + "|experimental")
    targets = {
        "documented": round(limit * composition.documented_pct / 100),
        "new": round(limit * composition.new_pct / 100),
    }
    targets["experimental"] = max(0, limit - targets["documented"] - targets["new"])
    selected: list[dict[str, Any]] = []; seen: set[str] = set()
    for bucket, pool in (("documented", known), ("new", new_pool), ("experimental", experimental_pool)):
        start = len(selected); wanted_total = start + targets[bucket]
        _take_unique(selected, pool, wanted_total, seen)
        for row in selected[start:]: row["discovery_bucket"] = bucket.upper()
    # Rebalance shortages from every verified pool while retaining traceability.
    _take_unique(selected, known + new_pool + experimental_pool + list(merged.values()), limit, seen)
    selected = selected[:limit]
    for row in selected:
        row.setdefault("discovery_bucket", "DOCUMENTED" if _ticker(row) in previous_set else "NEW")
        fp = _fingerprint(row); old = previous_fingerprints.get(_ticker(row))
        unchanged = bool(old and old == fp)
        row["discovery_fingerprint"] = fp
        row["new_information"] = not unchanged
        row["analysis_quarantine"] = unchanged
        row["analysis_quarantine_reason"] = "Ingen nye kilde-, nyhets-, insider- eller researchopplysninger" if unchanged else ""
        row["mission_id"] = mission_id; row["configuration_version"] = configuration_version

    current = [_ticker(row) for row in selected]
    identical = bool(previous and current == previous)
    if identical and len(merged) > limit:
        unused = next((row for ticker, row in merged.items() if ticker not in seen), None)
        if unused:
            unused = dict(unused); unused["discovery_bucket"] = "EXPERIMENTAL"
            unused["new_information"] = True; unused["analysis_quarantine"] = False
            unused["discovery_fingerprint"] = _fingerprint(unused)
            selected[-1] = unused; current[-1] = _ticker(unused); identical = False

    counts = {name: sum(1 for row in selected if row.get("discovery_bucket") == name) for name in ("DOCUMENTED", "NEW", "EXPERIMENTAL")}
    summary = {
        "version": LAYER_VERSION, "market": market, "mission_id": mission_id,
        "configuration_version": configuration_version, "selected": len(selected),
        "available": len(merged), "composition_target": asdict(composition),
        "composition_actual": counts, "rotated_from_previous": not identical,
        "previous_count": len(previous),
        "quarantined": sum(bool(row.get("analysis_quarantine")) for row in selected),
        "new_information": sum(bool(row.get("new_information")) for row in selected),
        "outside_index_exploration": counts["EXPERIMENTAL"],
        "degraded": bool(identical or len(selected) < limit),
        "degraded_reason": "Kildeuniverset var for lite til garantert rotasjon" if identical or len(selected) < limit else "",
        "source_control": "Kun eksisterende godkjente kilder; nye kilder krever eksplisitt godkjenning",
    }
    state.setdefault("markets", {})[market] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tickers": current,
        "fingerprints": {_ticker(row): row.get("discovery_fingerprint") for row in selected},
        "mission_id": mission_id, "configuration_version": configuration_version,
    }
    state["version"] = LAYER_VERSION; storage.write_json(STATE_KEY, state)
    history = storage.read_json(HISTORY_KEY, default=[]) or []
    history.insert(0, dict(summary, tickers=current)); storage.write_json(HISTORY_KEY, history[:500])
    return selected, summary


def propose_source(name: str, url: str, markets: Sequence[str], reason: str) -> dict[str, Any]:
    """Record a source suggestion; it is never enabled automatically."""
    proposal = {"proposal_id": "SRC-" + hashlib.sha256(f"{name}|{url}".encode()).hexdigest()[:10].upper(),
                "name": name, "url": url, "markets": list(markets), "reason": reason,
                "status": "PENDING_APPROVAL", "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    storage = get_storage_service(); rows = storage.read_json(SOURCE_PROPOSALS_KEY, default=[]) or []
    if not any(row.get("proposal_id") == proposal["proposal_id"] for row in rows):
        rows.insert(0, proposal); storage.write_json(SOURCE_PROPOSALS_KEY, rows[:200])
    return proposal
