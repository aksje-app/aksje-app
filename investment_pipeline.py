"""Investment Pipeline Foundation v18.6.86.

Automated, read-only orchestration from market universe to ranked investment
proposals. The pipeline can scan selected markets (including ``Alle``), rank
Top-N candidates, route them through suitable analysis gates and place final
proposals in a manual review queue. It never executes trades or changes live
rules automatically.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence

from market_universe import BASE_MARKET_SCOPES, FULL_MARKET_SCOPE_LABEL, CORE_MARKET_SCOPE_LABEL, expand_market_scope, market_scope_options
from storage_architecture import runtime_data_path
from durable_runtime import read_json as durable_read_json, write_json as durable_write_json

VERSION = "v18.6.93e"
PIPELINE_DIR = runtime_data_path("investment_pipeline")
RUNS_DIR = PIPELINE_DIR / "runs"
PROPOSALS_DIR = PIPELINE_DIR / "proposals"
REVIEW_QUEUE_PATH = PIPELINE_DIR / "review_queue.json"
LATEST_RUN_PATH = PIPELINE_DIR / "latest_run.json"

STATUS_RECOMMENDED = "ANBEFALT FOR VURDERING"
STATUS_WATCH = "OBSERVASJONSLISTE"
STATUS_MANUAL = "KREVER MANUELL VURDERING"
STATUS_REJECTED = "AVVIST AV RISIKOPORT"
STATUS_INSUFFICIENT = "UTILSTREKKELIGE DATA"


MARKET_SUFFIX_MAP = {
    ".OL": "Norge",
    ".ST": "Sverige",
    ".HE": "Finland",
    ".CO": "Danmark",
    ".SA": "Brasil",
}
MARKET_TICKER_SUFFIX = {
    "Norge": ".OL",
    "Sverige": ".ST",
    "Finland": ".HE",
    "Danmark": ".CO",
    "Brasil": ".SA",
}

NON_EQUITY_DISCOVERY_SYMBOLS = {
    "US10Y", "US02Y", "US05Y", "US30Y", "VIX", "DXY", "SPEMIX",
    "XAUUSD", "UKOILUSD", "GC=F", "BZ=F", "BTC-USD",
}


@lru_cache(maxsize=1)
def _packaged_symbol_markets() -> tuple[dict[str, str], set[str]]:
    """Return known cross-market bare symbols and the packaged US universe."""
    try:
        from stocks import (
            BRAZILIAN_STOCKS, DANISH_STOCKS, FINNISH_STOCKS,
            NORWEGIAN_STOCKS, SWEDISH_STOCKS, US_FALLBACK,
        )
    except Exception:
        return {}, set()
    mapping: dict[str, str] = {}
    for market, values, suffix in (
        ("Norge", NORWEGIAN_STOCKS, ".OL"),
        ("Sverige", SWEDISH_STOCKS, ".ST"),
        ("Finland", FINNISH_STOCKS, ".HE"),
        ("Danmark", DANISH_STOCKS, ".CO"),
        ("Brasil", BRAZILIAN_STOCKS, ".SA"),
    ):
        for value in values:
            symbol = str(value or "").strip().upper()
            if symbol.endswith(suffix):
                mapping.setdefault(symbol[: -len(suffix)], market)
    return mapping, {str(value or "").strip().upper() for value in US_FALLBACK}


def canonical_market_ticker(ticker: str, market: str = "") -> str:
    """Return the Yahoo-compatible symbol without rewriting explicit symbols."""
    symbol = str(ticker or "").strip().upper()
    if not symbol or "." in symbol:
        return symbol
    declared_market = str(market or "").strip()
    if not declared_market:
        packaged_markets, _ = _packaged_symbol_markets()
        declared_market = packaged_markets.get(symbol, "")
    suffix = MARKET_TICKER_SUFFIX.get(declared_market)
    return f"{symbol}{suffix}" if suffix else symbol


def filter_candidate_rows_for_market(
    rows: Sequence[Mapping[str, Any]], expected_market: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject cross-market and non-equity contamination before live requests.

    Explicit row metadata remains authoritative. Plain USA symbols without
    exchange/market metadata must be present in the packaged liquid universe;
    fallback rows then refill any removed capacity.
    """
    expected = str(expected_market or "").strip()
    packaged_markets, packaged_us = _packaged_symbol_markets()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw)
        original = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        declared = str(row.get("market") or row.get("country") or row.get("source_market") or "").strip()
        inferred_packaged = packaged_markets.get(original, "") if original and "." not in original else ""
        effective_market = declared or inferred_packaged or expected
        row = normalize_candidate_identity(row, effective_market)
        ticker = str(row.get("ticker") or "").upper()
        actual = infer_market_from_ticker(ticker, effective_market)
        reason = ""
        if original in NON_EQUITY_DISCOVERY_SYMBOLS:
            reason = "NON_EQUITY_SYMBOL"
        elif expected and expected != "Alle" and actual != expected:
            reason = f"CROSS_MARKET_{actual or 'UNKNOWN'}"
        elif expected == "USA" and "." not in original:
            has_market_proof = bool(declared) or original in packaged_us
            if not has_market_proof:
                reason = "UNVERIFIED_PLAIN_US_SYMBOL"
        if reason:
            rejected.append({
                "ticker": original or ticker,
                "canonical_ticker": ticker,
                "expected_market": expected,
                "actual_market": actual,
                "reason": reason,
            })
            continue
        row["market"] = actual
        row["market_identity_valid"] = True
        accepted.append(row)
    return accepted, rejected

def infer_market_from_ticker(ticker: str, fallback: str = "") -> str:
    symbol = str(ticker or "").strip().upper()
    for suffix, market in MARKET_SUFFIX_MAP.items():
        if symbol.endswith(suffix):
            return market
    if str(fallback or "").strip():
        return str(fallback).strip()
    if symbol and "." not in symbol:
        return "USA"
    return "Ukjent"

def normalize_candidate_identity(row: Mapping[str, Any], expected_market: str = "") -> dict[str, Any]:
    clean = dict(row)
    declared_market = str(clean.get("market") or expected_market or "").strip()
    ticker = canonical_market_ticker(
        str(clean.get("ticker") or clean.get("symbol") or ""),
        declared_market,
    )
    clean["ticker"] = ticker
    clean["symbol"] = ticker
    inferred = infer_market_from_ticker(ticker, declared_market)
    clean["market"] = inferred
    clean["source_market"] = str(clean.get("source_market") or expected_market or inferred)
    clean["market_identity_valid"] = bool(ticker and (expected_market in ("", "Alle") or inferred == expected_market))
    return clean


NUMERIC_FIELDS = {
    "ai_score", "smart_score", "score", "signal_score", "momentum_score", "strength",
    "relative_strength", "rsi_score", "return_1m", "change_1m", "monthly_return",
    "performance_1m", "return_3m", "change_3m", "quarter_return", "performance_3m",
    "trend_score", "technical_score", "fundamental_score", "quality_score", "roe",
    "return_on_equity", "earnings_growth", "eps_growth", "revenue_growth", "growth_score",
    "debt_to_equity", "debt_equity", "net_debt_ebitda", "pe", "trailing_pe",
    "forward_pe", "research_score", "sentiment_score", "news_score", "sentiment",
    "recommendation_score", "analyst_score", "target_upside", "backtest_score",
    "validation_score", "strategy_score", "sharpe", "sharpe_ratio", "win_rate",
    "win_rate_pct", "risk_score", "volatility", "volatility_pct", "annual_volatility",
    "beta", "max_drawdown", "max_drawdown_pct", "drawdown", "liquidity_score",
    "volume_score", "average_volume", "avg_volume", "volume", "data_quality",
    "quality", "data_quality_score", "portfolio_fit_score", "diversification_score",
}

