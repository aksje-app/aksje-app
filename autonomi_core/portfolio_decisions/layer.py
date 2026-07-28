"""Portfolio-aware decision gateway for Autonomy v19.14.1."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence

from persistent_config_store import read_persistent_json, write_persistent_json
from portfolio_optimizer import PortfolioLimits, load_settings, normalise_positions, position_size

from app_version import APP_VERSION

LAYER_VERSION = APP_VERSION
DISCOVERY_QUEUE_KEY = "autonomi_core/portfolio_decisions/discovery_requests.json"
MARKET_META = {
    "USA": ("USA", "USD"), "Norge": ("Norge", "NOK"), "Sverige": ("Sverige", "SEK"),
    "Finland": ("Finland", "EUR"), "Danmark": ("Danmark", "DKK"), "Brasil": ("Brasil", "BRL"),
}


def _num(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return float(default)


def _identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
    inferred = "Norge" if ticker.endswith(".OL") else "Sverige" if ticker.endswith(".ST") else "Finland" if ticker.endswith(".HE") else "Danmark" if ticker.endswith(".CO") else "Brasil" if ticker.endswith(".SA") else "USA" if ticker and "." not in ticker else "Ukjent"
    market = str(row.get("market") or inferred)
    default_country, default_currency = MARKET_META.get(market, (market, "Ukjent"))
    sector = str(row.get("sector") or row.get("industry") or "Ukjent")
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    country = str(row.get("country") or raw.get("country") or default_country)
    currency = str(row.get("currency") or raw.get("currency") or default_currency).upper()
    return ticker, sector, country, currency


def _exposure(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        name = str(row.get(key) or "Ukjent")
        out[name] = out.get(name, 0.0) + _num(row.get("weight_pct"))
    return {name: round(value, 2) for name, value in out.items()}


def build_portfolio_context(portfolio: Mapping[str, Any], *, limits: PortfolioLimits | None = None) -> dict[str, Any]:
    max_country_pct, max_currency_pct, min_liquidity = 45.0, 55.0, 40.0
    max_candidate_risk = 75.0
    if limits is None:
        limits = load_settings()
        try:
            from autonomous_portfolio import load_parameters
            autonomous = load_parameters()
            limits = PortfolioLimits(
                max_position_pct=min(limits.max_position_pct, autonomous.maximum_position_pct),
                max_sector_pct=min(limits.max_sector_pct, autonomous.maximum_sector_pct),
                max_positions=min(limits.max_positions, autonomous.maximum_open_positions),
                min_cash_pct=max(limits.min_cash_pct, autonomous.reserve_cash_pct),
                max_pair_correlation=limits.max_pair_correlation,
                annual_risk_budget_pct=limits.annual_risk_budget_pct,
                var_confidence=limits.var_confidence,
            )
            max_candidate_risk = autonomous.maximum_risk_score
        except Exception:
            pass
        try:
            from autonomi_core.configuration.registry import read
            decision_config = read("portfolio.decision", {}) or {}
            max_country_pct = _num(decision_config.get("max_country_pct"), max_country_pct)
            max_currency_pct = _num(decision_config.get("max_currency_pct"), max_currency_pct)
            min_liquidity = _num(decision_config.get("minimum_liquidity_score"), min_liquidity)
        except Exception:
            pass
    rows, cash, total = normalise_positions(portfolio)
    source_positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), Mapping) else {}
    for row in rows:
        source = source_positions.get(row["ticker"], {}) if isinstance(source_positions, Mapping) else {}
        _, _, country, currency = _identity(dict(source or {}, ticker=row["ticker"], sector=row.get("sector")))
        row["country"] = row.get("country") or country
        row["currency"] = row.get("currency") or currency
    weights = [_num(row.get("weight_pct")) / 100 for row in rows]
    hhi = sum(weight * weight for weight in weights)
    return {
        "version": LAYER_VERSION, "portfolio_status": portfolio.get("status") or "UKJENT",
        "positions": rows, "position_count": len(rows), "cash": round(cash, 2), "total_value": round(total, 2),
        "cash_pct": round(cash / total * 100, 2) if total else 100.0,
        "concentration_hhi": round(hhi, 4), "effective_positions": round(1 / hhi, 2) if hhi else 0.0,
        "sector_exposure": _exposure(rows, "sector"), "country_exposure": _exposure(rows, "country"),
        "currency_exposure": _exposure(rows, "currency"), "limits": asdict(limits),
        "max_country_pct": max_country_pct, "max_currency_pct": max_currency_pct,
        "minimum_liquidity_score": min_liquidity, "maximum_candidate_risk_score": max_candidate_risk,
        "source": "Autonomous Learning Portfolio + Portfolio Optimizer",
    }


def _correlation_evidence(candidate: Mapping[str, Any], positions: Sequence[Mapping[str, Any]], sector: str, country: str) -> dict[str, Any]:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    explicit = raw.get("portfolio_correlations") or candidate.get("portfolio_correlations")
    if isinstance(explicit, Mapping) and explicit:
        values = [_num(value) for value in explicit.values()]
        return {"method": "MEASURED", "maximum": round(max(values), 3), "pairs": dict(explicit), "confidence": 100}
    if not positions:
        return {"method": "NOT_APPLICABLE_EMPTY_PORTFOLIO", "maximum": 0.0, "pairs": {}, "confidence": 100}
    pairs = {}
    for position in positions:
        same_sector = str(position.get("sector")) == sector
        same_country = str(position.get("country")) == country
        estimate = .68 if same_sector and same_country else .58 if same_sector else .42 if same_country else .25
        pairs[str(position.get("ticker"))] = estimate
    return {"method": "EXPOSURE_PROXY", "maximum": round(max(pairs.values()), 3), "pairs": pairs,
            "confidence": 45, "warning": "Ikke målt kurskorrelasjon; konservativ sektor-/landproxy brukes"}


def assess_candidate(candidate: MutableMapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    ticker, sector, country, currency = _identity(candidate)
    positions = list(context.get("positions") or [])
    existing = next((row for row in positions if str(row.get("ticker")) == ticker), None)
    total = _num(context.get("total_value")); cash = _num(context.get("cash"))
    limits = dict(context.get("limits") or {})
    sector_now = _num((context.get("sector_exposure") or {}).get(sector))
    country_now = _num((context.get("country_exposure") or {}).get(country))
    currency_now = _num((context.get("currency_exposure") or {}).get(currency))
    max_position = _num(limits.get("max_position_pct"), 10)
    max_sector = _num(limits.get("max_sector_pct"), 25)
    max_country = _num(context.get("max_country_pct"), 45)
    max_currency = _num(context.get("max_currency_pct"), 55)
    reserve = _num(limits.get("min_cash_pct"), 15)
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    price = _num(candidate.get("price") or raw.get("current_price") or raw.get("regularMarketPrice"))
    liquidity = _num(candidate.get("liquidity_score"), 0); risk = _num(candidate.get("risk_score"), 100)
    score = _num(candidate.get("investment_score"), 0)
    correlation = _correlation_evidence(candidate, positions, sector, country)
    available_cash = max(0.0, cash - total * reserve / 100)
    rooms = {"position_pct": max_position, "sector_pct": max(0.0, max_sector - sector_now),
             "country_pct": max(0.0, max_country - country_now), "currency_pct": max(0.0, max_currency - currency_now),
             "cash_amount": available_cash}
    requested_pct = max(.5, _num(candidate.get("proposed_position_pct"), max_position))
    allowed_pct = min(requested_pct, rooms["position_pct"], rooms["sector_pct"], rooms["country_pct"], rooms["currency_pct"])
    sizing = position_size(total, price, "prosent", portfolio_pct=max(0.0, allowed_pct), max_amount=available_cash) if total and price else {"amount": 0.0, "shares": 0.0, "portfolio_pct": 0.0}
    blockers = []
    if not candidate.get("valid_for_decision", True): blockers.append("Datakontrakten tillater ikke beslutning")
    if not candidate.get("mission_eligible", True): blockers.append("Kandidaten er utenfor oppdraget")
    min_liquidity = _num(context.get("minimum_liquidity_score"), 40)
    max_candidate_risk = _num(context.get("maximum_candidate_risk_score"), 75)
    if liquidity < min_liquidity: blockers.append(f"Likviditet {liquidity:.1f}/100 er under minimum {min_liquidity:.0f}")
    if risk > max_candidate_risk: blockers.append(f"Risiko {risk:.1f}/100 er over maksimum {max_candidate_risk:.0f}")
    if correlation["maximum"] > _num(limits.get("max_pair_correlation"), .85): blockers.append("Korrelasjonsgrensen overskrides")
    if allowed_pct < .5 or sizing["amount"] <= 0: blockers.append("Ikke tilstrekkelig porteføljerom eller disponibel kontantandel")

    status = str(candidate.get("status") or "")
    if existing:
        action = "SELL" if risk > max_candidate_risk or status in {"AVVIST AV RISIKOPORT", "UTILSTREKKELIGE DATA"} else "HOLD"
        reason = "Eksisterende posisjon bryter risiko-/datavakt" if action == "SELL" else "Eksisterende posisjon beholdes; ingen exitvakt er utløst i porteføljelaget"
    elif blockers:
        hard = any(token in item for item in blockers for token in ("Datakontrakten", "utenfor oppdraget", "Likviditet", "Risiko"))
        action = "SKIP" if hard else "REVIEW"; reason = "; ".join(blockers)
    elif status == "ANBEFALT FOR VURDERING" and candidate.get("strategy_matches"):
        action, reason = "BUY", "Kandidaten passer oppdrag og strategi og har rom innen alle porteføljegrenser"
    elif score >= 60:
        action, reason = "REVIEW", "Porteføljen har rom, men kandidaten krever manuell vurdering før kjøp"
    else:
        action, reason = "SKIP", "Kandidatscore eller strategibevis er ikke sterkt nok"
    decision = {"version": LAYER_VERSION, "ticker": ticker, "action": action, "reason": reason,
                "existing_position": bool(existing), "portfolio_assessed": True, "sector": sector, "country": country, "currency": currency,
                "exposure_before": {"sector_pct": sector_now, "country_pct": country_now, "currency_pct": currency_now},
                "room": {key: round(value, 2) for key, value in rooms.items()}, "correlation": correlation,
                "liquidity_score": liquidity, "risk_score": risk,
                "position_size": {key: round(_num(value), 4) for key, value in sizing.items()},
                "blockers": blockers, "portfolio_source": context.get("source")}
    candidate["portfolio_decision"] = decision; candidate["portfolio_action"] = action
    return decision


def _portfolio_needs(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    needs = []
    if context.get("position_count", 0) == 0:
        needs.append({"type": "DIVERSIFICATION", "target": "Flere bransjer og markeder", "priority": "HIGH"})
    for kind, values, limit in (("SECTOR", context.get("sector_exposure") or {}, _num((context.get("limits") or {}).get("max_sector_pct"), 25)),
                                ("COUNTRY", context.get("country_exposure") or {}, _num(context.get("max_country_pct"), 45)),
                                ("CURRENCY", context.get("currency_exposure") or {}, _num(context.get("max_currency_pct"), 55))):
        if values and max(values.values()) >= limit * .85:
            name = max(values, key=values.get)
            needs.append({"type": kind, "avoid": name, "target": f"Reduser konsentrasjon utenfor {name}", "priority": "HIGH"})
    return needs


def read_portfolio_needs() -> dict[str, Any]:
    """Read the theoretical portfolio before an investment mission is created."""
    from autonomous_portfolio import load_portfolio
    context = build_portfolio_context(load_portfolio())
    needs = _portfolio_needs(context)
    return {
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": context.get("source"),
        "position_count": context.get("position_count", 0),
        "portfolio_value": context.get("portfolio_value", 0),
        "needs": needs,
        "summary": "; ".join(str(item.get("target") or item.get("type")) for item in needs)
                   or "Vedlikehold diversifisering og risikorammer",
        "context": context,
    }


def create_discovery_request(context: Mapping[str, Any], *, mission_id: str, configuration_version: str) -> dict[str, Any] | None:
    needs = _portfolio_needs(context)
    if not needs: return None
    raw = f"{mission_id}|{configuration_version}|{needs}"
    request = {"request_id": "PDR-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper(),
               "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "READY",
               "source": "PORTFOLIO_NEED", "mission_id": mission_id, "configuration_version": configuration_version,
               "needs": needs, "instruction": "Start nytt Discovery-oppdrag som søker diversifisering uten å overskride eksponeringene."}
    queue = read_persistent_json(DISCOVERY_QUEUE_KEY, default=[]) or []
    if not any(row.get("request_id") == request["request_id"] for row in queue):
        queue.insert(0, request); write_persistent_json(DISCOVERY_QUEUE_KEY, queue[:100])
    return request


def apply_portfolio_decisions(candidates: Sequence[MutableMapping[str, Any]], *, mission_id: str = "", configuration_version: str = "") -> dict[str, Any]:
    from autonomous_portfolio import load_portfolio
    context = build_portfolio_context(load_portfolio())
    decisions = [assess_candidate(candidate, context) for candidate in candidates]
    request = create_discovery_request(context, mission_id=mission_id, configuration_version=configuration_version)
    counts = {action: sum(row["action"] == action for row in decisions) for action in ("BUY", "HOLD", "SELL", "SKIP", "REVIEW")}
    return {"version": LAYER_VERSION, "portfolio_context": context, "decisions": decisions, "actions": counts,
            "discovery_request": request, "approval_rule": "Ingen kjøpskandidat vurderes isolert fra eksisterende portefølje"}


def build_portfolio_aware_proposal(candidates: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> dict[str, Any]:
    allocations = []
    for candidate in candidates:
        decision = candidate.get("portfolio_decision") if isinstance(candidate.get("portfolio_decision"), Mapping) else {}
        if decision.get("action") != "BUY":
            continue
        size = decision.get("position_size") or {}
        allocations.append({"ticker": candidate.get("ticker"), "market": candidate.get("market"),
                            "sector": candidate.get("sector"), "country": decision.get("country"), "currency": decision.get("currency"),
                            "weight_pct": _num(size.get("portfolio_pct")), "amount": _num(size.get("amount")),
                            "shares": _num(size.get("shares")), "score": candidate.get("investment_score"),
                            "confidence": candidate.get("confidence_score"), "risk": candidate.get("risk_score"),
                            "decision": "BUY", "portfolio_assessed": True})
    context = summary.get("portfolio_context") or {}
    invested = round(sum(_num(row.get("weight_pct")) for row in allocations), 2)
    return {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "allocations": allocations,
            "positions": allocations, "invested_pct": invested, "cash_pct": max(0.0, round(_num(context.get("cash_pct"), 100) - invested, 2)),
            "status": "PORTFOLIO_AWARE", "actions": dict(summary.get("actions") or {}),
            "approval_rule": summary.get("approval_rule"), "discovery_request": summary.get("discovery_request")}
