"""Trend discovery receipts and audit helpers for RC16.31bf.

This layer is descriptive. It never changes production buy thresholds, risk
limits or trade authorisation. It packages factual market-history fields that
already exist in the candidate enrichment into a stable report/learning
contract.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence

VERSION = "v19.22.0-rc16.31bf"


def _f(value: Any) -> float | None:
    try:
        x=float(value)
        return x if x == x else None
    except Exception:
        return None


def _source(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw=candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    # Enrichment fields live in raw. Keep a compatibility fallback to the row.
    return {**dict(candidate), **dict(raw)}


def _phase(src: Mapping[str, Any]) -> str:
    r5=_f(src.get("return_5d")); r20=_f(src.get("return_20d") or src.get("return_1m")); r60=_f(src.get("return_60d") or src.get("return_3m"))
    last=_f(src.get("last_price")); s20=_f(src.get("sma20")); s50=_f(src.get("sma50"))
    if r20 is None:
        return "UKJENT"
    above20 = last is not None and s20 not in (None,0) and last > s20
    above50 = last is not None and s50 not in (None,0) and last > s50
    if r20 > 4 and (r5 or 0) > 0 and above20 and not above50:
        return "TIDLIG TREND"
    if r20 > 6 and above20 and above50:
        if r60 is not None and r60 > 22 and (r5 or 0) <= max(0.5, r20/6):
            return "MODEN TREND"
        return "ETABLERT TREND"
    if (r5 or 0) < -2 and r20 > 0:
        return "TREND SVEKKES"
    return "NØYTRAL / UBEKREFTET"


def _drivers(src: Mapping[str, Any]) -> list[str]:
    rows=[]
    for label,key in (("5d", "return_5d"),("20d","return_20d"),("60d","return_60d")):
        val=_f(src.get(key))
        if val is not None:
            rows.append((abs(val), f"{label} {val:+.1f} %"))
    vr=_f(src.get("volume_ratio_20"))
    if vr is not None and vr >= 1.2:
        rows.append((min(20.0, vr*5), f"volum {vr:.2f}x 20d"))
    d20=_f(src.get("distance_from_20d_high_pct"))
    if d20 is not None and d20 >= -2.0:
        rows.append((8.0, f"{abs(d20):.1f} % fra 20d-topp"))
    rows.sort(key=lambda x:x[0], reverse=True)
    return [x[1] for x in rows[:3]]


def build_trend_receipt(candidate: Mapping[str, Any], history_item: Mapping[str, Any] | None = None) -> dict[str, Any]:
    src=_source(candidate)
    history_item=dict(history_item or {})
    obs=list(history_item.get("observations") or [])
    previous_rank=obs[-1].get("rank") if obs else None
    current_rank=candidate.get("rank")
    rank_delta=None
    try:
        rank_delta=int(previous_rank)-int(current_rank) if previous_rank and current_rank else None
    except Exception:
        pass
    return {
        "version": VERSION,
        "ticker": str(candidate.get("ticker") or ""),
        "first_discovered_at": history_item.get("first_seen") or candidate.get("created_at") or "",
        "last_seen_at": history_item.get("last_seen") or "",
        "times_seen": int(history_item.get("times_in_list") or len(obs) or 0),
        "rank_change": rank_delta,
        "trend_phase": _phase(src),
        "return_5d_pct": _f(src.get("return_5d")),
        "return_10d_pct": _f(src.get("return_10d")),
        "return_20d_pct": _f(src.get("return_20d") or src.get("return_1m")),
        "return_60d_pct": _f(src.get("return_60d") or src.get("return_3m")),
        "volume_ratio_20": _f(src.get("volume_ratio_20")),
        "sma20": _f(src.get("sma20")),
        "sma50": _f(src.get("sma50")),
        "distance_from_20d_high_pct": _f(src.get("distance_from_20d_high_pct")),
        "distance_from_60d_high_pct": _f(src.get("distance_from_60d_high_pct")),
        "price_trend_60d": list(src.get("price_trend_60d") or [])[-60:],
        "top_trend_drivers": _drivers(src),
        "descriptive_only": True,
    }


def annotate_run(run: dict[str, Any], history: Mapping[str, Any] | None = None) -> dict[str, Any]:
    history=dict(history or {})
    candidates=[row for row in (run.get("candidates") or []) if isinstance(row, Mapping)]
    receipts=[]
    for row in candidates:
        ticker=str(row.get("ticker") or "")
        receipt=build_trend_receipt(row, history.get(ticker) if isinstance(history.get(ticker), Mapping) else {})
        row["trend_receipt"]=receipt
        receipts.append(receipt)
    ranked=[r for r in receipts if r.get("return_20d_pct") is not None]
    ranked.sort(key=lambda r: float(r.get("return_20d_pct") or -1e9), reverse=True)
    run["trend_discovery"]={
        "version": VERSION,
        "mode": "NORWAY_PRODUCTION_STABILIZATION" if run.get("markets") == ["Norge"] else "MULTI_MARKET",
        "top10": ranked[:10],
        "near_candidates": ranked[10:15],
        "coverage": {"candidates": len(candidates), "with_20d_return": len(ranked), "with_60d_chart": sum(1 for r in receipts if len(r.get("price_trend_60d") or []) >= 20)},
        "missed_winner_audit": {"state": "COLLECTING_BASELINE", "note": "Sammenlignes mot bredt markedsunivers når nok daglige observasjoner er lagret."},
        "production_scoring_changed": False,
    }
    return run