def _sanitize_numeric_fields(row: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    clean = dict(row)
    missing: list[str] = []
    for field in NUMERIC_FIELDS:
        if field not in clean:
            continue
        value = clean.get(field)
        if value in (None, ""):
            clean[field] = None
            missing.append(field)
            continue
        try:
            number = float(value)
            clean[field] = number if math.isfinite(number) else None
            if clean[field] is None:
                missing.append(field)
        except (TypeError, ValueError):
            clean[field] = None
            missing.append(field)
    if missing:
        clean["numeric_fields_missing_or_invalid"] = sorted(set(missing))
    return clean, sorted(set(missing))


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _read_json(path: Path, default: Any) -> Any:
    key = _durable_key(path)
    if key:
        return durable_read_json(key, path, default)
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, payload: Any) -> None:
    key = _durable_key(path)
    if key:
        durable_write_json(key, path, payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _durable_key(path: Path) -> str | None:
    if path == LATEST_RUN_PATH: return "investment_pipeline/latest_run.json"
    if path == REVIEW_QUEUE_PATH: return "investment_pipeline/review_queue.json"
    if path.parent == RUNS_DIR: return f"investment_pipeline/runs/{path.name}"
    if path.parent == PROPOSALS_DIR: return f"investment_pipeline/proposals/{path.name}"
    return None


def _risk_penalty(value: Any) -> float:
    text = str(value or "").strip().lower()
    if any(x in text for x in ("høy", "high", "ekstrem")):
        return 28.0
    if any(x in text for x in ("middels", "medium", "moderat")):
        return 12.0
    if any(x in text for x in ("lav", "low")):
        return 4.0
    return 10.0


def _normalized_score(value: Any, fallback: float = 50.0) -> float:
    score = _f(value, fallback)
    if score <= 1.0:
        score *= 100.0
    elif score <= 10.0:
        score *= 10.0
    return _clamp(score)


def _candidate_id(ticker: str, market: str) -> str:
    digest = hashlib.sha1(f"{ticker}|{market}".encode("utf-8")).hexdigest()[:10].upper()
    return f"IP-{digest}"


@dataclass
class PipelineConfig:
    market_scope: str = "Alle"
    scan_limit: int = 25
    deep_analysis_count: int = 20
    proposal_count: int = 5
    evidence_analysis_count: int = 10
    min_data_quality: float = 45.0
    min_liquidity_score: float = 35.0
    max_risk_score: float = 75.0
    use_research: bool = True
    use_backtest: bool = True
    use_portfolio_fit: bool = True
    use_learning_advisor: bool = True
    use_insider_intelligence: bool = True
    use_news_intelligence: bool = True
    mission_id: str = ""
    configuration_version: str = ""
    full_universe_scan: bool = False
    weights: dict[str, float] = field(default_factory=lambda: {
        "discovery": 0.28,
        "fundamental": 0.18,
        "research": 0.14,
        "validation": 0.17,
        "portfolio_fit": 0.13,
        "risk_adjustment": 0.08,
        "insider": 0.08,
        "news": 0.10,
    })

    def normalized(self) -> "PipelineConfig":
        valid = market_scope_options(include_aggregate=True)
        market = self.market_scope if self.market_scope in valid else "Alle"
        # Scheduled candidate-recall runs may score the complete fetched
        # universe (up to scan_limit=500).  Evidence remains independently
        # bounded, so raising this local deterministic score ceiling does not
        # multiply external intelligence calls.
        deep = max(1, min(int(self.deep_analysis_count), 500))
        scan = 500 if self.full_universe_scan else max(deep, min(int(self.scan_limit), 500))
        proposals = max(0, min(int(self.proposal_count), deep))
        evidence_count = max(proposals, min(max(1, int(self.evidence_analysis_count)), deep))
        weights = {k: max(0.0, _f(v)) for k, v in self.weights.items()}
        total = sum(weights.values()) or 1.0
        weights = {k: v / total for k, v in weights.items()}
        return PipelineConfig(
            market_scope=market,
            scan_limit=scan,
            deep_analysis_count=deep,
            proposal_count=proposals,
            evidence_analysis_count=evidence_count,
            min_data_quality=_clamp(self.min_data_quality),
            min_liquidity_score=_clamp(self.min_liquidity_score),
            max_risk_score=_clamp(self.max_risk_score),
            use_research=bool(self.use_research),
            use_backtest=bool(self.use_backtest),
            use_portfolio_fit=bool(self.use_portfolio_fit),
            use_learning_advisor=bool(self.use_learning_advisor),
            use_insider_intelligence=bool(self.use_insider_intelligence),
            use_news_intelligence=bool(self.use_news_intelligence),
            mission_id=str(self.mission_id or ""),
            configuration_version=str(self.configuration_version or ""),
            full_universe_scan=bool(self.full_universe_scan),
            weights=weights,
        )


@dataclass
class CandidateAssessment:
    candidate_id: str
    ticker: str
    name: str
    market: str
    sector: str
    source: str
    scanner_score: float
    discovery_score: float
    fundamental_score: float
    research_score: float
    validation_score: float
    portfolio_fit_score: float
    risk_score: float
    data_quality: float
    liquidity_score: float
    investment_score: float
    status: str
    quality_gates: dict[str, str]
    positives: list[str]
    risks: list[str]
    proposed_position_pct: float
    strategy_match: str
    confidence_score: float = 0.0
    trend: str = "NY"
    score_delta: float = 0.0
    data_fields_used: list[str] = field(default_factory=list)
    explanation_reasons: list[str] = field(default_factory=list)
    rank: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    strategy_scores: dict[str, Any] = field(default_factory=dict)
    strategy_matches: list[str] = field(default_factory=list)
    scenario_analysis: dict[str, Any] = field(default_factory=dict)
    analysis_ranking: dict[str, Any] = field(default_factory=dict)


def _extract_rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "data"):
        value = getattr(value, "data")
    if isinstance(value, Mapping):
        if "result" in value and isinstance(value.get("result"), Mapping):
            value = value["result"]
        for key in ("ranked_rows", "top_picks", "candidates", "rows"):
            rows = value.get(key) if isinstance(value, Mapping) else None
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                return [dict(r) if isinstance(r, Mapping) else {"ticker": str(r)} for r in rows]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [dict(r) if isinstance(r, Mapping) else {"ticker": str(r)} for r in value]
    return []


def _market_matches(row: Mapping[str, Any], scope: str) -> bool:
    expanded = expand_market_scope(scope)
    if len(expanded) > 1:
        return any(_market_matches(row, market) for market in expanded)
    if len(expanded) == 1 and expanded[0] != str(scope or "").strip():
        return _market_matches(row, expanded[0])
    wanted = str((expanded[0] if expanded else scope) or "").strip().lower()
    actual = str(row.get("market") or row.get("country") or row.get("exchange") or "").strip().lower()
    aliases = {
        "norge": ("norge", "norway", "oslo", "osl"),
        "sverige": ("sverige", "sweden", "stockholm", "sto"),
        "finland": ("finland", "helsinki", "hel"),
        "danmark": ("danmark", "denmark", "copenhagen", "cph"),
        "brasil": ("brasil", "brazil", "sao paulo", "sao"),
        "usa": ("usa", "united states", "nasdaq", "nyse", "amex"),
    }
    accepted = aliases.get(wanted, (wanted,))
    return not actual or any(token in actual for token in accepted)


def _source_row_for_reanalysis(row: Mapping[str, Any]) -> dict[str, Any]:
    """Strip prior analysis wrappers before a new pipeline pass.

    Discovery and cached report rows can already be ``CandidateAssessment``
    objects. Feeding those objects back into ``score_candidate`` used to create
    ``raw.raw.raw`` chains and allowed old analysis outputs to masquerade as
    fresh source fields. Only the deepest source payload is carried forward;
    the previous assessment is retained as a compact, explicitly non-authoritative
    snapshot for traceability.
    """
    outer = dict(row or {})
    current = outer
    depth = 0
    while depth < 8:
        nested = current.get("raw")
        looks_like_assessment = bool(
            isinstance(nested, Mapping)
            and (
                current.get("candidate_id")
                or current.get("investment_score") is not None
                or current.get("quality_gates")
                or current.get("analysis_ranking")
            )
        )
        if not looks_like_assessment:
            break
        current = dict(nested)
        depth += 1

    if depth == 0:
        return outer

    source = dict(current)
    for key in (
        "ticker", "symbol", "name", "shortName", "longName", "market", "country",
        "exchange", "sector", "industry", "source", "source_market",
    ):
        if outer.get(key) not in (None, ""):
            source[key] = outer.get(key)
    source["previous_analysis_snapshot"] = {
        "authoritative": False,
        "wrapper_depth_removed": depth,
        "candidate_id": outer.get("candidate_id"),
        "investment_score": outer.get("investment_score"),
        "confidence_score": outer.get("confidence_score"),
        "risk_score": outer.get("risk_score"),
        "score_trend": outer.get("score_trend") or outer.get("trend"),
        "score_delta": outer.get("score_delta"),
        "status": outer.get("status"),
        "portfolio_action": outer.get("portfolio_action"),
        "rank": outer.get("rank"),
    }
    source["analysis_wrapper_depth_removed"] = depth
    return source


