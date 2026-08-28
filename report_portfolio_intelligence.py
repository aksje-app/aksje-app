"""Read-only portfolio and capital-efficiency section for scheduled reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from issuer_identity import issuer_identity
from exit_policy import evaluate_exit, policy_from
from short_intelligence import normalize_short_snapshot, portfolio_short_exposure


def _market_for_ticker(ticker: str, explicit: Any = "") -> str:
    """Return the deterministic evidence jurisdiction for a listed symbol."""
    market = str(explicit or "").strip()
    if market:
        return market
    symbol = str(ticker or "").upper().strip()
    suffixes = {
        ".OL": "Norge",
        ".ST": "Sverige",
        ".HE": "Finland",
        ".CO": "Danmark",
        ".SA": "Brasil",
    }
    for suffix, inferred in suffixes.items():
        if symbol.endswith(suffix):
            return inferred
    return "USA"


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


def _nested_evidence(candidate: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Find one evidence payload through legacy candidate wrappers.

    Scheduled runs have historically accumulated ``raw`` wrappers.  Evidence
    retrieval must not depend on the wrapper depth: losing short/insider data
    between the analysed candidate and the portfolio PDF is a publication
    defect, not an acceptable UNKNOWN result.
    """
    current: Mapping[str, Any] = candidate
    for _ in range(10):
        value = current.get(key)
        if isinstance(value, Mapping) and value:
            return dict(value)
        nested = current.get("raw")
        if not isinstance(nested, Mapping):
            break
        current = nested
    return {}


