"""Durable, secret-free evidence that the real Autonomi learning chain ran."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping

from durable_runtime import read_json, write_json
from storage_architecture import runtime_data_path

STATE_KEY = "controlled_learning/acceptance_latest.json"
STATE_PATH = runtime_data_path("controlled_learning", "acceptance_latest.json")
SCHEMA_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (value or []) if isinstance(row, Mapping)]


def _reason(row: Mapping[str, Any]) -> str:
    return str(row.get("first_blocker_code") or row.get("reason") or "").strip()


def first_blocker_code(row: Mapping[str, Any]) -> str:
    existing = str(row.get("first_blocker_code") or "").strip().upper()
    if existing:
        return existing
    reason = str(row.get("reason") or "").casefold()
    action = str(row.get("action") or "").upper()
    rules = (
        (("under læringsgrense",), "LEARNING_SCORE_BELOW_THRESHOLD"),
        (("markedsdata", "beslutningsgyldige"), "MARKET_DATA_INVALID"),
        (("risiko", "læringsgrense"), "LEARNING_RISK_LIMIT"),
        (("mangler gyldig pris", "ugyldig notional"), "PRICE_OR_NOTIONAL_INVALID"),
        (("teknisk timing", "vent"), "TECHNICAL_ENTRY_WAIT"),
        (("duplikat", "finnes allerede"), "DUPLICATE_OR_EXISTING_POSITION"),
        (("nye læringsposisjoner", "per kjøring er nådd"), "LEARNING_CYCLE_POSITION_CAP"),
        (("kapital", "sektorrom"), "CAPITAL_OR_EXPOSURE_LIMIT"),
    )
    for fragments, code in rules:
        if any(fragment in reason for fragment in fragments):
            return code
    # OBSERVE without a gate/blocking phrase means an already-open observation
    # is merely being followed. A threshold-related OBSERVE is classified by
    # the rules above and remains a real blocker.
    if action in {"OBSERVE", "ADD_OBSERVATION", "BUY", "SELL", "CLOSE_OBSERVATION", "PROMOTED"}:
        return "NONE"
    return "UNCLASSIFIED_BLOCKER"


def evaluate_learning_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the persisted production learning path, never a mock path."""
    chain = dict(run.get("autonomous_chain") or {})
    report_id = str(run.get("report_id") or run.get("run_id") or "")
    candidates = _rows(run.get("candidates"))
    learning_decisions = _rows(chain.get("learning_decisions"))
    learning_trades = _rows(chain.get("learning_trades"))
    learning_portfolio = dict(chain.get("learning_portfolio") or {})
    positions = dict(learning_portfolio.get("positions") or {})
    closed = _rows(learning_portfolio.get("closed_positions"))
    performance = dict(chain.get("learning_performance") or {})
    reasons = [_reason(row) for row in learning_decisions]
    decision_trace = [
        {
            "ticker": str(row.get("ticker") or ""), "action": str(row.get("action") or ""),
            "first_blocker_code": first_blocker_code(row), "reason": str(row.get("reason") or ""),
            "score": row.get("score"), "risk": row.get("risk"), "price": row.get("price"),
        }
        for row in learning_decisions
    ]
    blockers = Counter(row["first_blocker_code"] for row in decision_trace if row["first_blocker_code"] != "NONE")
    candidate_tickers = {str(row.get("ticker") or "").upper() for row in candidates if row.get("ticker")}
    decided_tickers = {str(row.get("ticker") or "").upper() for row in learning_decisions if row.get("ticker")}
    portfolio_decisions = run.get("portfolio_decisions")
    canonical_payload = portfolio_decisions if isinstance(portfolio_decisions, Mapping) else {}
    canonical_decisions = _rows(canonical_payload.get("decisions"))
    canonical_tickers = {str(row.get("ticker") or "").upper() for row in canonical_decisions if row.get("ticker")}
    accounted_tickers = decided_tickers | canonical_tickers
    unaccounted_tickers = sorted(candidate_tickers - accounted_tickers)

    checks = {
        "real_autonomy_chain_completed": str(chain.get("status") or "").upper() not in {"", "ERROR", "SKIPPED"},
        "candidates_received": bool(candidates),
        "learning_decisions_recorded": bool(learning_decisions),
        "persistent_learning_state_updated": str(learning_portfolio.get("last_run_id") or "") == report_id,
        "every_learning_decision_explained": bool(learning_decisions) and all(reasons),
        # A candidate rejected before the learning portfolio (for example an
        # invalid data contract or missing price) is still fully accounted for
        # by the canonical portfolio decision. Requiring a second learning row
        # for such a candidate caused false FAIL verdicts.
        "every_candidate_accounted_for": bool(candidate_tickers) and not unaccounted_tickers,
        "learning_observation_exists": bool(learning_trades or positions or closed),
        "performance_snapshot_exists": bool(performance),
        "production_trade_separation": all(str(row.get("mode") or "").upper() == "LEARNING_ONLY" for row in learning_trades),
    }
    hard = ("real_autonomy_chain_completed", "candidates_received", "learning_decisions_recorded", "persistent_learning_state_updated", "every_learning_decision_explained", "every_candidate_accounted_for", "production_trade_separation")
    if not all(checks[key] for key in hard):
        verdict = "FAIL"
    elif checks["learning_observation_exists"] and checks["performance_snapshot_exists"]:
        verdict = "PASS"
    else:
        verdict = "PARTIAL"

    result = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": _now(),
        "verdict": verdict,
        "report_id": report_id,
        "trigger": str(run.get("trigger") or ""),
        "job_id": str(run.get("job_id") or ""),
        "candidate_count": len(candidates),
        "learning_decision_count": len(learning_decisions),
        "learning_trade_count": len(learning_trades),
        "learning_accounted_candidate_count": len(candidate_tickers & decided_tickers),
        "canonical_accounted_candidate_count": len(candidate_tickers & canonical_tickers),
        "unaccounted_candidate_tickers": unaccounted_tickers,
        "open_learning_positions": len(positions),
        "closed_learning_positions": len(closed),
        "checks": checks,
        "blocker_counts": [{"first_blocker_code": code, "count": count} for code, count in blockers.most_common()],
        "decision_trace": decision_trace,
        "learning_trade_ids": [str(row.get("trade_id") or "") for row in learning_trades if row.get("trade_id")],
        "note": "PASS krever reell lagret læringsobservasjon. PARTIAL betyr at kjeden og blokkdiagnostikken virker, men ingen kvalifisert læringsposisjon ble opprettet.",
    }
    write_json(STATE_KEY, STATE_PATH, result)
    return result