def _prepare_candidate_rows(rows: Sequence[Mapping[str, Any]], config: PipelineConfig, progress_callback: Any | None = None, force_refresh: bool = False) -> list[dict[str, Any]]:
    normalized = []
    for raw in rows:
        source_row = _source_row_for_reanalysis(raw)
        identity = normalize_candidate_identity(source_row, config.market_scope)
        clean, _missing = _sanitize_numeric_fields(identity)
        normalized.append(clean)
    filtered = [r for r in normalized if r.get("ticker") and _market_matches(r, config.market_scope)]
    unique, seen = [], set()
    for row in filtered:
        ticker = row["ticker"]
        if ticker in seen:
            continue
        seen.add(ticker)
        unique.append(row)
    from candidate_market_data import enrich_candidate_rows
    # A complete controlled-universe pass must not serialize hundreds of
    # independent quote lookups.  Eight bounded workers stay below the
    # enricher's own global deadline while the ordinary compact scan keeps its
    # conservative two-worker behaviour.
    workers = 8 if config.full_universe_scan else 2
    return enrich_candidate_rows(unique[: config.scan_limit], max_workers=workers, progress_callback=progress_callback, force_refresh=force_refresh)


def score_candidate(row: Mapping[str, Any], config: PipelineConfig) -> CandidateAssessment:
    from advanced_investment_intelligence import adaptive_weights, derive_scores, load_candidate_trend

    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    name = str(row.get("name") or row.get("shortName") or ticker)
    market = str(row.get("market") or row.get("country") or row.get("exchange") or config.market_scope)
    sector = str(row.get("sector") or row.get("industry") or "Unknown")
    source = str(row.get("source") or "Investment Pipeline")

    derived = derive_scores(row)
    discovery = derived["discovery"]
    momentum = _normalized_score(row.get("momentum_score", row.get("strength", discovery)), discovery)
    fundamental = derived["fundamental"]
    research = derived["research"] if config.use_research else 50.0
    validation = derived["validation"] if config.use_backtest else 50.0
    portfolio_fit = _normalized_score(row.get("portfolio_fit_score", row.get("diversification_score", 50)), 50.0) if config.use_portfolio_fit else 50.0
    risk = derived["risk"]
    data_quality = derived["data_quality"]
    liquidity = derived["liquidity"]

    scanner_score = _clamp(0.50 * discovery + 0.25 * momentum + 0.15 * data_quality + 0.10 * liquidity - 0.18 * risk)
    risk_adjustment = _clamp(100.0 - risk)
    insider = _normalized_score(row.get("insider_score", 50.0), 50.0) if config.use_insider_intelligence else 50.0
    news = _normalized_score(row.get("news_score", 50.0), 50.0) if config.use_news_intelligence else 50.0
    parts = {
        "discovery": discovery,
        "fundamental": fundamental,
        "research": research,
        "validation": validation,
        "portfolio_fit": portfolio_fit,
        "risk_adjustment": risk_adjustment,
        "insider": insider,
        "news": news,
    }
    effective_weights, learning_meta = adaptive_weights(config.weights)
    from autonomi_core.analysis_ranking.layer import analyze_candidate
    parallel_analysis = analyze_candidate(row, derived, adaptive_meta=learning_meta)
    investment = _clamp(sum(parts[k] * effective_weights.get(k, 0.0) for k in parts))
    trend_meta = load_candidate_trend(ticker, investment)

    gates = {
        "Datakvalitet": "BESTÅTT" if data_quality >= config.min_data_quality else "IKKE BESTÅTT",
        "Likviditet": "BESTÅTT" if liquidity >= config.min_liquidity_score else "IKKE BESTÅTT",
        "AI Discovery": "BESTÅTT" if discovery >= 55 else "ADVARSEL",
        "Research": "BESTÅTT" if research >= 50 else "ADVARSEL",
        "Historisk validering": "BESTÅTT" if validation >= 50 else "ADVARSEL",
        "Porteføljetilpasning": "BESTÅTT" if portfolio_fit >= 50 else "ADVARSEL",
        "Risiko": "BESTÅTT" if risk <= config.max_risk_score else "IKKE BESTÅTT",
        "Konfidens": "BESTÅTT" if derived["confidence"] >= 55 else "ADVARSEL",
        "Insider Intelligence": "BESTÅTT" if insider >= 55 else ("ADVARSEL" if insider >= 35 else "IKKE BESTÅTT"),
        "News & Sentiment": "BESTÅTT" if news >= 55 else ("ADVARSEL" if news >= 35 else "IKKE BESTÅTT"),
    }
    failed = [k for k, v in gates.items() if v == "IKKE BESTÅTT"]
    warnings = [k for k, v in gates.items() if v == "ADVARSEL"]
    real_fields = list(derived.get("data_fields_used") or [])
    fetch_status = str(row.get("data_fetch_status") or "").upper()
    if not ticker or (not real_fields and fetch_status in {"ERROR", "NO_DATA"}):
        status = STATUS_INSUFFICIENT
    elif failed:
        status = STATUS_REJECTED
    elif investment >= 72 and derived["confidence"] >= 60 and len(warnings) <= 1:
        status = STATUS_RECOMMENDED
    elif investment >= 60:
        status = STATUS_MANUAL if warnings else STATUS_WATCH
    else:
        status = STATUS_WATCH

    positives, risks = [], []
    for label, score in (("AI Discovery", discovery), ("Fundamentaler", fundamental), ("Research", research), ("Backtest", validation), ("Porteføljetilpasning", portfolio_fit), ("Insider Intelligence", insider), ("News & Sentiment", news)):
        if score >= 65:
            positives.append(f"{label} trekker opp ({score:.0f}/100).")
        elif score < 45:
            risks.append(f"{label} trekker ned ({score:.0f}/100).")
    if trend_meta["trend"] == "STIGENDE":
        positives.append(f"Kandidatscoren stiger ({trend_meta['score_delta']:+.1f} siden forrige observasjon).")
    elif trend_meta["trend"] == "FALLENDE":
        risks.append(f"Kandidatscoren faller ({trend_meta['score_delta']:+.1f} siden forrige observasjon).")
    if risk > 65:
        risks.append(f"Risikoscore er høy ({risk:.0f}/100).")
    if data_quality < 60:
        risks.append(f"Datakvalitet er begrenset ({data_quality:.0f}/100).")
    if derived["confidence"] < 55:
        risks.append(f"Lav analysekontfidens ({derived['confidence']:.0f}/100) på grunn av manglende individuelle datapunkter.")
    positives.extend(x for x in derived["explanation_reasons"] if "positiv" in x or "trekker opp" in x)
    if not positives:
        positives.append("Ingen enkeltfaktor er sterk nok til å dominere totalbildet.")
    if not risks:
        risks.append("Ingen alvorlige risikoflagg i tilgjengelig datasett; risikokontroll kreves fortsatt.")

    parallel_matches = list(parallel_analysis.get("matches") or [])
    strategy = str(row.get("strategy_match") or (parallel_matches[0] if parallel_matches else ("Momentum" if momentum >= 68 else "Defensive")))
    proposed_position = max(0.5, min(6.0, (investment * derived["confidence"] / 100.0 - risk * 0.20) / 15.0))
    raw = dict(row)
    raw["effective_weights"] = effective_weights
    raw["adaptive_learning"] = learning_meta
    raw["component_trace"] = derived.get("component_trace") or {}
    raw["score_formula"] = {
        "parts": {k: round(v, 2) for k, v in parts.items()},
        "weights": {k: round(effective_weights.get(k, 0.0), 4) for k in parts},
        "weighted_contributions": {k: round(parts[k] * effective_weights.get(k, 0.0), 2) for k in parts},
        "investment_score": round(investment, 2),
    }
    raw["score_trend"] = trend_meta["trend"]
    raw["score_trend_basis"] = "Kandidatscore sammenlignet med forrige analysekjøring"
    raw["score_trend_observations"] = trend_meta.get("observations", 0)
    raw["score_trend_average"] = trend_meta.get("average_score")
    return CandidateAssessment(
        candidate_id=_candidate_id(ticker, market), ticker=ticker, name=name, market=market,
        sector=sector, source=source, scanner_score=round(scanner_score, 2),
        discovery_score=round(discovery, 2), fundamental_score=round(fundamental, 2),
        research_score=round(research, 2), validation_score=round(validation, 2),
        portfolio_fit_score=round(portfolio_fit, 2), risk_score=round(risk, 2),
        data_quality=round(data_quality, 2), liquidity_score=round(liquidity, 2),
        investment_score=round(investment, 2), status=status, quality_gates=gates,
        positives=positives, risks=risks, proposed_position_pct=round(proposed_position, 2),
        strategy_match=strategy, confidence_score=round(derived["confidence"], 2),
        trend=trend_meta["trend"], score_delta=trend_meta["score_delta"],
        data_fields_used=derived["data_fields_used"], explanation_reasons=derived["explanation_reasons"],
        raw=raw,
        strategy_scores=dict(parallel_analysis.get("strategies") or {}),
        strategy_matches=parallel_matches,
        scenario_analysis=dict(parallel_analysis.get("scenario_analysis") or {}),
        analysis_ranking=parallel_analysis,
    )


