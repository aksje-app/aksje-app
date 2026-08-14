"""Auditable investable-universe and sector-coverage contract.

The contract is deliberately honest: packaged symbol lists are a controlled
application universe, not an authoritative exchange master.  A report may say
that the configured universe was fully scanned, but must not claim that every
listed security on an exchange was covered unless an authoritative source has
been configured and verified.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


CANONICAL_SECTORS = (
    "Teknologi", "Finans", "Industri", "Helse", "Energi", "Materialer",
    "Forbruk syklisk", "Forbruk defensiv", "Kommunikasjon", "Eiendom",
    "Forsyning",
)

_ALIASES = {
    "technology": "Teknologi", "information technology": "Teknologi", "teknologi": "Teknologi",
    "financial services": "Finans", "financials": "Finans", "finance": "Finans", "finans": "Finans",
    "industrials": "Industri", "industrial": "Industri", "industri": "Industri",
    "healthcare": "Helse", "health care": "Helse", "helse": "Helse",
    "energy": "Energi", "energi": "Energi",
    "basic materials": "Materialer", "materials": "Materialer", "materialer": "Materialer",
    "consumer cyclical": "Forbruk syklisk", "consumer discretionary": "Forbruk syklisk",
    "forbruk syklisk": "Forbruk syklisk",
    "consumer defensive": "Forbruk defensiv", "consumer staples": "Forbruk defensiv",
    "forbruk defensiv": "Forbruk defensiv",
    "communication services": "Kommunikasjon", "communications": "Kommunikasjon",
    "kommunikasjon": "Kommunikasjon",
    "real estate": "Eiendom", "eiendom": "Eiendom",
    "utilities": "Forsyning", "utility": "Forsyning", "forsyning": "Forsyning",
}


def normalize_sector(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Ukjent"
    return _ALIASES.get(raw.lower(), raw)


def configured_universe_tickers(market: str) -> list[str]:
    from stocks import NORWEGIAN_STOCKS, SWEDISH_STOCKS, US_FALLBACK
    values = {"Norge": NORWEGIAN_STOCKS, "Sverige": SWEDISH_STOCKS, "USA": US_FALLBACK}.get(str(market), [])
    return list(dict.fromkeys(str(value or "").strip().upper() for value in values if str(value or "").strip()))


def build_universe_contract(
    market: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    advanced_tickers: Sequence[str] = (),
    evidence_tickers: Sequence[str] = (),
    source: str = "PACKAGED_CONTROLLED",
) -> dict[str, Any]:
    configured = configured_universe_tickers(market)
    scanned = {str(row.get("ticker") or "").upper() for row in rows if str(row.get("ticker") or "").strip()}
    advanced = {str(value or "").upper() for value in advanced_tickers}
    evidence = {str(value or "").upper() for value in evidence_tickers}
    sector_counts = Counter(normalize_sector(row.get("sector")) for row in rows)
    known_sectors = {sector for sector in sector_counts if sector != "Ukjent"}
    missing_symbols = [ticker for ticker in configured if ticker not in scanned]
    metadata_missing = [
        str(row.get("ticker") or "") for row in rows
        if normalize_sector(row.get("sector")) == "Ukjent"
    ]
    def present(row: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
        return any(row.get(key) not in (None, "", [], {}) for key in keys)

    metadata_fields = {
        "sector": ("sector", "industry"),
        "industry": ("industry",),
        "liquidity": ("liquidity_score", "average_volume", "avg_volume", "volume"),
        "market_cap": ("market_cap", "marketCap"),
        "trading_status": ("trading_status", "tradeable", "quote_type", "data_fetch_status"),
        "data_availability": ("data_fetch_status", "data_fields_used", "history_rows", "price"),
    }
    metadata_completeness = {
        label: {
            "present": sum(1 for row in rows if present(row, keys)),
            "missing": [str(row.get("ticker") or "") for row in rows if not present(row, keys)],
        }
        for label, keys in metadata_fields.items()
    }
    configured_complete = bool(configured) and not missing_symbols
    return {
        "market": market,
        "universe_source": source,
        "source_authoritative_exchange_master": False,
        "source_disclaimer": (
            "Kontrollert applikasjonsunivers; ikke dokumentert som komplett offisiell børsliste."
        ),
        "configured_universe": len(configured),
        "rough_scanned": len(scanned),
        "extended_analyzed": len(advanced),
        "evidence_controlled": len(evidence),
        "configured_universe_complete": configured_complete,
        "coverage_pct": round((len(scanned & set(configured)) / len(configured) * 100.0), 2) if configured else 0.0,
        "missing_symbols": missing_symbols,
        "sector_counts": dict(sorted(sector_counts.items())),
        "known_sector_coverage": f"{len(known_sectors)}/{len(CANONICAL_SECTORS)}",
        "missing_canonical_sectors": [sector for sector in CANONICAL_SECTORS if sector not in known_sectors],
        "missing_sector_metadata": metadata_missing,
        "metadata_completeness": metadata_completeness,
        "exclusion_contract": (
            "Et symbol kan bare utelates fra videre analyse på grunn av dokumentert datamangel, "
            "likviditet/handelsstatus eller rangering etter grovfilteret. Årsaken lagres per symbol."
        ),
        "coverage_failure": bool(missing_symbols),
    }


def select_sector_balanced_rows(rows: Sequence[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reserve analysis seats for sector champions without changing scores."""
    ordered = list(rows)
    limit = max(0, min(int(limit), len(ordered)))
    if not limit:
        return [], {"sector_champions": [], "overall_selected": []}
    champions: list[dict[str, Any]] = []
    seen_sectors: set[str] = set()
    for row in ordered:
        sector = normalize_sector(row.get("sector"))
        if sector == "Ukjent" or sector in seen_sectors:
            continue
        champions.append(row)
        seen_sectors.add(sector)
    # At most half of the expensive analysis budget is reserved for breadth.
    reserved = champions[: max(1, limit // 2)]
    selected: list[dict[str, Any]] = []
    selected_tickers: set[str] = set()
    for row in [*ordered[: max(0, limit - len(reserved))], *reserved, *ordered]:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker in selected_tickers:
            continue
        selected.append(row)
        selected_tickers.add(ticker)
        if len(selected) >= limit:
            break
    selected.sort(key=lambda row: float(row.get("stage1_prefilter_score") or 0), reverse=True)
    return selected, {
        "sector_champions": [str(row.get("ticker") or "") for row in reserved],
        "represented_sectors": sorted({normalize_sector(row.get("sector")) for row in selected}),
        "rule": "Beste totalrangering kombinert med inntil halve analysebudsjettet til sektorvinnere; ingen scorebonus.",
    }


def build_selection_trace(
    rows: Sequence[Mapping[str, Any]], advanced_tickers: Sequence[str], evidence_tickers: Sequence[str]
) -> list[dict[str, Any]]:
    advanced = {str(value or "").upper() for value in advanced_tickers}
    evidence = {str(value or "").upper() for value in evidence_tickers}
    trace = []
    for rank, row in enumerate(rows, 1):
        ticker = str(row.get("ticker") or "").upper()
        stage = "EVIDENS" if ticker in evidence else ("UTVIDET" if ticker in advanced else "GROVFILTER")
        trace.append({
            "rough_rank": rank,
            "ticker": ticker,
            "market": row.get("market"),
            "sector": normalize_sector(row.get("sector")),
            "prefilter_score": row.get("stage1_prefilter_score"),
            "advanced": ticker in advanced,
            "evidence_controlled": ticker in evidence,
            "last_stage": stage,
            "exclusion_reason": "" if ticker in advanced else "Under analysebudsjettets rangerings-/sektorkutt",
        })
    return trace


def build_detection_audit(selection_trace: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], top_n: int = 20) -> dict[str, Any]:
    """Measure whether the strongest observed moves survived selection."""
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in rows}
    ranked = []
    for ticker, row in by_ticker.items():
        observed = None
        for key in ("return_1d", "change_pct", "daily_return", "price_change_pct"):
            try:
                if row.get(key) is not None:
                    observed = float(row.get(key))
                    break
            except (TypeError, ValueError):
                continue
        if observed is not None:
            ranked.append((observed, ticker))
    ranked.sort(reverse=True)
    leaders = [ticker for _, ticker in ranked[: max(1, int(top_n))]]
    trace_by_ticker = {str(row.get("ticker") or "").upper(): row for row in selection_trace}
    advanced = [ticker for ticker in leaders if bool((trace_by_ticker.get(ticker) or {}).get("advanced"))]
    return {
        "basis": "Sterkeste observerte dagsbevegelse i samme kontrollerte univers; kun etterkontroll.",
        "leader_count": len(leaders), "leaders": leaders, "advanced_leaders": advanced,
        "discovery_rate_pct": round(len(advanced) / len(leaders) * 100.0, 2) if leaders else None,
        "not_available_reason": "Dagsavkastning manglet i kandidatgrunnlaget." if not leaders else "",
    }