def load_latest_learning_acceptance() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def build_learning_diagnostics() -> dict[str, Any]:
    """Return bounded learning diagnostics with no credentials or report payloads."""
    import autonomous_portfolio as ap

    parameters = asdict(ap.load_parameters().normalized())
    allowed_parameters = {
        key: parameters.get(key) for key in (
            "initial_cash", "enable_learning_probe_buys", "learning_probe_minimum_score",
            "learning_probe_maximum_risk_score", "learning_probe_max_buys",
            "learning_probe_notional_value", "learning_probe_horizon_days",
            "stop_loss_pct", "trailing_stop_pct", "take_profit_pct",
        )
    }
    portfolio = dict(ap.load_learning_portfolio() or {})
    positions = dict(portfolio.get("positions") or {})
    position_rows = []
    for ticker, raw in sorted(positions.items()):
        row = dict(raw) if isinstance(raw, Mapping) else {}
        position_rows.append({key: row.get(key) for key in (
            "ticker", "opened_at", "last_evaluated_at", "average_price", "last_price",
            "entry_score", "entry_risk_score", "entry_data_quality", "source_run_id",
            "observation_days", "observation_horizon_days", "production_blockers_at_entry",
            "paper_signal_action", "evidence_valid_at_entry",
            "learning_tier", "learning_cohort", "program_version_at_entry",
            "market", "benchmark_ticker", "benchmark_entry_status",
            "freshness_status", "stale_evaluation_count",
        )})
    decisions = _rows(ap._read(ap.LEARNING_DECISIONS_PATH, []))[:250]
    for row in decisions:
        row.setdefault("first_blocker_code", first_blocker_code(row))
    trades = ap.load_learning_trades(250)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "profile": allowed_parameters,
        "portfolio": {
            "status": portfolio.get("status"), "updated_at": portfolio.get("updated_at"),
            "last_run_id": portfolio.get("last_run_id"), "open_positions": position_rows,
            "open_position_count": len(position_rows),
            "closed_position_count": len(portfolio.get("closed_positions") or []),
        },
        "performance": dict(ap._read(ap.LEARNING_PERFORMANCE_PATH, {}) or {}),
        "quality_diagnostics": ap.learning_quality_diagnostics(portfolio, ap.load_learning_trades()),
        "recent_decisions": decisions,
        "recent_trades": trades,
        "acceptance": load_latest_learning_acceptance(),
    }