def _prefilter_score(row: Mapping[str, Any]) -> float:
    """Cheap stage-1 score based only on already fetched market/fundamental data."""
    scanner = _f(row.get("scanner_score"), _f(row.get("score"), 50.0))
    momentum = _f(row.get("momentum_score"), _f(row.get("trend_score"), 50.0))
    liquidity = _f(row.get("liquidity_score"), 50.0)
    data_quality = _f(row.get("data_quality"), 50.0)
    risk = _f(row.get("risk_score"), 50.0)
    return round(_clamp(scanner * 0.35 + momentum * 0.25 + liquidity * 0.18 + data_quality * 0.17 + (100.0 - risk) * 0.05), 2)


def _mark_intelligence_not_searched(
    row: dict[str, Any],
    area: str,
    reason: str,
    *,
    reason_code: str,
    enabled: bool = True,
) -> None:
    """Record a reasoned non-search without changing evidence gate semantics."""
    from evidence_contract import normalize_search_payload

    key = f"{area}_intelligence"
    payload = dict(row.get(key) or {}) if isinstance(row.get(key), Mapping) else {}
    payload.update({
        "coverage": "NOT_SEARCHED",
        "status": "NOT_SEARCHED",
        "reason": reason,
    })
    payload = normalize_search_payload(
        payload,
        area=area,
        enabled=enabled,
        default_reason_code=reason_code,
        default_reason=reason,
    )
    row[key] = payload


