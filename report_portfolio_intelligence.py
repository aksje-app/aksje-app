"""Read-only portfolio and capital-efficiency section for scheduled reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from issuer_identity import issuer_identity


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dt(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return result.replace(tzinfo=result.tzinfo or timezone.utc)
    except ValueError:
        return None


def build_portfolio_report(portfolio: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    raw_positions = portfolio.get("positions")
    if isinstance(raw_positions, Mapping):
        positions = dict(raw_positions)
    elif isinstance(raw_positions, Sequence) and not isinstance(raw_positions, (str, bytes)):
        positions = {str(row.get("ticker") or ""): dict(row) for row in raw_positions if isinstance(row, Mapping) and row.get("ticker")}
    else:
        positions = {}
    candidate_by_issuer = {issuer_identity(row): row for row in candidates if isinstance(row, Mapping)}
    rows: list[dict[str, Any]] = []
    for ticker, raw in positions.items():
        position = dict(raw) if isinstance(raw, Mapping) else {}
        position.setdefault("ticker", ticker)
        candidate = candidate_by_issuer.get(issuer_identity(position), {})
        entry = _f(position.get("average_price"))
        last = _f(candidate.get("raw", {}).get("last_price") if isinstance(candidate.get("raw"), Mapping) else 0.0) or _f(position.get("last_price"), entry)
        quantity = _f(position.get("quantity"))
        opened = _dt(position.get("opened_at"))
        holding_days = max(0, (now - opened).days) if opened else 0
        pnl_pct = ((last / entry) - 1.0) * 100.0 if entry > 0 and last > 0 else 0.0
        pnl_amount = (last - entry) * quantity if entry > 0 and last > 0 else 0.0
        entry_score = _f(position.get("entry_score"), _f(position.get("autonomy_adjusted_investment_score")))
        current_score = _f(candidate.get("effective_entry_score"), _f(candidate.get("investment_score"), entry_score))
        score_change = current_score - entry_score if entry_score else 0.0
        sideways = holding_days >= 20 and abs(pnl_pct) < 2.0
        weakened = bool(entry_score and score_change <= -7.0)
        label = "VURDER UTSKIFTING" if sideways and weakened else "KAPITALEFFEKTIVITETSVARSEL" if sideways else "BEHOLD"
        rows.append({
            "ticker": str(ticker), "already_in_portfolio": True, "portfolio_label": "ALLEREDE I PORTEFØLJEN",
            "opened_at": str(position.get("opened_at") or ""), "holding_days": holding_days,
            "quantity": round(quantity, 4), "entry_price": round(entry, 4), "last_price": round(last, 4),
            "market_value": round(last * quantity, 2), "unrealized_pnl": round(pnl_amount, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2), "entry_score": round(entry_score, 2),
            "current_score": round(current_score, 2), "score_change": round(score_change, 2),
            "sideways_20d_proxy": sideways, "weakened_score": weakened, "capital_efficiency_status": label,
            "source_run_id": str(position.get("source_run_id") or ""),
            "addition_policy": "TILLEGGSKJØP DEAKTIVERT",
        })
    rows.sort(key=lambda row: (row["capital_efficiency_status"] != "VURDER UTSKIFTING", row["unrealized_pnl_pct"]))
    owned_issuers = {issuer_identity(dict(raw) if isinstance(raw, Mapping) else {"ticker": ticker}) for ticker, raw in positions.items()}
    unified = []
    for candidate in candidates:
        unified.append({
            "ticker": str(candidate.get("ticker") or ""), "score": round(_f(candidate.get("effective_entry_score"), _f(candidate.get("investment_score"))), 2),
            "market": candidate.get("market"), "sector": candidate.get("sector"),
            "ownership": "EID" if issuer_identity(candidate) in owned_issuers else "IKKE EID",
            "action": (candidate.get("portfolio_decision") or {}).get("action") if isinstance(candidate.get("portfolio_decision"), Mapping) else candidate.get("portfolio_action"),
        })
    unified.sort(key=lambda row: row["score"], reverse=True)
    return {
        "open_positions": len(rows), "maximum_open_positions": int(_f(portfolio.get("maximum_open_positions"), _f((portfolio.get("limits") or {}).get("max_positions") if isinstance(portfolio.get("limits"), Mapping) else 20, 20))),
        "sideways_positions": sum(row["sideways_20d_proxy"] for row in rows),
        "weakened_positions": sum(row["weakened_score"] for row in rows),
        "replacement_review_count": sum(row["capital_efficiency_status"] == "VURDER UTSKIFTING" for row in rows),
        "positions": rows, "unified_owned_and_candidate_ranking": unified,
        "warning": "Sidelengs-proxy er et varsel, ikke et automatisk salgssignal. Indeksrelativ avkastning krever egen benchmarkserie.",
    }


def build_system_anomaly_watch(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in candidates if isinstance(row, Mapping)]
    alerts: list[dict[str, Any]] = []
    technical = [str(row.get("technical_signal_action") or "").upper() for row in rows]
    if rows and technical and all(value in {"HOLD", "WAIT", "HOLD / WAIT"} for value in technical):
        alerts.append({"code": "TECHNICAL_SIGNAL_UNIFORM", "severity": "WARNING", "message": "Teknisk motor ga HOLD/WAIT til 100 % av kandidatene."})
    critical = []
    for row in rows:
        decision = row.get("portfolio_decision") if isinstance(row.get("portfolio_decision"), Mapping) else {}
        gates = decision.get("gates") if isinstance(decision.get("gates"), Mapping) else {}
        blockers = set(decision.get("blocker_codes") or [])
        if gates.get("score_pass") and gates.get("portfolio_room") and gates.get("risk_pass") and "EVIDENCE_NOT_READY" in blockers:
            critical.append(str(row.get("ticker") or ""))
    if critical:
        alerts.append({"code": "COMMON_EVIDENCE_BLOCK", "severity": "CRITICAL", "message": f"{len(critical)} ellers kjøpsklare kandidater blokkeres av evidens.", "tickers": critical})
    return alerts


def build_candidate_watch_queue(candidates: Sequence[Mapping[str, Any]], *, lower: float = 68.0, upper: float = 73.0) -> list[dict[str, Any]]:
    """Keep near-threshold candidates visible without turning them into buys."""
    queue = []
    for row in candidates:
        score = _f(row.get("effective_entry_score"), _f(row.get("investment_score")))
        decision = row.get("portfolio_decision") if isinstance(row.get("portfolio_decision"), Mapping) else {}
        if not (lower <= score < upper) or decision.get("existing_position"):
            continue
        blockers = list(decision.get("blocker_codes") or [])
        queue.append({
            "ticker": str(row.get("ticker") or ""), "market": row.get("market"), "sector": row.get("sector"),
            "score": round(score, 2), "distance_to_production_threshold": round(upper - score, 2),
            "score_trend": row.get("score_trend") or row.get("trend") or "Ukjent",
            "blocker_codes": blockers, "next_action": "Vurderes automatisk på nytt ved neste rapport",
            "not_a_buy_recommendation": True,
        })
    return sorted(queue, key=lambda row: row["score"], reverse=True)