def build_buy_gate_audit(candidates: Sequence[Mapping[str, Any]], threshold: float = 78.0) -> list[dict[str, Any]]:
    """Explain why every deeply analysed candidate did or did not become BUY."""
    audits: list[dict[str, Any]] = []
    for row in candidates:
        score = float(row.get("investment_score") or 0.0)
        risk = float(row.get("risk_score") or 0.0)
        action = str(row.get("portfolio_action") or "").upper()
        readiness = row.get("decision_readiness") if isinstance(row.get("decision_readiness"), Mapping) else {}
        gates = row.get("quality_gates") if isinstance(row.get("quality_gates"), Mapping) else {}
        blockers = []
        if score < threshold:
            blockers.append(f"score {score:.1f} < produksjonsterskel {threshold:.1f}")
        if not bool(row.get("valid_for_decision")):
            blockers.append("markeds-/grunnlagsdata ikke beslutningsklar")
        if not bool(row.get("evidence_valid_for_decision")):
            blockers.append("evidensport ikke bestått")
        if any(str(value).upper() in {"FAILED", "IKKE BESTÅTT", "BLOCKED"} for value in gates.values()):
            blockers.append("minst én kvalitetsport feilet")
        if int(readiness.get("conflicts") or 0):
            blockers.append("uløst kildekonflikt")
        if action not in {"BUY", "KJØP"}:
            decision = row.get("portfolio_decision") if isinstance(row.get("portfolio_decision"), Mapping) else {}
            reason = str(decision.get("reason") or row.get("autonomy_outcome_reason") or "").strip()
            blockers.append(reason or "porteføljehandlingen er ikke BUY")
        audits.append({
            "ticker": str(row.get("ticker") or ""), "market": row.get("market"),
            "sector": normalize_sector(row.get("sector")), "score": round(score, 2),
            "threshold": threshold, "risk": round(risk, 2), "portfolio_action": action or "UKJENT",
            "buy_ready": not blockers, "first_blocker": blockers[0] if blockers else "Ingen",
            "all_blockers": list(dict.fromkeys(blockers)),
        })
    return sorted(audits, key=lambda item: float(item.get("score") or 0), reverse=True)
