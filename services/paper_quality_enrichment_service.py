"""Paper snapshot enrichment using the same intelligence sources as Autonomy.

The service never changes the technical production score or decision. It only
adds immutable evidence to the candidate snapshot for read-only challengers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Mapping

from services.quality_evidence_normalizer import (
    coverage_summary,
    freshness_score,
    liquidity_score_from_turnover,
    normalize_score,
    source_consensus_score,
)

PAPER_QUALITY_ENRICHMENT_SERVICE_VERSION = "1.0"


def _enabled(name: str, default: bool = True) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def _average_volume(hist: Any) -> float | None:
    try:
        if hist is not None and "Volume" in hist:
            values = hist["Volume"].dropna().tail(60)
            if len(values):
                return float(values.mean())
    except Exception:
        pass
    return None


def _history_points(hist: Any) -> int:
    try:
        return int(len(hist)) if hist is not None else 0
    except Exception:
        return 0


def _history_timestamp(hist: Any) -> str:
    try:
        if hist is not None and len(hist.index):
            value = hist.index[-1]
            return value.isoformat() if hasattr(value, "isoformat") else str(value)
    except Exception:
        pass
    return ""


def _data_quality(item: Mapping[str, Any], *, captured_at: str) -> dict[str, Any]:
    hist = item.get("hist")
    points = _history_points(hist)
    completeness_keys = (
        "score", "price", "volatility", "max_drawdown", "market_cap",
        "profit_margin", "revenue_growth", "debt_to_equity", "trailing_pe", "forward_pe",
    )
    available = sum(1 for key in completeness_keys if item.get(key) not in (None, ""))
    completeness = available / len(completeness_keys) * 100.0
    history_score = min(100.0, points / 252.0 * 100.0)
    timestamp = str(item.get("data_timestamp") or item.get("price_timestamp") or _history_timestamp(hist))
    fresh = freshness_score(timestamp, captured_at=captured_at)
    fresh_value = float(fresh.get("value") or 40.0)
    score = history_score * 0.40 + completeness * 0.35 + fresh_value * 0.25
    return {
        "status": "AVAILABLE",
        "value": round(max(0.0, min(100.0, score)), 3),
        "raw_value": {
            "history_points": points,
            "available_fields": available,
            "expected_fields": len(completeness_keys),
            "freshness": fresh,
        },
        "source": "paper_local_market_data",
        "normalised_from": "history_completeness_freshness",
    }


def _coverage_available(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    coverage = str(payload.get("coverage") or payload.get("canonical_evidence_status") or "").upper()
    if coverage in {"AVAILABLE", "VERIFIED", "PARTIAL", "SUCCESS", "OK"}:
        return True
    return bool(payload.get("verified_fact_count") or payload.get("events") or payload.get("evidence"))


class PaperQualityEnrichmentService:
    def enrich(self, item: Mapping[str, Any], technical_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        row = dict(item or {})
        captured_at = datetime.now(timezone.utc).isoformat()
        errors: list[dict[str, str]] = []

        if _enabled("PAPER_QUALITY_FETCH_NEWS", True):
            try:
                from news_intelligence import enrich_rows as enrich_news_rows
                enriched = enrich_news_rows([row], force_refresh=False)
                if enriched:
                    row = dict(enriched[0])
            except Exception as exc:
                errors.append({"component": "news", "error": str(exc)[:500]})
        if _enabled("PAPER_QUALITY_FETCH_INSIDER", True):
            try:
                from insider_intelligence import enrich_rows as enrich_insider_rows
                enriched = enrich_insider_rows([row], force_refresh=False)
                if enriched:
                    row = dict(enriched[0])
            except Exception as exc:
                errors.append({"component": "insider", "error": str(exc)[:500]})

        price = row.get("price")
        if price in (None, ""):
            try:
                hist = row.get("hist")
                close = hist["Close"].dropna() if hist is not None and "Close" in hist else []
                price = float(close.iloc[-1]) if len(close) else None
            except Exception:
                price = None
        avg_volume = row.get("average_volume") or row.get("averageVolume") or _average_volume(row.get("hist"))

        data_quality = normalize_score(row.get("data_quality_score", row.get("data_quality")), source="paper_input_data_quality")
        if data_quality["status"] != "AVAILABLE":
            data_quality = _data_quality(row, captured_at=captured_at)
        liquidity = normalize_score(row.get("liquidity_score"), source="paper_input_liquidity_score")
        if liquidity["status"] != "AVAILABLE":
            liquidity = liquidity_score_from_turnover(average_volume=avg_volume, price=price)

        news = row.get("news_intelligence") if isinstance(row.get("news_intelligence"), Mapping) else {}
        insider = row.get("insider_intelligence") if isinstance(row.get("insider_intelligence"), Mapping) else {}
        # Price and fundamentals commonly come from the same market-data provider,
        # so they count as one source family rather than two independent sources.
        source_names = ["market_data"] if price not in (None, "") or any(
            row.get(key) not in (None, "") for key in ("market_cap", "profit_margin", "revenue_growth", "debt_to_equity")
        ) else []
        if _coverage_available(news):
            source_names.append("news")
        if _coverage_available(insider):
            source_names.append("insider")
        consensus_payload = row.get("source_consensus")
        if consensus_payload in (None, ""):
            consensus_payload = {
                "level": "STERK" if len(source_names) >= 3 else ("MODERAT" if len(source_names) >= 2 else "BEGRENSET"),
                "independent_sources": len(source_names),
                "primary_source_present": "market_data" in source_names,
                "sources": source_names,
            }
        source_consensus = source_consensus_score(consensus_payload, source="paper_enrichment_source_consensus")

        news_component = normalize_score(row.get("news_score"), source="autonomy_news_intelligence") if _coverage_available(news) else normalize_score(None, source="autonomy_news_intelligence")
        insider_component = normalize_score(row.get("insider_score"), source="autonomy_insider_intelligence") if _coverage_available(insider) else normalize_score(None, source="autonomy_insider_intelligence")
        analyst_component = normalize_score(row.get("analyst_score", row.get("recommendation_score")), source="analyst_data")
        regime_component = normalize_score(row.get("market_regime_score", row.get("sector_relative_strength")), source="market_regime")
        earnings_value = row.get("earnings_surprise")
        earnings_component = {
            "status": "AVAILABLE" if earnings_value not in (None, "") else "MISSING",
            "value": earnings_value if earnings_value not in (None, "") else None,
            "raw_value": earnings_value,
            "source": "earnings_data",
            "normalised_from": "percentage_surprise",
        }

        components = {
            "data_quality": data_quality,
            "liquidity": liquidity,
            "source_consensus": source_consensus,
            "news_score": news_component,
            "insider_score": insider_component,
            "analyst_score": analyst_component,
            "market_regime_score": regime_component,
            "earnings_surprise": earnings_component,
        }
        coverage = coverage_summary(components, minimum_components=2)
        row.update({
            "data_quality": data_quality.get("value"),
            "data_quality_score": data_quality.get("value"),
            "liquidity": liquidity.get("value"),
            "liquidity_score": liquidity.get("value"),
            "source_consensus": source_consensus.get("value"),
            "quality_evidence": components,
            "quality_coverage": coverage,
            "quality_enrichment": {
                "service_version": PAPER_QUALITY_ENRICHMENT_SERVICE_VERSION,
                "captured_at": captured_at,
                "production_score_unchanged": True,
                "production_decision_unchanged": True,
                "external_news_enabled": _enabled("PAPER_QUALITY_FETCH_NEWS", True),
                "external_insider_enabled": _enabled("PAPER_QUALITY_FETCH_INSIDER", True),
                "errors": errors,
            },
        })
        if news_component.get("value") is not None:
            row["news_score"] = news_component["value"]
        if insider_component.get("value") is not None:
            row["insider_score"] = insider_component["value"]
        return row


_default: PaperQualityEnrichmentService | None = None


def get_paper_quality_enrichment_service() -> PaperQualityEnrichmentService:
    global _default
    if _default is None:
        _default = PaperQualityEnrichmentService()
    return _default
