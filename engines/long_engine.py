from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from engines.long_scores.ownership_score import calculate_ownership_score, ownership_score_details
from engines.long_scores.insider_score import calculate_insider_score, insider_score_details
from engines.long_scores.earnings_score import calculate_earnings_score, earnings_score_details
from engines.long_scores.analyst_score import calculate_analyst_score, analyst_score_details


LONG_ALPHA_WEIGHTS = {
    "ownership": 0.35,
    "insider": 0.30,
    "earnings": 0.25,
    "analyst": 0.10,
}


def _ticker(candidate: Mapping[str, Any] | str) -> str:
    if isinstance(candidate, str):
        return candidate.strip().upper()
    return str(candidate.get("ticker") or candidate.get("symbol") or "").strip().upper()


def _as_candidate(candidate: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(candidate, str):
        return {"ticker": candidate.strip().upper()}
    row = dict(candidate)
    row["ticker"] = _ticker(row)
    return row


def calculate_long_alpha_components(candidate: Mapping[str, Any] | str) -> dict[str, Any]:
    """Calculate the Smart Money based Long Alpha component scores.

    Long Alpha is deliberately not momentum-driven, so it can be compared
    against the existing Top Picks engine without simply duplicating it.
    """
    row = _as_candidate(candidate)
    ownership = calculate_ownership_score(row)
    insider = calculate_insider_score(row)
    earnings = calculate_earnings_score(row)
    analyst = calculate_analyst_score(row)
    score = (
        ownership * LONG_ALPHA_WEIGHTS["ownership"]
        + insider * LONG_ALPHA_WEIGHTS["insider"]
        + earnings * LONG_ALPHA_WEIGHTS["earnings"]
        + analyst * LONG_ALPHA_WEIGHTS["analyst"]
    )
    return {
        "ticker": row.get("ticker"),
        "ownership_score": round(ownership, 2),
        "insider_score": round(insider, 2),
        "earnings_score": round(earnings, 2),
        "analyst_score": round(analyst, 2),
        "long_alpha_score": round(score, 2),
    }


def calculate_long_alpha(candidate: Mapping[str, Any] | str) -> float:
    return float(calculate_long_alpha_components(candidate)["long_alpha_score"])


def explain_long_alpha(candidate: Mapping[str, Any] | str) -> dict[str, Any]:
    row = _as_candidate(candidate)
    components = calculate_long_alpha_components(row)
    return {
        **components,
        "weights": dict(LONG_ALPHA_WEIGHTS),
        "details": {
            "ownership": ownership_score_details(row),
            "insider": insider_score_details(row),
            "earnings": earnings_score_details(row),
            "analyst": analyst_score_details(row),
        },
    }


def rank_long_candidates(candidates: Iterable[Mapping[str, Any] | str], *, top_n: int | None = None, progress_callback: Any | None = None) -> list[dict[str, Any]]:
    items = list(candidates or [])
    total = len(items)
    ranked: list[dict[str, Any]] = []
    for idx, candidate in enumerate(items, start=1):
        row = _as_candidate(candidate)
        if not row.get("ticker"):
            continue
        row.update(calculate_long_alpha_components(row))
        ranked.append(row)
        if progress_callback:
            try:
                progress_callback(idx, total, row.get("ticker"))
            except Exception:
                pass

    ranked.sort(
        key=lambda item: (
            float(item.get("long_alpha_score") or 0),
            float(item.get("ownership_score") or 0),
            float(item.get("insider_score") or 0),
            float(item.get("earnings_score") or 0),
        ),
        reverse=True,
    )
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
    if top_n:
        return ranked[: max(0, int(top_n))]
    return ranked


def overlap_score(top_long: Iterable[Mapping[str, Any] | str], top_picks: Iterable[Mapping[str, Any] | str], *, top_n: int = 20) -> dict[str, Any]:
    long_set = {_ticker(item) for item in list(top_long or [])[:top_n] if _ticker(item)}
    picks_set = {_ticker(item) for item in list(top_picks or [])[:top_n] if _ticker(item)}
    if not long_set and not picks_set:
        pct = 0.0
    else:
        pct = 100.0 * len(long_set & picks_set) / max(1, min(len(long_set), len(picks_set)) or len(long_set | picks_set))
    return {
        "overlap_pct": round(pct, 2),
        "overlap_count": len(long_set & picks_set),
        "long_count": len(long_set),
        "top_picks_count": len(picks_set),
        "overlap_tickers": sorted(long_set & picks_set),
    }


def save_top_long_usa_alpha(results: list[dict[str, Any]], path: str | Path = "data/long_engine/top_long_usa_alpha.json") -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine": "Long Engine Alpha",
        "model": "ownership_insider_earnings_analyst",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "weights": LONG_ALPHA_WEIGHTS,
        "count": len(results),
        "results": results,
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def run_top_long_usa_alpha(candidates: Iterable[Mapping[str, Any] | str], *, top_n: int = 20, save: bool = True, progress_callback: Any | None = None) -> list[dict[str, Any]]:
    ranked = rank_long_candidates(candidates, top_n=top_n, progress_callback=progress_callback)
    if save:
        save_top_long_usa_alpha(ranked)
    return ranked
