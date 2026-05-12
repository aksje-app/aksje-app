"""
portfolio_mixed_analyzer.py

v18.5.44 Portfolio Analyzer: Stocks + Funds.

Pure helper layer for analysing a mixed portfolio with individual stocks,
funds and ETFs. It intentionally performs no network calls. The UI supplies
holdings from manual input, paper trading, Auto Test Lab and Fund / ETF results.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import math
import re

from app_version import get_app_version


TECH_STOCKS = {"AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AMD", "AVGO", "ORCL", "CRM", "ADBE", "NFLX"}
US_HINT_SUFFIXES = {"", ".US"}
NORWAY_SUFFIXES = (".OL",)
SWEDEN_SUFFIXES = (".ST",)
BROAD_US_FUNDS = {"SPY", "VOO", "VTI", "DIA", "SCHB", "ITOT"}
BROAD_GLOBAL_FUNDS = {"ACWI", "VT", "IUSQ.DE", "EUNL.DE", "VEA", "IEFA"}
TECH_FUNDS = {"QQQ", "XLK", "ARKK", "ARKW", "JEPQ"}
EMERGING_FUNDS = {"EEM", "IEMG", "VWO"}
ACTIVE_FUND_HINTS = {"AKTIV", "ACTIVE", "ARK", "JEP", "DYNF", "TCAF", "AVGV"}
FIXED_INCOME_ASSET_TYPES = {"Rente-/obligasjonsfond", "High yield-fond", "Pengemarkedsfond", "Kombinasjonsfond"}
FIXED_INCOME_SYMBOLS = {"BND", "AGG", "IEF", "TLT", "SHY", "BSV", "VCIT", "LQD", "SGOV", "BIL", "SHV", "ICSH", "MINT"}
HIGH_YIELD_SYMBOLS = {"HYG", "JNK", "ANGL", "HYLB", "USHY", "SJNK", "BKLN", "KRAFT_HIGH_YIELD_D"}


@dataclass
class MixedHolding:
    symbol: str
    asset_type: str = "Aksje"  # Aksje / Fond / ETF / Aktivt fond / Indeksfond / rente/high yield
    weight_pct: Optional[float] = None
    name: str = ""
    role: str = ""
    sector: str = ""
    geography: str = ""
    expense_ratio_pct: Optional[float] = None
    decision_quality: Optional[float] = None
    data_quality: Optional[float] = None
    source: str = "Manuell"
    metadata: Dict[str, Any] | None = None

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["metadata"] = dict(self.metadata or {})
        return data


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        out = float(str(value).replace("%", "").replace(",", ".").strip())
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _is_fund_type(asset_type: str) -> bool:
    return str(asset_type or "").strip() in {"Fond", "ETF", "Aktivt fond", "Indeksfond", *FIXED_INCOME_ASSET_TYPES}


def _infer_asset_type(symbol: str, requested_type: str = "") -> str:
    typ = str(requested_type or "").strip()
    if typ in {"Aksje", "Fond", "ETF", "Aktivt fond", "Indeksfond", *FIXED_INCOME_ASSET_TYPES}:
        return typ
    s = normalize_symbol(symbol)
    if s in HIGH_YIELD_SYMBOLS or "HIGHYIELD" in s or "HY" in s:
        return "High yield-fond"
    if s in FIXED_INCOME_SYMBOLS:
        return "Pengemarkedsfond" if s in {"SGOV", "BIL", "SHV", "ICSH", "MINT"} else "Rente-/obligasjonsfond"
    if s in TECH_FUNDS or s in BROAD_US_FUNDS or s in BROAD_GLOBAL_FUNDS or s in EMERGING_FUNDS or s in {"IWM", "EFA", "XLF", "XLV"}:
        return "ETF"
    if any(h in s for h in ACTIVE_FUND_HINTS):
        return "Aktivt fond"
    return "Aksje"


def _infer_geo(symbol: str, asset_type: str, metadata: Mapping[str, Any] | None = None) -> str:
    meta = dict(metadata or {})
    if meta.get("geography"):
        return str(meta.get("geography"))
    s = normalize_symbol(symbol)
    if s.endswith(NORWAY_SUFFIXES):
        return "Norge"
    if s.endswith(SWEDEN_SUFFIXES):
        return "Sverige"
    if asset_type in FIXED_INCOME_ASSET_TYPES:
        return "Rente/kreditt"
    if s in BROAD_GLOBAL_FUNDS or s in EMERGING_FUNDS:
        return "Global/Internasjonal"
    if s.endswith(".DE"):
        return "Europa/UCITS"
    return "USA/Global"


def _infer_sector(symbol: str, asset_type: str, metadata: Mapping[str, Any] | None = None) -> str:
    meta = dict(metadata or {})
    if meta.get("sector"):
        return str(meta.get("sector"))
    s = normalize_symbol(symbol)
    if s in TECH_STOCKS or s in TECH_FUNDS:
        return "Teknologi/vekst"
    if s in {"XLV"}:
        return "Helse"
    if s in {"XLF"}:
        return "Finans"
    if asset_type == "High yield-fond":
        return "High yield/kreditt"
    if asset_type in {"Rente-/obligasjonsfond", "Pengemarkedsfond"}:
        return "Rente/defensiv"
    if asset_type == "Kombinasjonsfond":
        return "Kombinasjon"
    if s in BROAD_US_FUNDS or s in BROAD_GLOBAL_FUNDS:
        return "Bredt marked"
    if s in EMERGING_FUNDS:
        return "Emerging markets"
    return "Ukjent"


def _infer_role(symbol: str, asset_type: str, explicit_role: str = "", metadata: Mapping[str, Any] | None = None) -> str:
    role = str(explicit_role or "").strip()
    if role:
        return role
    meta = dict(metadata or {})
    for key in ("recommended_role", "role"):
        if meta.get(key):
            return str(meta.get(key))
    s = normalize_symbol(symbol)
    if asset_type in {"Rente-/obligasjonsfond"}:
        return "Defensiv komponent"
    if asset_type == "Pengemarkedsfond":
        return "Likviditetsbuffer"
    if asset_type == "High yield-fond":
        return "Kredittsatellitt"
    if asset_type == "Kombinasjonsfond":
        return "Kombinasjon"
    if asset_type in {"Indeksfond", "ETF", "Fond"} and (s in BROAD_US_FUNDS or s in BROAD_GLOBAL_FUNDS):
        return "Grunnmur"
    if asset_type in {"ETF", "Aktivt fond", "Fond"}:
        return "Satellitt"
    return "Enkeltaksje"


def parse_portfolio_text(text: str, *, default_asset_type: str = "Aksje", source: str = "Manuell") -> List[Dict[str, Any]]:
    """Parse manual portfolio text.

    Accepted examples:
    ``AAPL``
    ``AAPL 12.5``
    ``AAPL: 12.5``
    ``VOO, 40, ETF``
    ``KLPGLOBAL 60 Indeksfond``
    """
    rows: List[Dict[str, Any]] = []
    for raw_line in str(text or "").replace(";", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Split comma/colon/whitespace while keeping dot suffixes in symbols.
        line = line.replace(":", " ").replace(",", " ")
        parts = [p for p in re.split(r"\s+", line) if p]
        if not parts:
            continue
        symbol = normalize_symbol(parts[0])
        if not symbol:
            continue
        weight = None
        typ = default_asset_type
        name_parts: List[str] = []
        for part in parts[1:]:
            value = _safe_float(part, None)
            if value is not None and weight is None:
                weight = value
                continue
            lower = part.lower()
            if lower in {"aksje", "stock"}:
                typ = "Aksje"
            elif lower in {"etf"}:
                typ = "ETF"
            elif lower in {"fond", "fund"}:
                typ = "Fond"
            elif lower in {"aktiv", "active", "aktivt"}:
                typ = "Aktivt fond"
            elif lower in {"indeks", "index", "indeksfond"}:
                typ = "Indeksfond"
            elif lower in {"rente", "obligasjon", "obligasjonsfond", "bond", "bonds"}:
                typ = "Rente-/obligasjonsfond"
            elif lower in {"highyield", "high-yield", "kreditt", "credit", "hy"}:
                typ = "High yield-fond"
            elif lower in {"pengemarked", "money", "market", "cash"}:
                typ = "Pengemarkedsfond"
            elif lower in {"kombinasjon", "balanced", "allocation"}:
                typ = "Kombinasjonsfond"
            else:
                name_parts.append(part)
        rows.append({
            "symbol": symbol,
            "asset_type": _infer_asset_type(symbol, typ),
            "weight_pct": weight,
            "name": " ".join(name_parts),
            "source": source,
        })
    return rows


def _holding_from_mapping(item: Mapping[str, Any], *, fallback_type: str = "Aksje", source: str = "") -> Optional[MixedHolding]:
    symbol = normalize_symbol(item.get("symbol") or item.get("ticker"))
    if not symbol:
        return None
    asset_type = _infer_asset_type(symbol, str(item.get("asset_type") or item.get("fund_type") or fallback_type))
    metadata = dict(item)
    role = _infer_role(symbol, asset_type, str(item.get("recommended_role") or item.get("role") or ""), metadata)
    return MixedHolding(
        symbol=symbol,
        asset_type=asset_type,
        weight_pct=_safe_float(item.get("weight_pct"), None),
        name=str(item.get("name") or item.get("longName") or item.get("shortName") or symbol),
        role=role,
        sector=_infer_sector(symbol, asset_type, metadata),
        geography=_infer_geo(symbol, asset_type, metadata),
        expense_ratio_pct=_safe_float(item.get("expense_ratio_pct"), None),
        decision_quality=_safe_float(item.get("decision_quality") or item.get("quality") or item.get("ai_score") or item.get("score"), None),
        data_quality=_safe_float(item.get("data_quality"), None),
        source=str(source or item.get("source") or "Ukjent"),
        metadata=metadata,
    )


def normalize_holdings(items: Sequence[Mapping[str, Any]], *, fallback_type: str = "Aksje", source: str = "") -> List[Dict[str, Any]]:
    holdings: List[MixedHolding] = []
    seen: Dict[Tuple[str, str], int] = {}
    for item in items or []:
        h = _holding_from_mapping(item, fallback_type=fallback_type, source=source)
        if h is None:
            continue
        key = (h.symbol, h.asset_type)
        if key in seen:
            idx = seen[key]
            prev = holdings[idx]
            if h.weight_pct is not None:
                prev.weight_pct = (prev.weight_pct or 0.0) + h.weight_pct
            continue
        seen[key] = len(holdings)
        holdings.append(h)

    explicit = [h for h in holdings if h.weight_pct is not None]
    missing = [h for h in holdings if h.weight_pct is None]
    explicit_sum = sum(max(0.0, float(h.weight_pct or 0.0)) for h in explicit)
    if holdings:
        if explicit and missing:
            remaining = max(0.0, 100.0 - explicit_sum)
            fill = remaining / len(missing) if missing else 0.0
            for h in missing:
                h.weight_pct = fill
        elif not explicit:
            equal = 100.0 / len(holdings)
            for h in holdings:
                h.weight_pct = equal
        # Normalize to 100.0.
        total = sum(max(0.0, float(h.weight_pct or 0.0)) for h in holdings)
        if total > 0:
            for h in holdings:
                h.weight_pct = round((max(0.0, float(h.weight_pct or 0.0)) / total) * 100.0, 2)
            drift = round(100.0 - sum(float(h.weight_pct or 0.0) for h in holdings), 2)
            holdings[0].weight_pct = round(float(holdings[0].weight_pct or 0.0) + drift, 2)
    return [h.as_dict() for h in holdings]


def _weighted_average(rows: Sequence[Mapping[str, Any]], field: str, *, only_funds: bool = False) -> Optional[float]:
    total_weight = 0.0
    value_sum = 0.0
    for row in rows or []:
        if only_funds and not _is_fund_type(str(row.get("asset_type") or "")):
            continue
        val = _safe_float(row.get(field), None)
        weight = _safe_float(row.get("weight_pct"), 0.0) or 0.0
        if val is None or weight <= 0:
            continue
        value_sum += val * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return round(value_sum / total_weight, 2)


def _sum_weight(rows: Sequence[Mapping[str, Any]], predicate) -> float:
    return round(sum(float(r.get("weight_pct") or 0.0) for r in rows or [] if predicate(r)), 2)


def _top_concentration(rows: Sequence[Mapping[str, Any]], n: int = 3) -> float:
    weights = sorted([float(r.get("weight_pct") or 0.0) for r in rows or []], reverse=True)
    return round(sum(weights[:n]), 2)


def _detect_overlap_risks(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    symbols = {str(r.get("symbol") or "").upper(): float(r.get("weight_pct") or 0.0) for r in rows or []}
    risks: List[Dict[str, Any]] = []
    tech_stock_weight = sum(symbols.get(s, 0.0) for s in TECH_STOCKS)
    qqq_weight = symbols.get("QQQ", 0.0) + symbols.get("XLK", 0.0) + symbols.get("ARKK", 0.0) + symbols.get("ARKW", 0.0)
    broad_us_weight = sum(symbols.get(s, 0.0) for s in BROAD_US_FUNDS)
    if tech_stock_weight >= 15 and qqq_weight >= 10:
        risks.append({
            "level": "Høy",
            "title": "Teknologi-overlapp",
            "message": "Store enkeltaksjer innen teknologi overlapper med QQQ/XLK/aktive teknologi-ETF-er.",
            "weight_pct": round(tech_stock_weight + qqq_weight, 2),
        })
    elif tech_stock_weight >= 15:
        risks.append({
            "level": "Middels",
            "title": "Enkeltaksje-konsentrasjon i teknologi",
            "message": "Flere store teknologiaksjer kan gjøre porteføljen mer sårbar for samme tema/regime.",
            "weight_pct": round(tech_stock_weight, 2),
        })
    if broad_us_weight >= 35 and tech_stock_weight >= 12:
        risks.append({
            "level": "Middels",
            "title": "USA indeks + samme toppaksjer",
            "message": "Brede USA-fond inneholder allerede mange av de største enkeltaksjene i porteføljen.",
            "weight_pct": round(broad_us_weight + tech_stock_weight, 2),
        })
    if len(rows or []) and _top_concentration(rows, 3) >= 55:
        risks.append({
            "level": "Høy",
            "title": "Høy topp-konsentrasjon",
            "message": "De tre største posisjonene utgjør over halvparten av porteføljen.",
            "weight_pct": _top_concentration(rows, 3),
        })
    return risks


def _profile_targets(profile: str) -> Dict[str, float]:
    p = str(profile or "Balansert")
    if p == "Lav risiko":
        return {"core_min": 65.0, "stock_max": 25.0, "sat_max": 25.0, "single_max": 8.0, "tech_max": 25.0}
    if p == "Vekst":
        return {"core_min": 45.0, "stock_max": 45.0, "sat_max": 40.0, "single_max": 12.0, "tech_max": 40.0}
    if p == "Lav kostnad":
        return {"core_min": 70.0, "stock_max": 25.0, "sat_max": 20.0, "single_max": 8.0, "tech_max": 30.0}
    if p == "Grunnmur":
        return {"core_min": 75.0, "stock_max": 20.0, "sat_max": 15.0, "single_max": 7.0, "tech_max": 25.0}
    return {"core_min": 55.0, "stock_max": 35.0, "sat_max": 30.0, "single_max": 10.0, "tech_max": 35.0}


def analyze_mixed_portfolio(
    holdings: Sequence[Mapping[str, Any]],
    *,
    profile: str = "Balansert",
    include_overlap: bool = True,
) -> Dict[str, Any]:
    rows = normalize_holdings(holdings)
    if not rows:
        return {
            "version": get_app_version(),
            "created_at": _now_iso(),
            "status": "empty",
            "portfolio_health": 0,
            "grade": "Ingen data",
            "holdings": [],
            "summary": {"text": "Ingen beholdninger å analysere."},
            "suggestions": ["Legg inn aksjer og/eller fond før analyse."],
            "warnings": ["Ingen data."],
        }

    targets = _profile_targets(profile)
    stock_pct = _sum_weight(rows, lambda r: str(r.get("asset_type")) == "Aksje")
    fund_pct = round(100.0 - stock_pct, 2)
    core_pct = _sum_weight(rows, lambda r: str(r.get("role")) == "Grunnmur")
    satellite_pct = _sum_weight(rows, lambda r: str(r.get("role")) == "Satellitt")
    active_pct = _sum_weight(rows, lambda r: str(r.get("asset_type")) == "Aktivt fond")
    fixed_income_pct = _sum_weight(rows, lambda r: str(r.get("asset_type")) in {"Rente-/obligasjonsfond", "Pengemarkedsfond"})
    high_yield_pct = _sum_weight(rows, lambda r: str(r.get("asset_type")) == "High yield-fond")
    tech_pct = _sum_weight(rows, lambda r: str(r.get("sector")) == "Teknologi/vekst")
    broad_pct = _sum_weight(rows, lambda r: str(r.get("sector")) == "Bredt marked")
    us_global_pct = _sum_weight(rows, lambda r: str(r.get("geography")) in {"USA/Global", "Global/Internasjonal"})
    top3_pct = _top_concentration(rows, 3)
    max_single = max([float(r.get("weight_pct") or 0.0) for r in rows] or [0.0])
    weighted_quality = _weighted_average(rows, "decision_quality")
    weighted_data_quality = _weighted_average(rows, "data_quality")
    weighted_expense = _weighted_average(rows, "expense_ratio_pct", only_funds=True)
    overlap = _detect_overlap_risks(rows) if include_overlap else []

    score = 72.0
    suggestions: List[str] = []
    strengths: List[str] = []
    warnings: List[str] = []

    if core_pct >= targets["core_min"]:
        score += 9
        strengths.append("god grunnmurandel")
    else:
        score -= min(18.0, (targets["core_min"] - core_pct) * 0.35)
        suggestions.append("Øk andelen brede indeksfond/ETF som grunnmur.")

    if stock_pct > targets["stock_max"]:
        score -= min(16.0, (stock_pct - targets["stock_max"]) * 0.35)
        suggestions.append("Vurder å redusere enkeltaksjeandel eller flytte noe til bredt indeksfond.")
    elif stock_pct <= targets["stock_max"]:
        strengths.append("enkeltaksjeandel er innenfor valgt profil")

    if max_single > targets["single_max"]:
        score -= min(14.0, (max_single - targets["single_max"]) * 0.8)
        warnings.append("én eller flere posisjoner er større enn anbefalt for profilen")

    if tech_pct > targets["tech_max"]:
        score -= min(14.0, (tech_pct - targets["tech_max"]) * 0.45)
        suggestions.append("Teknologi/vekst-eksponeringen er høy; vurder bredere eller mer defensiv diversifisering.")

    if weighted_expense is not None:
        if weighted_expense <= 0.35:
            score += 6
            strengths.append("lav vektet fondskostnad")
        elif weighted_expense >= 1.0:
            score -= 8
            suggestions.append("Vektet fondskostnad er høy; aktive fond bør bevise merverdi.")
    else:
        warnings.append("mangler kostnadsdata for fond/ETF-er")
        score -= 3

    if fixed_income_pct >= 10 and profile in {"Lav risiko", "Balansert"}:
        score += 3
        strengths.append("rente-/pengemarkedsandel gir defensiv ballast")
    if high_yield_pct > 20:
        score -= min(10.0, (high_yield_pct - 20.0) * 0.45)
        warnings.append("high yield-andelen er høy; dette er kredittrisiko, ikke kontant/rentebase")
        suggestions.append("Hold high yield som kredittsatellitt, ikke som hoveddelen av defensiv renteandel.")

    if weighted_quality is not None:
        score += (weighted_quality - 65.0) * 0.12
    if weighted_data_quality is not None and weighted_data_quality < 55:
        score -= 5
        warnings.append("datakvalitet er svak for flere posisjoner")

    for risk in overlap:
        score -= 7 if risk.get("level") == "Høy" else 4
        warnings.append(str(risk.get("title") or "Overlapp"))

    active_unproven = [r for r in rows if str(r.get("asset_type")) == "Aktivt fond" and str((r.get("metadata") or {}).get("active_evidence_status") or "") not in {"Godkjent", "Ikke relevant"}]
    if active_unproven:
        score -= min(12.0, active_pct * 0.35 + len(active_unproven) * 2)
        suggestions.append("Aktive fond uten godkjent merverdi bør holdes små eller flyttes til 'krever mer bevis'.")

    score = round(_clamp(score), 1)
    if score >= 78:
        grade = "Sterk"
    elif score >= 62:
        grade = "OK / forbedres"
    elif score >= 45:
        grade = "Svak / bør ryddes"
    else:
        grade = "Høy risiko"

    if not strengths:
        strengths.append("porteføljen kan analyseres, men trenger bedre struktur eller data")
    if not suggestions:
        suggestions.append("Porteføljen ser balansert ut mot valgt profil; følg med på kostnader, overlapp og event-risk.")

    by_asset_type: Dict[str, float] = {}
    by_role: Dict[str, float] = {}
    by_sector: Dict[str, float] = {}
    by_geo: Dict[str, float] = {}
    for row in rows:
        w = float(row.get("weight_pct") or 0.0)
        by_asset_type[str(row.get("asset_type") or "Ukjent")] = round(by_asset_type.get(str(row.get("asset_type") or "Ukjent"), 0.0) + w, 2)
        by_role[str(row.get("role") or "Ukjent")] = round(by_role.get(str(row.get("role") or "Ukjent"), 0.0) + w, 2)
        by_sector[str(row.get("sector") or "Ukjent")] = round(by_sector.get(str(row.get("sector") or "Ukjent"), 0.0) + w, 2)
        by_geo[str(row.get("geography") or "Ukjent")] = round(by_geo.get(str(row.get("geography") or "Ukjent"), 0.0) + w, 2)

    return {
        "version": get_app_version(),
        "created_at": _now_iso(),
        "status": "ok",
        "profile": profile,
        "portfolio_health": score,
        "grade": grade,
        "holdings": rows,
        "summary": {
            "text": f"Porteføljen består av {len(rows)} posisjoner: {stock_pct:.1f}% enkeltaksjer og {fund_pct:.1f}% fond/ETF.",
            "stock_pct": stock_pct,
            "fund_pct": fund_pct,
            "core_pct": core_pct,
            "satellite_pct": satellite_pct,
            "active_pct": active_pct,
            "fixed_income_pct": fixed_income_pct,
            "high_yield_pct": high_yield_pct,
            "tech_pct": tech_pct,
            "broad_market_pct": broad_pct,
            "us_global_pct": us_global_pct,
            "top3_pct": top3_pct,
            "max_single_position_pct": round(max_single, 2),
            "weighted_fund_expense_pct": weighted_expense,
            "weighted_quality": weighted_quality,
            "weighted_data_quality": weighted_data_quality,
        },
        "breakdown": {
            "asset_type": by_asset_type,
            "role": by_role,
            "sector": by_sector,
            "geography": by_geo,
        },
        "overlap_risks": overlap,
        "strengths": strengths[:8],
        "suggestions": suggestions[:8],
        "warnings": warnings[:8],
    }


def build_holdings_from_sources(
    *,
    stock_rows: Sequence[Mapping[str, Any]] | None = None,
    fund_rows: Sequence[Mapping[str, Any]] | None = None,
    manual_stock_text: str = "",
    manual_fund_text: str = "",
    default_stock_weight_pct: Optional[float] = None,
    default_fund_weight_pct: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Merge manual and result rows into a normalized mixed holding list."""
    raw: List[Dict[str, Any]] = []
    for row in stock_rows or []:
        d = dict(row)
        d.setdefault("asset_type", "Aksje")
        d.setdefault("source", "Aksjeresultat")
        if default_stock_weight_pct is not None and d.get("weight_pct") is None:
            d["weight_pct"] = default_stock_weight_pct
        raw.append(d)
    for row in fund_rows or []:
        d = dict(row)
        d.setdefault("asset_type", d.get("fund_type") or "Fond")
        d.setdefault("source", "Fondresultat")
        if default_fund_weight_pct is not None and d.get("weight_pct") is None:
            d["weight_pct"] = default_fund_weight_pct
        raw.append(d)
    raw.extend(parse_portfolio_text(manual_stock_text, default_asset_type="Aksje", source="Manuell aksje"))
    raw.extend(parse_portfolio_text(manual_fund_text, default_asset_type="ETF", source="Manuell fond/ETF"))
    return normalize_holdings(raw)


__all__ = [
    "MixedHolding",
    "parse_portfolio_text",
    "normalize_holdings",
    "build_holdings_from_sources",
    "analyze_mixed_portfolio",
]