def run_pipeline(rows: Sequence[Mapping[str, Any]], config: PipelineConfig | None = None, progress_callback: Any | None = None, force_refresh: bool = False) -> dict[str, Any]:
    """Run a staged scan: broad market data, extended analysis, then deep evidence.

    ``scan_limit`` controls stage 1, ``deep_analysis_count`` controls stage 2,
    ``evidence_analysis_count`` controls the bounded evidence review in stage 3,
    and ``proposal_count`` controls how many final proposals are presented.
    """
    cfg = (config or PipelineConfig()).normalized()
    strict_source_refresh = os.getenv("STRICT_INTELLIGENCE_SOURCE_REFRESH", "0").strip().lower() in {"1", "true", "yes", "on"}
    intelligence_force_refresh = bool(force_refresh and strict_source_refresh)
    if progress_callback:
        progress_callback({"phase": "PREPARE", "completed": 0, "total": max(1, min(len(rows), cfg.scan_limit)), "message": "Trinn 1/3: forbereder rask markedsskanning"})

    def _enrich_progress(done: int, total: int, ticker: str) -> None:
        if progress_callback:
            progress_callback({"phase": "MARKET_DATA", "completed": done, "total": total, "ticker": ticker, "message": f"Trinn 1/3: henter markedsdata {done}/{total}: {ticker}"})

    prepared_rows = _prepare_candidate_rows(rows, cfg, progress_callback=_enrich_progress, force_refresh=force_refresh)
    for row in prepared_rows:
        row["mission_id"] = cfg.mission_id
        row["configuration_version"] = cfg.configuration_version

    candidate_errors: list[dict[str, Any]] = []
    sanitized_rows: list[dict[str, Any]] = []
    for row in prepared_rows:
        clean, missing = _sanitize_numeric_fields(row)
        if missing:
            clean["loader_diagnostics"] = {"missing_or_invalid_numeric_fields": missing}
        clean["stage1_prefilter_score"] = _prefilter_score(clean)
        clean["analysis_stage"] = "FAST_SCAN"
        sanitized_rows.append(clean)

    # Stage 1 ends here. Only the strongest rows proceed to extended analysis.
    sanitized_rows.sort(key=lambda row: (_f(row.get("stage1_prefilter_score")), _f(row.get("scanner_score"))), reverse=True)
    from universe_coverage import select_sector_balanced_rows
    extended_source_rows, sector_selection = select_sector_balanced_rows(sanitized_rows, cfg.deep_analysis_count)
    extended_tickers = {str(row.get("ticker") or "").upper() for row in extended_source_rows}
    screened_out_rows = [row for row in sanitized_rows if str(row.get("ticker") or "").upper() not in extended_tickers]
    for row in extended_source_rows:
        row["analysis_stage"] = "EXTENDED_ANALYSIS"

    if progress_callback:
        progress_callback({
            "phase": "EXTENDED_ANALYSIS", "completed": 0, "total": max(1, len(extended_source_rows)),
            "message": f"Trinn 2/3: utvidet analyse av {len(extended_source_rows)} kandidater; {len(screened_out_rows)} avsluttet etter rask skanning",
        })

    # Portfolio fit is local and relatively cheap, but only useful for stage-2 rows.
    if cfg.use_portfolio_fit and extended_source_rows:
        from advanced_investment_intelligence import calculate_portfolio_fit
        for row in extended_source_rows:
            ticker = str(row.get("ticker") or "")
            try:
                fit, trace = calculate_portfolio_fit(row, extended_source_rows)
                row["portfolio_fit_score"] = fit
                row["portfolio_fit_trace"] = trace
            except Exception as exc:
                row["portfolio_fit_score"] = 50.0
                row["portfolio_fit_trace"] = {"status": "FALLBACK", "error": str(exc)}
                candidate_errors.append({"ticker": ticker, "stage": "PORTFOLIO_FIT", "error": str(exc)})

    preliminary: list[CandidateAssessment] = []
    source_by_ticker: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(extended_source_rows, start=1):
        ticker = str(row.get("ticker") or "")
        source_by_ticker[ticker.upper()] = row
        try:
            preliminary.append(score_candidate(row, cfg))
        except Exception as exc:
            candidate_errors.append({
                "ticker": ticker, "stage": "PRELIMINARY_SCORING", "error": str(exc),
                "missing_or_invalid_numeric_fields": list(row.get("numeric_fields_missing_or_invalid") or []),
            })
        if progress_callback:
            progress_callback({"phase": "EXTENDED_ANALYSIS", "completed": idx, "total": max(1, len(extended_source_rows)), "ticker": ticker, "message": f"Trinn 2/3: beregner utvidet score {idx}/{len(extended_source_rows)}"})

    preliminary.sort(key=lambda item: (item.investment_score, item.scanner_score), reverse=True)
    # RC16: evidence collection follows the deep-analysis set (bounded by the
    # explicit evidence limit), not only the smaller presentation count.  This
    # prevents high-scoring candidates from being rejected merely because no
    # evidence search was started for their rank.
    evidence_order = [item.ticker.upper() for item in preliminary[: cfg.evidence_analysis_count]]
    evidence_tickers = set(evidence_order)
    # A data quarantine may block a trading decision, but must not silently
    # suppress the very evidence collection that can explain or clear it.
    # Keep the bounded rank/budget guard, and attempt evidence for every
    # selected candidate.  Decision gating remains unchanged.
    evidence_rows = [source_by_ticker[ticker] for ticker in evidence_order if ticker in source_by_ticker]
    for row in evidence_rows:
        row["analysis_stage"] = "EVIDENCE_CONTROLLED"
        if bool(row.get("analysis_quarantine")):
            row["evidence_quarantine_override"] = True
            row["evidence_refresh_reason"] = "TOP_RANKED_MINIMUM"
        # Only this bounded top-ranked set may spend the per-report NewsAPI
        # budget. Other consumers retain the conservative fallback policy.
        row["newsapi_priority"] = True
        row["evidence_priority"] = True
        row["evidence_budget"] = {"max_source_areas": 2, "candidate_rank_budget": cfg.evidence_analysis_count, "strict_refresh": intelligence_force_refresh}
        if not cfg.use_insider_intelligence:
            _mark_intelligence_not_searched(
                row, "insider",
                "Innsiderevidens er deaktivert i denne kjøringskonfigurasjonen.",
                reason_code="MODULE_DISABLED", enabled=False,
            )
        if not cfg.use_news_intelligence:
            _mark_intelligence_not_searched(
                row, "news",
                "Nyhetsevidens er deaktivert i denne kjøringskonfigurasjonen.",
                reason_code="MODULE_DISABLED", enabled=False,
            )
    for row in extended_source_rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker not in evidence_tickers:
            reason = "Ikke prioritert til full evidenskontroll etter rask og utvidet rangering; programmet vurderer kandidaten på nytt senere."
            reason_code = "RANK_LIMIT"
            if cfg.use_insider_intelligence:
                _mark_intelligence_not_searched(row, "insider", reason, reason_code=reason_code)
            else:
                _mark_intelligence_not_searched(
                    row, "insider",
                    "Innsiderevidens er deaktivert i denne kjøringskonfigurasjonen.",
                    reason_code="MODULE_DISABLED", enabled=False,
                )
            if cfg.use_news_intelligence:
                _mark_intelligence_not_searched(row, "news", reason, reason_code=reason_code)
            else:
                _mark_intelligence_not_searched(
                    row, "news",
                    "Nyhetsevidens er deaktivert i denne kjøringskonfigurasjonen.",
                    reason_code="MODULE_DISABLED", enabled=False,
                )

    if progress_callback:
        progress_callback({
            "phase": "EVIDENCE", "completed": 0, "total": max(1, len(evidence_rows)),
            "message": f"Trinn 3/3: grundig evidenskontroll av {len(evidence_rows)} prioriterte kandidater",
        })

    enriched_by_ticker: dict[str, dict[str, Any]] = {str(row.get("ticker") or "").upper(): row for row in evidence_rows}
    if cfg.use_insider_intelligence and evidence_rows:
        from insider_intelligence import enrich_rows as enrich_insider_rows
        evidence_rows = enrich_insider_rows(
            evidence_rows, force_refresh=intelligence_force_refresh,
            progress_callback=(lambda done, total, ticker: progress_callback({"phase": "INSIDER", "completed": done, "total": total, "ticker": ticker, "message": f"Trinn 3/3: henter insiderdata {done}/{total}: {ticker}"})) if progress_callback else None,
        )
    if cfg.use_news_intelligence and evidence_rows:
        from news_intelligence import enrich_rows as enrich_news_rows
        evidence_rows = enrich_news_rows(
            evidence_rows, force_refresh=intelligence_force_refresh,
            progress_callback=(lambda done, total, ticker: progress_callback({"phase": "NEWS", "completed": done, "total": total, "ticker": ticker, "message": f"Trinn 3/3: analyserer nyheter {done}/{total}: {ticker}"})) if progress_callback else None,
        )
    enriched_by_ticker = {str(row.get("ticker") or "").upper(): row for row in evidence_rows}

    def _evidence_area_completed(row: Mapping[str, Any], area: str, enabled: bool) -> bool:
        if not enabled:
            return True
        payload = row.get(f"{area}_intelligence") if isinstance(row.get(f"{area}_intelligence"), Mapping) else {}
        status = str(payload.get("coverage") or payload.get("status") or "NOT_SEARCHED").upper()
        terminal = {
            "AVAILABLE", "CHECKED_NO_EVENTS", "VERIFIED_FACTS_FOUND", "VERIFIED_FACTS_NONE",
            "DISCOVERY_ONLY", "NOT_CONFIGURED", "NOT_SUPPORTED", "SOURCE_ERROR", "ERROR",
            "PARTIAL_SOURCE_FAILURE", "RATE_LIMITED", "DAILY_QUOTA_EXCEEDED",
        }
        attempted = any(
            isinstance(item, Mapping) and bool(item.get("attempted"))
            for item in (payload.get("search_log") or [])
        )
        return attempted or status in terminal

    stage3_completed_tickers: set[str] = set()
    evidence_diagnostics: list[dict[str, Any]] = []
    for row in evidence_rows:
        ticker_key = str(row.get("ticker") or "").upper()
        complete = (
            _evidence_area_completed(row, "insider", cfg.use_insider_intelligence)
            and _evidence_area_completed(row, "news", cfg.use_news_intelligence)
        )
        row["evidence_control_completed"] = complete
        if complete and ticker_key:
            stage3_completed_tickers.add(ticker_key)
        news_payload = row.get("news_intelligence") if isinstance(row.get("news_intelligence"), Mapping) else {}
        insider_payload = row.get("insider_intelligence") if isinstance(row.get("insider_intelligence"), Mapping) else {}
        evidence_diagnostics.append({
            "ticker": ticker_key,
            "rank_selected": evidence_order.index(ticker_key) + 1 if ticker_key in evidence_order else None,
            "completed": complete,
            "news_status": str(news_payload.get("coverage") or news_payload.get("status") or "NOT_SEARCHED").upper(),
            "insider_status": str(insider_payload.get("coverage") or insider_payload.get("status") or "NOT_SEARCHED").upper(),
            "news_attempted": any(isinstance(item, Mapping) and bool(item.get("attempted")) for item in news_payload.get("search_log") or []),
            "insider_attempted": any(isinstance(item, Mapping) and bool(item.get("attempted")) for item in insider_payload.get("search_log") or []),
            "quarantine_override": bool(row.get("evidence_quarantine_override")),
        })

    final_source_rows: list[dict[str, Any]] = []
    for row in extended_source_rows:
        ticker = str(row.get("ticker") or "").upper()
        final_source_rows.append(enriched_by_ticker.get(ticker, row))

    assessments: list[CandidateAssessment] = []
    for idx, row in enumerate(final_source_rows, start=1):
        ticker = str(row.get("ticker") or "")
        try:
            assessment = score_candidate(row, cfg)
            assessment.raw["analysis_stage"] = str(row.get("analysis_stage") or "EXTENDED_ANALYSIS")
            assessment.raw["stage1_prefilter_score"] = row.get("stage1_prefilter_score")
            assessment.raw["evidence_budget"] = row.get("evidence_budget") or {}
            assessments.append(assessment)
        except Exception as exc:
            candidate_errors.append({
                "ticker": ticker, "stage": "FINAL_SCORING", "error": str(exc),
                "missing_or_invalid_numeric_fields": list(row.get("numeric_fields_missing_or_invalid") or []),
            })
        if progress_callback:
            progress_callback({"phase": "SCORING", "completed": idx, "total": max(1, len(final_source_rows)), "ticker": ticker, "message": f"Fullfører score {idx}/{len(final_source_rows)}"})

    assessments.sort(key=lambda item: (item.investment_score, item.scanner_score), reverse=True)
    for idx, item in enumerate(assessments, start=1):
        item.rank = idx
    eligible = [item for item in assessments if item.status in {STATUS_RECOMMENDED, STATUS_MANUAL, STATUS_WATCH} and item.ticker.upper() in evidence_tickers]
    proposals = eligible[: cfg.proposal_count]

    previous_run = _read_json(LATEST_RUN_PATH, {})
    previous_by_ticker = {str(x.get("ticker") or "").upper(): x for x in (previous_run.get("candidates") or [])}
    for item in assessments:
        previous = previous_by_ticker.get(item.ticker.upper())
        if not previous:
            item.raw["score_change_explanation"] = {"status": "NEW", "previous_score": None, "current_score": item.investment_score, "delta": 0.0, "drivers": []}
            continue
        previous_formula = ((previous.get("raw") or {}).get("score_formula") or {})
        previous_parts = previous_formula.get("parts") or {}
        current_parts = (item.raw.get("score_formula") or {}).get("parts") or {}
        previous_weights = previous_formula.get("weights") or {}
        current_weights = (item.raw.get("score_formula") or {}).get("weights") or {}
        drivers = []
        for key, current_value in current_parts.items():
            previous_value = _f(previous_parts.get(key), current_value)
            weight = _f(current_weights.get(key), _f(previous_weights.get(key), 0.0))
            contribution_delta = (float(current_value) - previous_value) * weight
            if abs(contribution_delta) >= 0.01:
                drivers.append({"component": key, "previous": round(previous_value, 2), "current": round(float(current_value), 2), "raw_delta": round(float(current_value) - previous_value, 2), "weighted_delta": round(contribution_delta, 2)})
        drivers.sort(key=lambda x: abs(float(x.get("weighted_delta", 0))), reverse=True)
        previous_score = _f(previous.get("investment_score"), item.investment_score)
        item.raw["score_change_explanation"] = {
            "status": "CHANGED" if abs(item.investment_score - previous_score) >= 0.01 else "UNCHANGED",
            "previous_score": round(previous_score, 2), "current_score": item.investment_score,
            "delta": round(item.investment_score - previous_score, 2), "drivers": drivers[:8],
        }

    run_id = datetime.now().strftime("IP-%Y%m%d-%H%M%S")
    from universe_coverage import build_detection_audit, build_selection_trace, build_universe_contract
    universe_contract = build_universe_contract(
        cfg.market_scope, sanitized_rows,
        advanced_tickers=sorted(extended_tickers), evidence_tickers=sorted(evidence_tickers),
    )
    selection_trace = build_selection_trace(sanitized_rows, sorted(extended_tickers), sorted(evidence_tickers))
    detection_audit = build_detection_audit(selection_trace, sanitized_rows)
    payload = {
        "version": VERSION,
        "run_id": run_id,
        "created_at": _now_iso(),
        "config": asdict(cfg),
        "market_expansion": expand_market_scope(cfg.market_scope),
        "all_markets": list(BASE_MARKET_SCOPES) if cfg.market_scope == FULL_MARKET_SCOPE_LABEL else [],
        "summary": {
            "scanned": len(sanitized_rows), "deep_analyzed": len(assessments), "proposals": len(proposals),
            "recommended": sum(1 for x in assessments if x.status == STATUS_RECOMMENDED),
            "rejected": sum(1 for x in assessments if x.status == STATUS_REJECTED),
            "stage1_scanned": len(sanitized_rows), "stage1_screened_out": len(screened_out_rows),
            "stage2_extended": len(assessments),
            "stage3_evidence_prioritized": len(evidence_rows),
            "stage3_evidence_controlled": len(stage3_completed_tickers),
        },
        "analysis_stages": {
            "stage1": {"label": "Rask markedsskanning", "input": len(sanitized_rows), "advanced": len(extended_source_rows)},
            "stage2": {"label": "Utvidet analyse", "input": len(extended_source_rows), "advanced": len(evidence_rows)},
            "stage3": {
                "label": "Grundig evidenskontroll", "input": len(evidence_rows),
                "prioritized": len(evidence_rows), "completed": len(stage3_completed_tickers),
                "completion_rule": "Faktisk kildeforsøk eller eksplisitt terminal kilde-/støttestatus for alle aktiverte evidensområder",
            },
        },
        "evidence_observability": {
            "selected": len(evidence_order),
            "attempted_or_terminal": len(stage3_completed_tickers),
            "coverage_pct": round(100.0 * len(stage3_completed_tickers) / max(1, len(evidence_order)), 1),
            "top3_complete": all(ticker in stage3_completed_tickers for ticker in evidence_order[:3]),
            "top3_tickers": evidence_order[:3],
            "candidates": evidence_diagnostics,
        },
        "universe_contract": universe_contract,
        "sector_selection": sector_selection,
        "selection_trace": selection_trace,
        "detection_audit": detection_audit,
        "candidates": [asdict(x) | {"analysis_stage": str(x.raw.get("analysis_stage") or "EXTENDED_ANALYSIS")} for x in assessments],
        "proposals": [asdict(x) | {"analysis_stage": str(x.raw.get("analysis_stage") or "EVIDENCE_CONTROLLED")} for x in proposals],
        "execution": "ANALYSE_ONLY_MANUAL_APPROVAL",
        "data_refresh": {"force_refresh": bool(force_refresh), "cache_ttl_seconds": 21600,
                         "intelligence_source_cache_respected": not intelligence_force_refresh,
                         "strict_intelligence_source_refresh": intelligence_force_refresh},
        "candidate_errors": candidate_errors,
        "loader_diagnostics": {
            "prepared_count": len(sanitized_rows), "scored_count": len(assessments), "skipped_count": len(candidate_errors),
            "analysis_quarantine_count": sum(bool(row.get("analysis_quarantine")) for row in extended_source_rows),
            "analysis_quarantine_effect": "Beslutningen blokkeres, men prioritert evidensinnhenting forsøkes innenfor eksisterende budsjett",
            "stage1_screened_out": len(screened_out_rows),
        },
    }
    if progress_callback:
        progress_callback({"phase": "PORTFOLIO_PROPOSAL", "completed": 1, "total": 1, "message": "Bygger teoretisk porteføljeforslag"})
    from advanced_investment_intelligence import build_portfolio_proposal
    payload["portfolio_proposal"] = build_portfolio_proposal(payload["candidates"])
    _write_json(LATEST_RUN_PATH, payload)
    _write_json(RUNS_DIR / f"{run_id}.json", payload)
    _write_json(PROPOSALS_DIR / f"{run_id}_proposals.json", payload["proposals"])
    return payload

