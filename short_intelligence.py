"""Fail-closed short-interest intelligence.

Short volume, price/volume momentum and inferred squeeze pressure are never
treated as reported open short interest.  The helpers are pure so the same
contract can be used by reports, learning and replay exports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


SHORT_SCHEMA_VERSION = "1.0"
VERIFIED_STATUSES = {"VERIFIED", "OFFICIAL", "LICENSED"}


def _f(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def normalize_short_snapshot(candidate: Mapping[str, Any]) -> dict[str, Any]:
    raw = candidate.get("short_data") if isinstance(candidate.get("short_data"), Mapping) else {}
    source = _text(_first(raw, "source", "source_name") or candidate.get("short_source"))
    as_of = _text(_first(raw, "as_of", "reporting_date", "data_date") or candidate.get("short_as_of"))
    published_at = _text(_first(raw, "published_at", "publication_date"))
    status = _text(_first(raw, "verification_status", "status")).upper()
    pct_float = _f(_first(raw, "short_interest_pct_float", "short_float_pct", "short_percent_float") or _first(candidate, "short_interest_pct_float", "short_float_pct"))
    pct_outstanding = _f(_first(raw, "short_interest_pct_outstanding", "short_interest_pct") or _first(candidate, "short_interest_pct_outstanding", "short_interest_pct"))
    shares_short = _f(_first(raw, "shares_short", "short_interest_shares") or _first(candidate, "shares_short", "short_interest_shares"))
    days_to_cover = _f(_first(raw, "days_to_cover", "short_ratio") or _first(candidate, "days_to_cover", "short_ratio"))
    change_pct = _f(_first(raw, "change_pct", "short_interest_change_pct") or candidate.get("short_interest_change_pct"))
    short_volume_pct = _f(_first(raw, "short_volume_pct", "daily_short_volume_pct") or candidate.get("short_volume_pct"))
    has_reported_value = any(value is not None for value in (pct_float, pct_outstanding, shares_short, days_to_cover))
    verified = bool(source and as_of and status in VERIFIED_STATUSES and has_reported_value)
    coverage = "VERIFIED" if verified else ("UNVERIFIED" if has_reported_value else "UNKNOWN")
    return {
        "schema_version": SHORT_SCHEMA_VERSION,
        "ticker": _text(candidate.get("ticker")),
        "market": _text(candidate.get("market")),
        "source": source or None,
        "as_of": as_of or None,
        "published_at": published_at or None,
        "verification_status": status or "UNKNOWN",
        "coverage": coverage,
        "verified": verified,
        "short_interest_pct_float": pct_float,
        "short_interest_pct_outstanding": pct_outstanding,
        "shares_short": shares_short,
        "days_to_cover": days_to_cover,
        "change_pct": change_pct,
        "short_volume_pct": short_volume_pct,
        "short_volume_is_not_short_interest": short_volume_pct is not None,
        "production_score_contribution": 0.0,
        "unknown_not_neutral": not has_reported_value,
    }


def classify_short_context(candidate: Mapping[str, Any], snapshot: Mapping[str, Any] | None = None) -> dict[str, Any]:
    snap = dict(snapshot or normalize_short_snapshot(candidate))
    if not snap.get("verified"):
        return {"classification": "UNKNOWN", "confidence": "LOW", "reason": "Verifisert shortinteresse mangler; volum/momentum brukes ikke som erstatning."}
    pct = _f(snap.get("short_interest_pct_float"))
    if pct is None:
        pct = _f(snap.get("short_interest_pct_outstanding"))
    dtc = _f(snap.get("days_to_cover"))
    trend = _f(_first(candidate, "trend_score", "momentum_score", "technical_score"))
    revisions = _f(_first(candidate, "revision_score", "analyst_revision_score"))
    balance = _f(_first(candidate, "balance_sheet_score", "quality_score"))
    high_short = bool((pct or 0.0) >= 10.0 or (dtc or 0.0) >= 5.0)
    positive = sum(value is not None and value >= 6.5 for value in (trend, revisions, balance))
    negative = sum(value is not None and value <= 4.0 for value in (trend, revisions, balance))
    if high_short and positive >= 2:
        label, reason = "SQUEEZE_WATCH", "Høy shortinteresse kombineres med minst to positive bekreftelser."
    elif high_short and negative >= 2:
        label, reason = "CROWDED_SHORT_RISK", "Høy shortinteresse kombineres med minst to svake bekreftelser."
    elif high_short:
        label, reason = "HIGH_SHORT_UNRESOLVED", "Shortinteressen er høy, men øvrige signaler gir ikke entydig retning."
    else:
        label, reason = "NORMAL_SHORT", "Verifisert shortinteresse er ikke høy etter observasjonsgrensene."
    return {"classification": label, "confidence": "MEDIUM", "reason": reason, "high_short": high_short}


def enrich_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        snapshot = normalize_short_snapshot(row)
        row["short_intelligence"] = {**snapshot, **classify_short_context(row, snapshot)}
        enriched.append(row)
    return enriched


def build_short_report(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for candidate in candidates:
        snapshot = normalize_short_snapshot(candidate)
        context = classify_short_context(candidate, snapshot)
        rows.append({**snapshot, **context})
    verified = [row for row in rows if row["verified"]]
    ranked = sorted(
        verified,
        key=lambda row: (
            row.get("short_interest_pct_float") if row.get("short_interest_pct_float") is not None else row.get("short_interest_pct_outstanding") or -1.0,
            row.get("days_to_cover") or -1.0,
            row.get("ticker") or "",
        ),
        reverse=True,
    )
    return {
        "schema_version": SHORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(rows),
        "verified_count": len(verified),
        "unknown_count": sum(row["coverage"] == "UNKNOWN" for row in rows),
        "coverage_pct": round(100.0 * len(verified) / len(rows), 1) if rows else 0.0,
        "most_shorted_verified": ranked,
        "candidates": rows,
        "decision_policy": "OBSERVE_ONLY",
        "production_score_changed": False,
        "warning": "Shortvolum og momentum er ikke shortinteresse. Manglende data vises som UKJENT.",
    }


def portfolio_short_exposure(positions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total_value = sum((_f(row.get("market_value")) or 0.0) for row in positions)
    verified_value = high_short_value = 0.0
    weighted_short = 0.0
    for row in positions:
        value = _f(row.get("market_value")) or 0.0
        snap = row.get("short_intelligence") if isinstance(row.get("short_intelligence"), Mapping) else normalize_short_snapshot(row)
        if not snap.get("verified"):
            continue
        pct = _f(snap.get("short_interest_pct_float"))
        if pct is None:
            pct = _f(snap.get("short_interest_pct_outstanding"))
        verified_value += value
        weighted_short += value * (pct or 0.0)
        if (pct or 0.0) >= 10.0 or (_f(snap.get("days_to_cover")) or 0.0) >= 5.0:
            high_short_value += value
    return {
        "portfolio_market_value": round(total_value, 2),
        "verified_short_coverage_pct": round(100.0 * verified_value / total_value, 2) if total_value else 0.0,
        "capital_weighted_short_interest_pct": round(weighted_short / verified_value, 2) if verified_value else None,
        "high_short_exposure_pct": round(100.0 * high_short_value / total_value, 2) if total_value else 0.0,
        "unknown_is_excluded": True,
    }


__all__ = ["SHORT_SCHEMA_VERSION", "build_short_report", "classify_short_context", "enrich_candidates", "normalize_short_snapshot", "portfolio_short_exposure"]
