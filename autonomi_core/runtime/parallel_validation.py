"""Read-only parallel validation between legacy authority and Autonomy Core v18.9.3."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from durable_runtime import read_json, write_json

VERSION = "v18.9.3"
ROOT = Path(__file__).resolve().parents[2] / ".app_runtime" / "data" / "autonomi_core" / "parallel_validation"
LATEST_KEY = "autonomi_core/parallel_validation/latest.json"
LATEST_PATH = ROOT / "latest.json"
HISTORY_KEY = "autonomi_core/parallel_validation/history.json"
HISTORY_PATH = ROOT / "history.json"
HORIZONS = (5, 30, 90)


def _num(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or "").strip().upper()


def _legacy_view(run: Mapping[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    candidates = [dict(x) for x in run.get("candidates") or [] if isinstance(x, Mapping)]
    ranked = sorted(candidates, key=lambda x: _num(x.get("investment_score")), reverse=True)
    decisions = {str(x.get("ticker") or "").upper(): str(x.get("action") or "") for x in (run.get("portfolio_decisions") or {}).get("decisions") or []}
    return {"candidates": ranked, "tickers": [_ticker(x) for x in ranked], "decisions": decisions,
            "duration_ms": round((perf_counter() - started) * 1000, 3)}


def _shadow_view(run: Mapping[str, Any]) -> dict[str, Any]:
    started = perf_counter(); rows = []
    for raw in run.get("candidates") or []:
        if not isinstance(raw, Mapping): continue
        row = dict(raw); scores = dict(row.get("strategy_scores") or {})
        best = max((_num((v or {}).get("score") if isinstance(v, Mapping) else v) for v in scores.values()), default=0.0)
        valid = bool(row.get("valid_for_decision", True))
        portfolio_action = str(row.get("portfolio_action") or "REVIEW")
        shadow_action = "SKIP" if not valid or portfolio_action in {"SKIP", "SELL"} else ("BUY" if best >= 70 and row.get("strategy_matches") else "REVIEW")
        row["shadow_score"] = round(best, 2); row["shadow_action"] = shadow_action; rows.append(row)
    rows.sort(key=lambda x: (_num(x.get("shadow_score")), _num(x.get("confidence_score"))), reverse=True)
    return {"candidates": rows, "tickers": [_ticker(x) for x in rows],
            "decisions": {_ticker(x): x.get("shadow_action") for x in rows},
            "duration_ms": round((perf_counter() - started) * 1000, 3)}


def _source_strategy(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sources, strategies = set(), set()
    for row in rows:
        contract = row.get("data_contract") if isinstance(row.get("data_contract"), Mapping) else {}
        for value in (contract.get("source"), row.get("source"), (row.get("raw") or {}).get("source") if isinstance(row.get("raw"), Mapping) else None):
            if value: sources.add(str(value))
        strategies.update(str(x) for x in row.get("strategy_matches") or [])
    return {"sources": sorted(sources), "strategies": sorted(strategies)}


def _api_usage(run: Mapping[str, Any]) -> dict[str, Any]:
    refresh = dict(run.get("data_refresh") or {})
    return {"measurement": "OBSERVED_REQUEST_ATTEMPTS", "authoritative_attempts": int(refresh.get("live_attempt_count") or 0),
            "successful_live": int(refresh.get("live_count") or 0), "cache_hits": int(refresh.get("cache_count") or 0),
            "failed": int(refresh.get("error_count") or 0), "shadow_additional_calls": 0,
            "note": "Shadow gjenbruker samme innhentede datasett og utløser ingen ekstra API-kall."}


def build_parallel_validation(run: Mapping[str, Any], *, total_runtime_seconds: float | None = None) -> dict[str, Any]:
    """Run both pure evaluators concurrently; legacy output remains authoritative."""
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="autonomy-shadow") as pool:
        old_future = pool.submit(_legacy_view, run); shadow_future = pool.submit(_shadow_view, run)
        old, shadow = old_future.result(), shadow_future.result()
    old_set, new_set = set(old["tickers"]), set(shadow["tickers"])
    common = old_set & new_set
    old_rank = {ticker: i + 1 for i, ticker in enumerate(old["tickers"])}
    new_rank = {ticker: i + 1 for i, ticker in enumerate(shadow["tickers"])}
    rank_delta = {ticker: new_rank[ticker] - old_rank[ticker] for ticker in sorted(common)}
    agreements = sum(old["decisions"].get(t) == shadow["decisions"].get(t) for t in common)
    contracts = dict(run.get("data_contract") or {}); portfolio = dict(run.get("portfolio_decisions") or {})
    validation_id = f"PV-{run.get('run_id')}"
    return {
        "version": VERSION, "validation_id": validation_id, "run_id": run.get("run_id"),
        "mission_id": run.get("mission_id"), "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_READ_ONLY", "authoritative_chain": "LEGACY", "shadow_chain": "AUTONOMY_CORE",
        "authority_preserved": True, "writes_blocked": ["TOP_PICKS", "DASHBOARD", "PORTFOLIO", "DECISIONS", "NOTIFICATIONS"],
        "comparison": {
            "candidates": {"authoritative": len(old_set), "shadow": len(new_set), "overlap": len(common), "only_authoritative": sorted(old_set-new_set), "only_shadow": sorted(new_set-old_set), "jaccard_pct": round(100*len(common)/max(1, len(old_set|new_set)), 2)},
            "source_and_search": {"authoritative": _source_strategy(old["candidates"]), "shadow": _source_strategy(shadow["candidates"])},
            "ranking": {"common": len(common), "mean_absolute_rank_delta": round(sum(abs(v) for v in rank_delta.values())/max(1, len(rank_delta)), 3), "rank_delta": rank_delta},
            "decisions": {"compared": len(common), "agreements": agreements, "agreement_pct": round(100*agreements/max(1, len(common)), 2)},
            "data_quality": {"evaluated": contracts.get("evaluated", 0), "valid": contracts.get("valid_for_decision", 0), "blocked": len(contracts.get("blocked") or []), "same_input_snapshot": True},
            "portfolio_risk": {"authoritative_actions": portfolio.get("actions") or {}, "shadow_read_only": True, "context_source": (portfolio.get("portfolio_context") or {}).get("source")},
            "runtime": {"authoritative_seconds": total_runtime_seconds, "legacy_evaluator_ms": old["duration_ms"], "shadow_evaluator_ms": shadow["duration_ms"], "comparison_ms": round((perf_counter()-started)*1000, 3)},
            "api_usage": _api_usage(run),
            "outcomes": {str(h): {"status": "PENDING", "trading_days": h, "authoritative_run_id": run.get("run_id"), "shadow_run_id": f"SHADOW-{run.get('run_id')}"} for h in HORIZONS},
        },
        "shadow_candidates": [{"ticker": _ticker(x), "market": x.get("market"), "sector": x.get("sector"), "source": (x.get("data_contract") or {}).get("source") if isinstance(x.get("data_contract"), Mapping) else x.get("source"), "discovery_bucket": x.get("discovery_bucket"), "strategies": list(x.get("strategy_matches") or []), "rank": i+1, "shadow_score": x.get("shadow_score"), "investment_score": x.get("shadow_score"), "action": x.get("shadow_action"), "status": "ANBEFALT FOR VURDERING" if x.get("shadow_action") in {"BUY", "REVIEW"} else "SKIP", "entry_price": x.get("current_price") or ((x.get("raw") or {}).get("current_price") if isinstance(x.get("raw"), Mapping) else None)} for i, x in enumerate(shadow["candidates"])],
        "approval_rule": "Gammel kjede er autoritativ; Shadow kan bare observere og sammenligne.",
    }


def save_parallel_validation(record: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(record); vid = str(value.get("validation_id") or "")
    if not vid: raise ValueError("validation_id mangler")
    write_json(f"autonomi_core/parallel_validation/runs/{vid}.json", ROOT / "runs" / f"{vid}.json", value)
    write_json(LATEST_KEY, LATEST_PATH, value)
    history = read_json(HISTORY_KEY, HISTORY_PATH, []) or []
    history = [dict(x) for x in history if isinstance(x, Mapping) and x.get("validation_id") != vid]
    write_json(HISTORY_KEY, HISTORY_PATH, ([value] + history)[:500])
    return value


def load_parallel_validation_history(limit: int = 100) -> list[dict[str, Any]]:
    rows = read_json(HISTORY_KEY, HISTORY_PATH, []) or []
    return [dict(x) for x in rows if isinstance(x, Mapping)][:max(1, int(limit))]


def load_latest_parallel_validation() -> dict[str, Any]:
    value = read_json(LATEST_KEY, LATEST_PATH, {})
    return refresh_parallel_outcomes(dict(value)) if isinstance(value, Mapping) and value else {}


def refresh_parallel_outcomes(record: Mapping[str, Any]) -> dict[str, Any]:
    """Attach matured 5/30/90-day comparisons without changing either chain."""
    value = dict(record); comparison = dict(value.get("comparison") or {})
    from historical_learning import run_horizon_performance
    old = run_horizon_performance(str(value.get("run_id") or ""), HORIZONS)
    shadow = run_horizon_performance(f"SHADOW-{value.get('run_id')}", HORIZONS)
    outcomes = {}
    for horizon in HORIZONS:
        key = str(horizon); a, s = old[key], shadow[key]
        ready = a.get("status") == "READY" and s.get("status") == "READY"
        outcomes[key] = {"status": "READY" if ready else "PENDING", "trading_days": horizon,
                         "authoritative": a, "shadow": s,
                         "shadow_minus_authoritative_pct": round(_num(s.get("average_return_pct")) - _num(a.get("average_return_pct")), 3) if ready else None}
    comparison["outcomes"] = outcomes; value["comparison"] = comparison
    write_json(LATEST_KEY, LATEST_PATH, value)
    return value