def add_to_review_queue(candidate: Mapping[str, Any], note: str = "") -> dict[str, Any]:
    queue = _read_json(REVIEW_QUEUE_PATH, [])
    if not isinstance(queue, list):
        queue = []
    item = dict(candidate)
    item.update({"queue_status": "ÅPEN", "added_at": _now_iso(), "note": note, "execution": "MANUAL_ONLY"})
    cid = str(item.get("candidate_id") or "")
    queue = [x for x in queue if str(x.get("candidate_id") or "") != cid]
    queue.insert(0, item)
    _write_json(REVIEW_QUEUE_PATH, queue)
    return item


def load_review_queue() -> list[dict[str, Any]]:
    value = _read_json(REVIEW_QUEUE_PATH, [])
    return value if isinstance(value, list) else []


def _market_rows_from_tickers(tickers: Sequence[str], market: str, source: str) -> list[dict[str, Any]]:
    """Build lightweight candidate rows; live enrichment happens once in run_pipeline."""
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            continue
        rows.append({
            "ticker": symbol,
            "symbol": symbol,
            "name": symbol,
            "market": market,
            "source": source,
        })
    return rows


def _merge_candidate_rows(primary: Sequence[Mapping[str, Any]], fallback: Sequence[Mapping[str, Any]], market: str, limit: int) -> list[dict[str, Any]]:
    """Merge sources with deploy-safe built-ins first.

    Persisted Smart-Universe rows can contain legacy absolute Render paths.  A
    scheduled market scan must never depend on those paths, so canonical ticker
    rows from the packaged universe are authoritative and persisted enrichment
    is used only to fill remaining capacity.
    """
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    # USA previously failed because persisted rows referenced an obsolete
    # /opt/render path.  Prefer the packaged reserve there; preserve established
    # source ordering for every other market for full backwards compatibility.
    ordered = [*fallback, *primary] if market == "USA" else [*primary, *fallback]
    for raw in ordered:
        row = normalize_candidate_identity(raw, market)
        ticker = row.get("ticker", "")
        if not ticker or ticker in seen:
            continue
        if market != "Alle" and row.get("market") != market:
            continue
        row.setdefault("name", ticker)
        row.setdefault("source", "Market universe")
        merged.append(row)
        seen.add(ticker)
        if len(merged) >= int(limit):
            break
    return merged