def _with_canonical_evidence(position: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    merged = {**dict(position), **dict(candidate)}
    short_data = _nested_evidence(candidate, "short_data") or _nested_evidence(position, "short_data")
    insider = _nested_evidence(candidate, "insider_intelligence") or _nested_evidence(position, "insider_intelligence")
    if short_data:
        merged["short_data"] = short_data
    if insider:
        merged["insider_intelligence"] = insider
    return merged


def ensure_portfolio_evidence(
    portfolio: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *, force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Guarantee bounded short and insider checks for every open position.

    The ordinary candidate budget may omit an owned issuer. Owned positions
    are never optional report rows, so their evidence checks are performed as
    a small, explicit final pass and merged back into the canonical candidates.
    """
    result = [dict(row) for row in candidates if isinstance(row, Mapping)]
    raw_positions = portfolio.get("positions")
    if isinstance(raw_positions, Mapping):
        positions = [dict(value) | {"ticker": str((value or {}).get("ticker") or ticker)}
                     for ticker, value in raw_positions.items() if isinstance(value, Mapping)]
    elif isinstance(raw_positions, Sequence) and not isinstance(raw_positions, (str, bytes)):
        positions = [dict(row) for row in raw_positions if isinstance(row, Mapping) and row.get("ticker")]
    else:
        positions = []
    by_issuer = {issuer_identity(row): index for index, row in enumerate(result)}
    pending: list[dict[str, Any]] = []
    pending_targets: list[int | None] = []
    for position in positions:
        identity = issuer_identity(position)
        target_index = by_issuer.get(identity)
        candidate = result[target_index] if target_index is not None else {}
        merged = _with_canonical_evidence(position, candidate)
        if target_index is None:
            # This is an owned position appended after the ranked candidate
            # population.  Its valuation, short and insider controls remain
            # mandatory, while candidate-only news discovery is explicitly
            # not applicable.  Persist the role so every report consumer can
            # distinguish that contract from an unexplained missing search.
            merged["coverage_role"] = "PORTFOLIO_ONLY_EXISTING_POSITION"
        short = normalize_short_snapshot(merged)
        insider = merged.get("insider_intelligence") if isinstance(merged.get("insider_intelligence"), Mapping) else {}
        insider_attempted = any(isinstance(item, Mapping) and bool(item.get("attempted")) for item in insider.get("search_log") or [])
        insider_terminal = str(insider.get("coverage") or "NOT_SEARCHED").upper() not in {"", "NOT_SEARCHED"}
        if short.get("coverage") == "UNKNOWN" or not (insider_attempted or insider_terminal):
            market = str(merged.get("market") or merged.get("country") or position.get("market") or position.get("country") or "")
            ticker = str(merged.get("ticker") or position.get("ticker") or "").upper()
            market = _market_for_ticker(ticker, market)
            pending.append({**dict(merged), "ticker": ticker, "market": market})
            pending_targets.append(target_index)
    if not pending:
        return result
    from short_data_sources import enrich_rows as enrich_short_rows
    from insider_intelligence import enrich_rows as enrich_insider_rows
    enriched = enrich_short_rows(pending, force_refresh=force_refresh)
    enriched = enrich_insider_rows(enriched, force_refresh=force_refresh)
    for row, target_index in zip(enriched, pending_targets):
        if target_index is None:
            appended = dict(row)
            appended["coverage_role"] = "PORTFOLIO_ONLY_EXISTING_POSITION"
            result.append(appended)
            by_issuer[issuer_identity(row)] = len(result) - 1
            continue
        target = dict(result[target_index])
        raw = dict(target.get("raw") or {}) if isinstance(target.get("raw"), Mapping) else {}
        raw["short_data"] = dict(row.get("short_data") or {})
        raw["insider_intelligence"] = dict(row.get("insider_intelligence") or {})
        raw["insider_score"] = row.get("insider_score")
        raw["insider_signal"] = row.get("insider_signal")
        target["raw"] = raw
        result[target_index] = target
    return result


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
    owned_issuers_pre = {issuer_identity(dict(raw) if isinstance(raw, Mapping) else {"ticker": ticker}) for ticker, raw in positions.items()}
    replacement_candidates = [row for row in candidates if isinstance(row, Mapping) and issuer_identity(row) not in owned_issuers_pre
                              and bool(row.get("valid_for_decision", True)) and bool(row.get("evidence_valid_for_decision", False))]
    replacement_candidates.sort(key=lambda row: _f(row.get("effective_entry_score"), _f(row.get("investment_score"))), reverse=True)
    best_replacement = replacement_candidates[0] if replacement_candidates else {}
    best_replacement_score = _f(best_replacement.get("effective_entry_score"), _f(best_replacement.get("investment_score"))) if best_replacement else None
    active_policy = policy_from(portfolio.get("exit_policy") if isinstance(portfolio.get("exit_policy"), Mapping) else portfolio.get("parameters"))
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
        exit_decision = evaluate_exit(entry_price=entry, current_price=last,
                                      highest_price=_f(position.get("highest_price"), max(entry, last)),
                                      entry_score=entry_score, current_score=current_score,
                                      holding_days=holding_days,
                                      take_profit_taken=bool(position.get("partial_take_profit_taken")),
                                      best_replacement_score=best_replacement_score, policy=active_policy)
        sideways = exit_decision["reason_code"] in {"CAPITAL_STAGNATION", "CAPITAL_REPLACEMENT"}
        weakened = bool(entry_score and score_change <= -active_policy.score_drop_review_points)
        label = {
            "SELL": "SELG",
            "SELL_PARTIAL": "SIKRE DELVIS GEVINST",
            "REPLACE_REVIEW": "VURDER UTSKIFTING",
            "REVIEW": "KAPITALEFFEKTIVITETSVARSEL",
        }.get(exit_decision["action"], "BEHOLD")
        evidence_row = _with_canonical_evidence(position, candidate)
        short_snapshot = normalize_short_snapshot(evidence_row)
        insider_snapshot = dict(evidence_row.get("insider_intelligence") or {})
        rows.append({
            "ticker": str(ticker), "already_in_portfolio": True, "portfolio_label": "ALLEREDE I PORTEFØLJEN",
            "opened_at": str(position.get("opened_at") or ""), "holding_days": holding_days,
            "quantity": round(quantity, 4), "entry_price": round(entry, 4), "last_price": round(last, 4),
            "market_value": round(last * quantity, 2), "unrealized_pnl": round(pnl_amount, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2), "entry_score": round(entry_score, 2),
            "current_score": round(current_score, 2), "score_change": round(score_change, 2),
            "sideways_20d_proxy": sideways, "weakened_score": weakened, "capital_efficiency_status": label,
            "exit_action": exit_decision["action"], "exit_reason_code": exit_decision["reason_code"],
            "exit_reason": exit_decision["reason"], "suggested_sell_pct": exit_decision["sell_pct"],
            "replacement_ticker": str(best_replacement.get("ticker") or "") if exit_decision["action"] == "REPLACE_REVIEW" else "",
            "replacement_score": round(best_replacement_score, 2) if best_replacement_score is not None and exit_decision["action"] == "REPLACE_REVIEW" else None,
            "source_run_id": str(position.get("source_run_id") or ""),
            "addition_policy": "TILLEGGSKJØP DEAKTIVERT",
            "short_intelligence": short_snapshot,
            "insider_intelligence": insider_snapshot,
            "evidence_contract": {
                "short_checked": short_snapshot.get("coverage") not in {"UNKNOWN", "NOT_SUPPORTED"},
                "short_coverage": short_snapshot.get("coverage"),
                "insider_checked": bool(insider_snapshot.get("search_log")) or str(insider_snapshot.get("coverage") or "NOT_SEARCHED").upper() not in {"", "NOT_SEARCHED"},
                "insider_coverage": str(insider_snapshot.get("coverage") or "NOT_SEARCHED").upper(),
            },
        })
    cash = _f(portfolio.get("cash"))
    initial_cash = _f(portfolio.get("initial_cash"))
    realized_pnl = _f(portfolio.get("realized_pnl"))
    total_cost_basis = sum(_f(row.get("entry_price")) * _f(row.get("quantity")) for row in rows)
    total_market_value = sum(_f(row.get("market_value")) for row in rows)
    total_unrealized_pnl = sum(_f(row.get("unrealized_pnl")) for row in rows)
    equity = cash + total_market_value
    reserve_cash_pct = _f(portfolio.get("reserve_cash_pct"), 10.0)
    required_reserve = equity * reserve_cash_pct / 100.0
    available_cash = max(0.0, cash - required_reserve)
    invested_pct = total_market_value / equity * 100.0 if equity else 0.0
    cash_pct = cash / equity * 100.0 if equity else 100.0
    for row in rows:
        row["portfolio_weight_pct"] = round(_f(row.get("market_value")) / equity * 100.0, 2) if equity else 0.0
        row["cost_basis"] = round(_f(row.get("entry_price")) * _f(row.get("quantity")), 2)
        raw_position = positions.get(str(row.get("ticker") or ""), {})
        row["sector"] = str((raw_position or {}).get("sector") or "Ukjent")
        row["market"] = _market_for_ticker(
            str(row.get("ticker") or ""),
            (raw_position or {}).get("market") or (raw_position or {}).get("country"),
        )
    rows.sort(key=lambda row: (row["capital_efficiency_status"] != "VURDER UTSKIFTING", row["unrealized_pnl_pct"]))
    sector_values: dict[str, float] = {}
    market_values: dict[str, float] = {}
    for row in rows:
        sector_values[row["sector"]] = sector_values.get(row["sector"], 0.0) + _f(row.get("market_value"))
        market_values[row["market"]] = market_values.get(row["market"], 0.0) + _f(row.get("market_value"))
    maximum_open_positions = int(_f(portfolio.get("maximum_open_positions"), _f((portfolio.get("limits") or {}).get("max_positions") if isinstance(portfolio.get("limits"), Mapping) else 20, 20)))
    account_result = equity - initial_cash if initial_cash else realized_pnl + total_unrealized_pnl
    accounting_delta = account_result - realized_pnl - total_unrealized_pnl
    reconciliation = {
        "position_count_matches": len(rows) == len(positions),
        "equity_matches_cash_plus_positions": abs(equity - cash - total_market_value) <= 0.02,
        "weights_match_invested_pct": abs(sum(_f(row.get("portfolio_weight_pct")) for row in rows) - invested_pct) <= max(0.05, 0.01 * len(rows)),
        "account_result_delta": round(accounting_delta, 2),
        "account_result_matches_realized_plus_unrealized": abs(accounting_delta) <= 0.05,
    }
    reconciliation["ok"] = all(bool(reconciliation[key]) for key in (
        "position_count_matches", "equity_matches_cash_plus_positions", "weights_match_invested_pct",
        "account_result_matches_realized_plus_unrealized",
    ))
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
    short_exposure = portfolio_short_exposure(rows)
    return {
        "snapshot_timing": "ETTER_AUTONOMI",
        "snapshot_run_id": str(portfolio.get("last_run_id") or ""),
        "valuation_unit": str(portfolio.get("valuation_currency") or "SIMULERT KONTOENHET"),
        "open_positions": len(rows), "maximum_open_positions": maximum_open_positions,
        "remaining_position_slots": max(0, maximum_open_positions - len(rows)),
        "initial_capital": round(initial_cash, 2), "cash": round(cash, 2),
        "required_cash_reserve": round(required_reserve, 2), "available_purchase_limit": round(available_cash, 2),
        "total_cost_basis": round(total_cost_basis, 2), "total_market_value": round(total_market_value, 2),
        "portfolio_equity": round(equity, 2), "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(total_unrealized_pnl, 2), "total_result": round(account_result, 2),
        "total_return_pct": round(account_result / initial_cash * 100.0, 2) if initial_cash else 0.0,
        "invested_pct": round(invested_pct, 2), "cash_pct": round(cash_pct, 2),
        "reserve_cash_pct": round(reserve_cash_pct, 2),
        "active_exit_policy": active_policy.to_dict(),
        "sideways_positions": sum(row["sideways_20d_proxy"] for row in rows),
        "weakened_positions": sum(row["weakened_score"] for row in rows),
        "replacement_review_count": sum(row["capital_efficiency_status"] == "VURDER UTSKIFTING" for row in rows),
        "positions": rows, "unified_owned_and_candidate_ranking": unified,
        "short_exposure": short_exposure,
        "sector_exposure": [
            {"sector": key, "market_value": round(value, 2), "weight_pct": round(value / equity * 100.0, 2) if equity else 0.0}
            for key, value in sorted(sector_values.items(), key=lambda item: item[1], reverse=True)
        ],
        "market_exposure": [
            {"market": key, "market_value": round(value, 2), "weight_pct": round(value / equity * 100.0, 2) if equity else 0.0}
            for key, value in sorted(market_values.items(), key=lambda item: item[1], reverse=True)
        ],
        "reconciliation": reconciliation,
        "warning": "Kapitalstagnasjon utløser vurdering. Utskifting krever en navngitt, evidensklar kandidat med tilstrekkelig scorefordel.",
    }


def assert_portfolio_report_integrity(report: Mapping[str, Any]) -> None:
    """Block publication when one portfolio snapshot contradicts itself."""
    reconciliation = report.get("reconciliation") if isinstance(report.get("reconciliation"), Mapping) else {}
    if reconciliation.get("ok") is not True:
        failed = [key for key, value in reconciliation.items() if key != "account_result_delta" and value is False]
        raise RuntimeError("Porteføljeregnskapet kunne ikke avstemmes: " + ", ".join(failed or ["ukjent avvik"]))
    contradictions: list[str] = []
    for row in report.get("positions") or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "-")
        contract = row.get("evidence_contract") if isinstance(row.get("evidence_contract"), Mapping) else {}
        short = row.get("short_intelligence") if isinstance(row.get("short_intelligence"), Mapping) else {}
        insider = row.get("insider_intelligence") if isinstance(row.get("insider_intelligence"), Mapping) else {}
        if contract.get("short_checked") and str(short.get("coverage") or "UNKNOWN").upper() == "UNKNOWN":
            contradictions.append(f"{ticker}: short er kontrollert, men presentert som ukjent")
        attempted = any(isinstance(item, Mapping) and bool(item.get("attempted")) for item in insider.get("search_log") or [])
        if attempted and str(insider.get("coverage") or "NOT_SEARCHED").upper() == "NOT_SEARCHED":
            contradictions.append(f"{ticker}: innsider er kontrollert, men presentert som ikke søkt")
    if contradictions:
        raise RuntimeError("Evidenskontrakten er selvmotsigende: " + "; ".join(contradictions))
    rows = list(report.get("positions") or [])
    if int(report.get("open_positions") or 0) != len(rows):
        raise RuntimeError("Porteføljeregnskapet har ulikt posisjonsantall i sammendrag og detaljtabell")


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
        if bool(row.get("analytical_recommendation_ready")):
            continue
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
