from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from ranking_service import RankingRequest, RankingResult, rank_candidates, score100


UNIVERSE_RANKING_ADAPTER_VERSION = "v18.6.3br"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _first(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
        low = str(key).lower()
        if low in lowered and lowered[low] not in (None, ""):
            return lowered[low]
    return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _score_0_100(value: Any, default: float = 0.0) -> float:
    number = _as_float(value, None)
    if number is None:
        return float(default)
    if 0.0 <= number <= 1.0:
        number *= 100.0
    elif 0.0 <= number <= 10.0:
        number *= 10.0
    return max(0.0, min(100.0, float(number)))


def _threshold_0_100(value: Any) -> float:
    number = _as_float(value, 0.0) or 0.0
    if 0.0 <= number <= 1.0:
        return score100(number)
    if 0.0 <= number <= 10.0:
        return number * 10.0
    return max(0.0, min(100.0, number))


def _normal_text_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("|", ";").replace(",", ";").split(";")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        parts = [str(part or "").strip() for part in value]
    else:
        parts = [str(value).strip()]
    seen: set[str] = set()
    out: List[str] = []
    for part in parts:
        if not part:
            continue
        marker = part.lower()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(part)
    return out


def _source_score(row: Mapping[str, Any]) -> float:
    for key in ("smart_score", "score", "ai_score", "alpha_score", "early_warning_score", "hidden_potential_score"):
        value = row.get(key)
        if value not in (None, ""):
            return _score_0_100(value)
    return 0.0


def _legacy_score(row: Mapping[str, Any]) -> Any:
    value = row.get("score")
    if value not in (None, ""):
        return value
    smart = row.get("smart_score")
    if smart not in (None, ""):
        number = _as_float(smart, None)
        if number is not None:
            return round(number / 10.0, 2) if number > 10 else number
    return value


def existing_row_to_ranking_row(row: Mapping[str, Any], *, source: str = "") -> Dict[str, Any]:
    """Convert an existing app ranking row to the shared ranking input shape.

    This adapter never fetches market/news/insider data. It only normalizes the
    row already produced by Top Picks, Smart AI, Marked/rangering or cached UI
    state.
    """
    raw = dict(row or {})
    source_label = _clean(source or raw.get("source") or raw.get("decision_source") or "Eksisterende rangering")
    base = _source_score(raw)
    evidence_items = raw.get("evidence_items")
    if not isinstance(evidence_items, Sequence) or isinstance(evidence_items, (str, bytes, bytearray)):
        evidence_items = []

    signals = _normal_text_list(raw.get("signals") or raw.get("signal_tags") or raw.get("recommendation") or source_label)
    if source_label and source_label not in signals:
        signals.append(source_label)

    ranking_row: Dict[str, Any] = {
        **raw,
        "ticker": _first(raw, ("ticker", "symbol", "Ticker"), ""),
        "name": _first(raw, ("name", "longName", "shortName", "company", "Selskap"), ""),
        "market": _first(raw, ("market", "source_market", "Marked"), ""),
        "source": source_label,
        "decision_source": source_label,
        "sector": _first(raw, ("sector", "industry", "Sektor"), ""),
        "score": base,
        "alpha_score": max(base, _score_0_100(raw.get("alpha_score"), 0.0)),
        "ai_score": max(base, _score_0_100(raw.get("ai_score"), 0.0)),
        "smart_score": max(base, _score_0_100(raw.get("smart_score"), 0.0)),
        "timing_score": max(
            _score_0_100(raw.get("strength"), 0.0),
            _score_0_100(raw.get("momentum_strength"), 0.0),
            _score_0_100(raw.get("trend_score"), 0.0),
        ),
        "quality_score": _score_0_100(raw.get("data_quality_score") or raw.get("quality_score"), 58.0),
        "risk_score": _score_0_100(raw.get("risk_score"), 45.0),
        "signals": signals,
        "evidence_items": list(evidence_items),
        "data_quality": raw.get("data_quality") or raw.get("data_quality_label") or "eksisterende ranking/cache",
        "ranking_adapter_version": UNIVERSE_RANKING_ADAPTER_VERSION,
    }
    if raw.get("insider_score") not in (None, ""):
        ranking_row["insider_score"] = _score_0_100(raw.get("insider_score"))
    return ranking_row


def existing_rows_to_ranking_rows(rows: Sequence[Mapping[str, Any]], *, source: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        if not (_first(row, ("ticker", "symbol", "Ticker"), "") or _first(row, ("name", "company", "Selskap"), "")):
            continue
        out.append(existing_row_to_ranking_row(row, source=source))
    return out


def rank_existing_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source: str = "",
    request: Mapping[str, Any] | RankingRequest | None = None,
) -> RankingResult:
    ranking_rows = existing_rows_to_ranking_rows(rows, source=source)
    if isinstance(request, RankingRequest):
        req = request
    else:
        payload = dict(request or {})
        payload.setdefault("max_count", len(ranking_rows) or 30)
        payload.setdefault("label", source or "Felles ranking fra eksisterende rader")
        req = RankingRequest.from_mapping(payload)
    return rank_candidates(ranking_rows, req)


def _index_original_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        ticker = _clean(_first(row, ("ticker", "symbol", "Ticker"), "")).upper().replace(" ", "")
        name = _clean(_first(row, ("name", "company", "Selskap"), ""))
        key = f"ticker:{ticker}" if ticker else f"name:{name.lower()}"
        if key not in by_key:
            by_key[key] = dict(row)
    return by_key


def _ranked_to_legacy_row(ranked: Mapping[str, Any], original: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    original = dict(original or {})
    out = dict(original)
    candidate = ranked.get("candidate") if isinstance(ranked.get("candidate"), Mapping) else {}
    out.setdefault("ticker", ranked.get("ticker") or candidate.get("ticker"))
    out.setdefault("name", ranked.get("name") or candidate.get("name"))
    out.setdefault("market", ranked.get("market") or candidate.get("market"))
    out.setdefault("source", ranked.get("source") or candidate.get("source"))
    legacy_score = _legacy_score(original)
    if legacy_score not in (None, ""):
        out["score"] = legacy_score
    else:
        out["score"] = round((_as_float(ranked.get("score"), 0.0) or 0.0) / 10.0, 2)
    out["shared_rank"] = ranked.get("rank")
    out["shared_score"] = ranked.get("score")
    out["shared_confidence"] = ranked.get("confidence")
    out["shared_recommended_action"] = ranked.get("recommended_action")
    out["shared_score_components"] = ranked.get("score_components") or []
    out["shared_evidence_summary"] = ranked.get("evidence_summary") or {}
    out["shared_risk_flags"] = ranked.get("risk_flags") or []
    out["shared_ranking_version"] = UNIVERSE_RANKING_ADAPTER_VERSION
    return out


def enrich_existing_ranking_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source: str = "",
    max_count: int | None = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    result = rank_existing_rows(
        rows,
        source=source,
        request={"max_count": max_count or len(rows), "label": source or "Eksisterende ranking"},
    )
    original = _index_original_rows(rows)
    out: List[Dict[str, Any]] = []
    for ranked in result.as_dict().get("ranked", []):
        candidate = ranked.get("candidate") if isinstance(ranked.get("candidate"), Mapping) else {}
        ticker = _clean(ranked.get("ticker") or candidate.get("ticker")).upper().replace(" ", "")
        name = _clean(ranked.get("name") or candidate.get("name"))
        key = f"ticker:{ticker}" if ticker else f"name:{name.lower()}"
        out.append(_ranked_to_legacy_row(ranked, original.get(key)))
    return out


def build_shared_top_picks(
    results: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 6.5,
    max_items: int = 10,
    source: str = "Top Picks",
) -> List[Dict[str, Any]]:
    threshold = _threshold_0_100(min_score)
    eligible = [dict(row) for row in results or [] if isinstance(row, Mapping) and _source_score(row) >= threshold]
    if not eligible:
        return []
    return enrich_existing_ranking_rows(eligible, source=source, max_count=max_items)[: max(1, int(max_items or 10))]


def attach_shared_ranking_to_smart_result(result: Mapping[str, Any], *, max_count: int | None = None) -> Dict[str, Any]:
    out = dict(result or {})
    candidates = [dict(row) for row in out.get("candidates", []) or [] if isinstance(row, Mapping)]
    ranked = rank_existing_rows(
        candidates,
        source="Smart AI",
        request={"max_count": max_count or len(candidates) or 30, "label": "Smart AI felles ranking"},
    )
    ranked_dict = ranked.as_dict()
    enriched = enrich_existing_ranking_rows(candidates, source="Smart AI", max_count=max_count or len(candidates) or 30)
    out["shared_ranking"] = ranked_dict
    out["shared_ranking_version"] = UNIVERSE_RANKING_ADAPTER_VERSION
    if enriched:
        out["candidates"] = enriched
        top_limit = len(out.get("top_picks") or []) or min(10, len(enriched))
        out["top_picks"] = enriched[:top_limit]
        out["top_tickers"] = [row.get("ticker") for row in enriched[:top_limit] if row.get("ticker")]
    return out


__all__ = [
    "UNIVERSE_RANKING_ADAPTER_VERSION",
    "attach_shared_ranking_to_smart_result",
    "build_shared_top_picks",
    "enrich_existing_ranking_rows",
    "existing_row_to_ranking_row",
    "existing_rows_to_ranking_rows",
    "rank_existing_rows",
]