def _load_candidate_rows_from_app(config: PipelineConfig, *, return_discovery: bool = False):
    """Load up to scan_limit unique candidates for one market.

    Smart Universe remains the preferred source, but it is augmented by the
    built-in liquid market universe whenever it returns fewer rows than the
    configured per-market scan size. This prevents a stale persisted Top-10
    result from silently limiting a 25/50-stock scheduled scan.
    """
    cfg = config.normalized()
    primary: list[dict[str, Any]] = []
    source_parts: list[str] = []

    try:
        from services.universe_service import get_universe_service
        service = get_universe_service()
        result = service.run_smart_universe({
            "mode": "Smart AI-utvalg",
            "scopes": [cfg.market_scope],
            "max_count": min(500, max(cfg.scan_limit, cfg.scan_limit * 3)),
            "max_risk": "Høy",
            "sectors": ["Alle sektorer"],
            "use_news": cfg.use_research,
            "use_signal_intelligence": True,
        })
        primary = _extract_rows(result)
        if primary:
            source_parts.append("Smart Universe Engine")
    except Exception:
        primary = []

    if not primary:
        try:
            from services.storage_service import get_storage_service
            storage = get_storage_service()
            for name in ("smart_universe_result.json", "latest_rankings_v148.json", "top_picks_result.json"):
                stored = _extract_rows(storage.read_json(name, default={}) or {})
                if stored:
                    primary = stored
                    source_parts.append(f"Lagret {name}")
                    break
        except Exception:
            pass

    fallback_rows: list[dict[str, Any]] = []
    try:
        from universe_engine import resolve_universe_tickers
        tickers = resolve_universe_tickers([cfg.market_scope], max_count=min(500, max(cfg.scan_limit, cfg.scan_limit * 4)))
        fallback_rows = _market_rows_from_tickers(tickers, cfg.market_scope, "Built-in liquid market universe")
        if fallback_rows:
            source_parts.append("Built-in market universe")
    except Exception:
        pass

    # Independent USA safety net.  It is deliberately imported directly from
    # the packaged module and therefore works without network, cwd or /opt paths.
    if cfg.market_scope == "USA" and not fallback_rows:
        from stocks import US_FALLBACK
        fallback_rows = _market_rows_from_tickers(US_FALLBACK[:cfg.scan_limit], "USA", "Packaged USA reserve")
        source_parts.append("Packaged USA reserve")

    primary, primary_rejected = filter_candidate_rows_for_market(primary, cfg.market_scope)
    fallback_rows, fallback_rejected = filter_candidate_rows_for_market(fallback_rows, cfg.market_scope)
    rejected_rows = [*primary_rejected, *fallback_rejected]
    if rejected_rows:
        source_parts.append(f"{len(rejected_rows)} ugyldige/kryssmarkeds-symboler filtrert")

    if cfg.full_universe_scan:
        rows = _merge_candidate_rows(primary, fallback_rows, cfg.market_scope, cfg.scan_limit)
        discovery = {
            "version": "CONTROLLED-FULL-UNIVERSE-v1",
            "market": cfg.market_scope,
            "selected": len(rows),
            "rotated_from_previous": False,
            "selection_rule": "Alle gyldige symboler i det konfigurerte universet; ingen rotasjon før grovskann.",
        }
    else:
        from autonomi_core.discovery_data.layer import select_discovery_candidates
        rows, discovery = select_discovery_candidates(
            primary, fallback_rows, market=cfg.market_scope, limit=cfg.scan_limit,
            mission_id=cfg.mission_id, configuration_version=cfg.configuration_version,
        )
    discovery = dict(discovery or {})
    discovery["symbol_filter"] = {
        "accepted_primary": len(primary),
        "accepted_fallback": len(fallback_rows),
        "rejected_count": len(rejected_rows),
        "rejected": rejected_rows[:50],
    }
    if rows:
        result = (rows, " + ".join(source_parts or ["Market universe"]) + " + Discovery Data Layer + yfinance enrichment")
        return (*result, discovery) if return_discovery else result
    result = ([], "Ingen kandidatkilde")
    return (*result, discovery) if return_discovery else result


def render_investment_pipeline() -> None:
    import pandas as pd
    import streamlit as st

    pipeline_tab, intelligence_tab, autonomous_tab = st.tabs(["🚀 Investment Pipeline", "⏰ Scheduled Intelligence & PDF", "🧠 Autonomous Portfolio"] )
    with intelligence_tab:
        try:
            from market_intelligence import render_market_intelligence
            render_market_intelligence()
        except Exception as exc:
            st.error(f"Scheduled Market Intelligence kunne ikke lastes: {exc}")
    with autonomous_tab:
        try:
            from autonomous_portfolio import render_autonomous_portfolio
            render_autonomous_portfolio()
        except Exception as exc:
            st.error(f"Autonomous Learning Portfolio kunne ikke lastes: {exc}")
    with pipeline_tab:
        st.markdown("#### 🚀 Orkestrering – Investment Pipeline")
        st.caption(
            "Skanner valgt marked, rangerer toppkandidater og kjører en kontrollert analyseflyt frem til investeringsforslag. "
            "Alternativet **Alle** betyr kjernemarkedene Norge, Sverige og USA. Full seksmarkedsskanning er et eget eksplisitt valg. Ingen handler utføres automatisk."
        )

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            market = st.selectbox("Markedsvalg", market_scope_options(include_aggregate=True), index=market_scope_options(True).index("Alle"), key="ip_market_v18686")
        with c2:
            scan_limit = st.number_input("Maks kandidater å skanne", 10, 500, 25, 5, key="ip_scan_limit_v18693")
        with c3:
            deep_count = st.number_input("Grundig analyse av topp", 1, 100, 20, 1, key="ip_deep_v18686")
        with c4:
            proposal_count = st.number_input("Presenter forslag", 1, 20, 5, 1, key="ip_proposals_v18686")

        x1, x2, x3, x4 = st.columns(4)
        use_research = x1.checkbox("AI Research", True, key="ip_research_v18686")
        use_backtest = x2.checkbox("Historisk validering", True, key="ip_backtest_v18686")
        use_portfolio = x3.checkbox("Portfolio Optimizer", True, key="ip_portfolio_v18686")
        use_learning = x4.checkbox("Learning Advisor-kontekst", True, key="ip_learning_v18686")

        cfg = PipelineConfig(
            market_scope=market, scan_limit=int(scan_limit), deep_analysis_count=int(deep_count),
            proposal_count=int(proposal_count), use_research=use_research, use_backtest=use_backtest,
            use_portfolio_fit=use_portfolio, use_learning_advisor=use_learning,
        ).normalized()

        force_refresh = st.checkbox("Tving full ny analyse (ignorer cache)", value=False, key="ip_force_refresh_v18692e", help="Henter nye data for alle kandidater. Brukes ved kontroll og feilsøking; kjøringen kan ta lengre tid.")
        if market == CORE_MARKET_SCOPE_LABEL:
            st.info("Valgte land: " + ", ".join(expand_market_scope(CORE_MARKET_SCOPE_LABEL)))

        if st.button("Kjør automatisk investeringspipeline", type="primary", width="stretch", key="ip_run_v18686"):
            with st.spinner("Skanner og rangerer kandidater..."):
                rows, source = _load_candidate_rows_from_app(cfg)
                if not rows:
                    st.error("Ingen kandidater ble funnet. Kjør Smart Universe/Market Scanner først, eller kontroller datakildene.")
                else:
                    payload = run_pipeline(rows, cfg, force_refresh=force_refresh)
                    payload["candidate_source"] = source
                    _write_json(LATEST_RUN_PATH, payload)
                    st.session_state["ip_latest_run_v18686"] = payload
                    st.success(f"Pipeline fullført fra {source}: {len(payload['proposals'])} forslag klare for manuell vurdering.")

        payload = st.session_state.get("ip_latest_run_v18686") or _read_json(LATEST_RUN_PATH, {})
        if not payload:
            st.info("Ingen pipeline-kjøring er lagret ennå.")
            return

        summary = payload.get("summary") or {}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Skannet", summary.get("scanned", 0))
        m2.metric("Grundig analysert", summary.get("deep_analyzed", 0))
        m3.metric("Anbefalt", summary.get("recommended", 0))
        m4.metric("Forslag", summary.get("proposals", 0))

        rows = payload.get("candidates") or []
        if rows:
            table = [{
                "Rang": r.get("rank"), "Ticker": r.get("ticker"), "Marked": r.get("market"),
                "Sektor": r.get("sector"), "Scanner": r.get("scanner_score"),
                "Investment Score": r.get("investment_score"), "Risiko": r.get("risk_score"),
                "Datakvalitet": r.get("data_quality"), "Insider": (r.get("raw") or {}).get("insider_score", 50), "Insidersignal": (r.get("raw") or {}).get("insider_signal", "INGEN DATA"), "Status": r.get("status"),
                "Strategi": r.get("strategy_match"), "Foreslått vekt %": r.get("proposed_position_pct"),
                "Parallelle treff": ", ".join(r.get("strategy_matches") or []),
            } for r in rows]
            st.markdown("##### Rangert kandidatliste")
            st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
            st.markdown("##### 🔎 Analysebevis per kandidat")
            selected_ticker = st.selectbox("Velg kandidat for sporbar analyse", [str(r.get("ticker")) for r in rows], key="ip_trace_ticker_v18692b")
            selected = next((r for r in rows if str(r.get("ticker")) == selected_ticker), {})
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Datainnhenting", selected.get("raw", {}).get("data_fetch_status", selected.get("data_fetch_status", "-")))
            t2.metric("Felt brukt", len(selected.get("data_fields_used") or []))
            t3.metric("Konfidens", selected.get("confidence_score", 0))
            t4.metric("Investment Score", selected.get("investment_score", 0))
            raw = selected.get("raw") or {}
            insider = raw.get("insider_intelligence") or {}
            st.markdown("###### 🕵️ Insider Intelligence")
            ins1, ins2, ins3, ins4 = st.columns(4)
            ins1.metric("Insider-score", raw.get("insider_score", 50))
            ins2.metric("Signal", raw.get("insider_signal", "INGEN DATA"))
            ins3.metric("Kjøp / salg", f"{insider.get('buy_count',0)} / {insider.get('sell_count',0)}")
            ins4.metric("Nettoverdi", insider.get("net_value", 0))
            if insider.get("evidence"):
                st.dataframe(pd.DataFrame(insider.get("evidence")), width="stretch", hide_index=True)
            else:
                st.caption(insider.get("reason") or "Ingen dokumenterte insidertransaksjoner i tilgjengelig datakilde.")
            if raw.get("data_fetch_error"):
                st.warning(str(raw.get("data_fetch_error")))
            cache_cols = st.columns(4)
            cache_cols[0].metric("Datakilde", raw.get("data_source") or raw.get("data_fetch_status") or "Ukjent")
            cache_cols[1].metric("Cache", "TREFF" if raw.get("cache_hit") else "LIVE")
            cache_cols[2].metric("Cache-alder", f"{float(raw.get('cache_age_minutes') or 0):.1f} min")
            cache_cols[3].metric("Beriket", raw.get("enriched_at") or "-")
            change = raw.get("score_change_explanation") or {}
            if change:
                st.markdown("###### Endring siden forrige analyse")
                d1, d2, d3 = st.columns(3)
                d1.metric("Forrige score", "-" if change.get("previous_score") is None else f"{float(change.get('previous_score')):.2f}")
                d2.metric("Ny score", f"{float(change.get('current_score') or selected.get('investment_score') or 0):.2f}")
                d3.metric("Endring", f"{float(change.get('delta') or 0):+.2f}")
                if change.get("drivers"):
                    st.dataframe(pd.DataFrame(change.get("drivers")), width="stretch", hide_index=True)
                elif change.get("status") == "UNCHANGED":
                    st.caption("Ingen målbar scoreendring. Kontroller cache-alder og datakilde over.")
                else:
                    st.caption("Ingen tidligere sammenlignbar analyse finnes for denne kandidaten.")
            trace = raw.get("analysis_trace") or []
            if trace:
                st.markdown("###### Datainnhenting")
                st.dataframe(pd.DataFrame(trace), width="stretch", hide_index=True)
            component_trace = raw.get("component_trace") or {}
            if component_trace:
                st.markdown("###### Beregning av delscorer")
                component_rows = []
                for key, item in component_trace.items():
                    if not isinstance(item, Mapping):
                        continue
                    component_rows.append({
                        "Komponent": item.get("component", key),
                        "Score": item.get("score"),
                        "Status": item.get("status", ""),
                        "Dekning": item.get("coverage", item.get("group_coverage", "")),
                        "Detaljer": item.get("note", ""),
                    })
                st.dataframe(pd.DataFrame(component_rows), width="stretch", hide_index=True)
                for key, item in component_trace.items():
                    inputs = item.get("inputs") if isinstance(item, Mapping) else None
                    if inputs:
                        with st.expander(f"Sporing: {item.get('component', key)}", expanded=False):
                            st.dataframe(pd.DataFrame(inputs), width="stretch", hide_index=True)
            portfolio_trace = raw.get("portfolio_fit_trace") or {}
            if portfolio_trace:
                with st.expander("Sporing: Porteføljetilpasning", expanded=False):
                    st.json(portfolio_trace)
            formula = raw.get("score_formula") or {}
            if formula:
                with st.expander("Sporing: Total Investment Score", expanded=True):
                    st.json(formula)
            if not trace and not component_trace:
                st.info("Ingen analysetrace er lagret for denne kandidaten.")

        st.markdown("##### Investeringsforslag")
        proposals = payload.get("proposals") or []
        if not proposals:
            st.warning("Ingen kandidater passerte kvalitetsportene i denne kjøringen.")
        for p in proposals:
            title = f"#{p.get('rank')} {p.get('ticker')} – {p.get('status')} – {p.get('investment_score')}/100"
            with st.expander(title, expanded=(p.get("rank") == 1)):
                a, b, c, d = st.columns(4)
                a.metric("AI Discovery", p.get("discovery_score"))
                b.metric("Fundamentaler", p.get("fundamental_score"))
                c.metric("Validering", p.get("validation_score"))
                d.metric("Porteføljetilpasning", p.get("portfolio_fit_score"))
                st.write(f"**Strategier:** {', '.join(p.get('strategy_matches') or []) or p.get('strategy_match')}  |  **Foreslått posisjon:** {p.get('proposed_position_pct')} %")
                st.write("**Positive drivere:** " + " ".join(p.get("positives") or []))
                st.write("**Risikoer:** " + " ".join(p.get("risks") or []))
                st.json(p.get("quality_gates") or {}, expanded=False)
                note = st.text_input("Notat", key=f"ip_note_{p.get('candidate_id')}")
                if st.button("Legg til i manuell vurderingskø", key=f"ip_queue_{p.get('candidate_id')}"):
                    add_to_review_queue(p, note)
                    st.success("Kandidaten er lagt i manuell vurderingskø. Ingen handel er utført.")

        with st.expander("Manuell vurderingskø", expanded=False):
            queue = load_review_queue()
            if queue:
                st.dataframe(pd.DataFrame(queue), width="stretch", hide_index=True)
            else:
                st.caption("Køen er tom.")

        st.download_button(
            "Last ned komplett pipeline-rapport (JSON)",
            data=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            file_name=f"investment_pipeline_{payload.get('run_id', 'latest')}.json",
            mime="application/json",
            width="stretch",
            key="ip_export_v18686",
        )
