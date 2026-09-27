"""Observational quality and valuation screen; never places trades.

Missing financial evidence is a first-class result. Commodity proxies describe
market context, not a measured sensitivity of an individual company.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable, Mapping, Sequence
import math
import re
import resource
import time


MAX_SYMBOLS = 20
MAX_SECONDS = 180
GROUPS = ("Attraktivt priset kandidat", "Kvalitetsselskap", "Dyr kvalitet / følges")
PROXY_BY_INDUSTRY = {
    "oil": ("Brent", "Europeisk gass"),
    "gas": ("Europeisk gass", "Brent"),
    "alumin": ("Aluminium", "Alumina", "Kraft"),
    "copper": ("Kobber",),
    "gold": ("Gull",),
    "fertiliz": ("Gjødsel", "Naturgass"),
    "gjødsel": ("Gjødsel", "Naturgass"),
    "salmon": ("Laks", "Fôr"),
    "laks": ("Laks", "Fôr"),
    "airline": ("Flydrivstoff",),
    "shipping": ("Fraktrater", "Drivstoff"),
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _positive(value: Any) -> float | None:
    n = _number(value)
    return n if n is not None and n > 0 else None


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _safe_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,19}", ticker):
        return ""
    # This observation screen follows the shared market activation contract.
    # Unsupported suffixes must never silently be interpreted as US listings.
    from market_universe import market_activation_level
    suffix = ticker.rpartition(".")[2] if "." in ticker else ""
    market = {"OL": "Norge", "ST": "Sverige", "CO": "Danmark", "HE": "Finland", "": "USA",
              "A": "USA", "B": "USA"}.get(suffix)
    return ticker if market and market_activation_level(market) != "OFF" else ""


def relevant_prices(industry: str, *, verified_exposure: Mapping[str, Any] | None = None) -> list[str]:
    if verified_exposure:
        return [str(k) for k in verified_exposure if str(k).strip()][:5]
    text = str(industry or "").lower()
    matches = [names for word, names in PROXY_BY_INDUSTRY.items() if word in text]
    return list(dict.fromkeys(name for group in matches for name in group))[:5]

GRADE_COLORS = {
    5: "#0b6b3a",  # mørk grønn
    4: "#16a34a",  # grønn
    3: "#d97706",  # gul/amber
    2: "#ea580c",  # oransje
    1: "#dc2626",  # rød
}


def _sector_policy(raw: Mapping[str, Any]) -> str:
    """Route quality evidence to metrics that fit the business model.

    The policy deliberately avoids one universal ROCE/P-E template. Unknown
    sectors fall back to STANDARD, while structurally different businesses are
    routed before thresholds are applied.
    """
    text = " ".join((
        str(raw.get("sector") or ""),
        str(raw.get("industry") or ""),
        str(raw.get("name") or ""),
    )).lower()
    if bool(raw.get("is_financial")) or any(word in text for word in (
        "financial", "bank", "insurance", "forsik", "capital markets",
        "asset management", "broker", "investment banking",
    )):
        return "FINANCIAL"
    if any(word in text for word in (
        "real estate", "reit", "property", "eiendom",
    )):
        return "REAL_ESTATE"
    if any(word in text for word in (
        "shipping", "marine", "oil", "gas", "energy", "metals", "mining",
        "steel", "commodity", "tankers", "dry bulk", "offshore", "airline",
    )):
        return "CYCLICAL"
    if any(word in text for word in (
        "utilities", "electric utility", "regulated utility", "water utility",
        "telecom services", "integrated telecom", "wireless telecom",
        "railroad", "infrastructure",
    )):
        return "CAPITAL_INTENSIVE"
    return "STANDARD"


def _financial_subtype(raw: Mapping[str, Any]) -> str:
    text = " ".join((str(raw.get("sector") or ""), str(raw.get("industry") or ""), str(raw.get("name") or ""))).lower()
    if "insurance" in text or "forsik" in text:
        return "INSURANCE"
    if "bank" in text:
        return "BANK"
    return "FINANCIAL_MARKETS"


def _fallback_exchange(ticker: str) -> str:
    suffix = ticker.rpartition(".")[2] if "." in ticker else ""
    return {
        "OL": "Oslo Børs",
        "ST": "Nasdaq Stockholm",
        "CO": "Nasdaq Copenhagen",
        "HE": "Nasdaq Helsinki",
    }.get(suffix, "")


def _score_color(score: int) -> str:
    return GRADE_COLORS.get(max(1, min(5, int(score or 1))), GRADE_COLORS[1])


def _apply_valuation_context(item: dict[str, Any]) -> None:
    price = _positive(item.get("price"))
    fair = _positive(item.get("fair_price_scenario"))
    entry = item.get("entry_range_scenario") or []
    low = _positive(entry[0]) if len(entry) >= 1 else None
    high = _positive(entry[1]) if len(entry) >= 2 else None

    item["price_vs_scenario_pct"] = round((price / fair - 1) * 100, 1) if price and fair else None
    item["price_vs_entry_low_pct"] = round((price / low - 1) * 100, 1) if price and low else None
    item["price_vs_entry_high_pct"] = round((price / high - 1) * 100, 1) if price and high else None
    if not price or not fair:
        item["valuation_position"] = "IKKE_BEREGNET"
        item["valuation_position_text"] = "Scenarioavstand kan ikke beregnes med dokumentert grunnlag."
        item["valuation_position_color"] = "#64748b"
        return

    distance = float(item["price_vs_scenario_pct"])
    if low and high and price < low:
        item["valuation_position"] = "UNDER_ENTRY_RANGE"
        item["valuation_position_text"] = f"Dagens kurs er {abs(float(item['price_vs_entry_low_pct'])):.1f}% under nedre inngangsscenario."
        item["valuation_position_color"] = "#16a34a"
    elif low and high and low <= price <= high:
        item["valuation_position"] = "INSIDE_ENTRY_RANGE"
        item["valuation_position_text"] = "Dagens kurs ligger innenfor inngangsscenarioet."
        item["valuation_position_color"] = "#16a34a"
    elif distance <= 5:
        item["valuation_position"] = "NEAR_SCENARIO"
        item["valuation_position_text"] = f"Dagens kurs er {abs(distance):.1f}% {'under' if distance < 0 else 'over'} scenarioverdien."
        item["valuation_position_color"] = "#d97706"
    else:
        item["valuation_position"] = "ABOVE_SCENARIO"
        item["valuation_position_text"] = f"Dagens kurs er {distance:.1f}% over scenarioverdien."
        item["valuation_position_color"] = "#ea580c" if distance <= 20 else "#dc2626"


def ensure_valuation_context(item: dict[str, Any]) -> dict[str, Any]:
    """Backfill scenario-distance fields for persisted rows from older releases."""
    _apply_valuation_context(item)
    return item


def _apply_grade(item: dict[str, Any]) -> None:
    _apply_valuation_context(item)
    """Apply an explainable 1-5 quality/pricing grade without hiding evidence.

    Stars summarize the screen; they never replace the sector-specific method.
    Missing sector evidence caps the grade instead of being silently imputed.
    """
    policy = str(item.get("sector_policy") or "STANDARD")
    quality_state = str(item.get("quality_state") or "")
    roce = _number(item.get("roce_pct"))
    roe = _number(item.get("roe_pct"))

    if policy == "FINANCIAL":
        level = (roe or 0) / 100
        quality_score = 5 if level >= .20 else 4 if level >= .15 else 3 if level >= .10 else 2 if level >= .08 else 1
        trend = str(item.get("roe_trend") or "")
    elif policy == "CAPITAL_INTENSIVE":
        level = (roce or 0) / 100
        quality_score = 5 if level >= .12 else 4 if level >= .09 else 3 if level >= .07 else 2 if level >= .05 else 1
        trend = str(item.get("roce_trend") or "")
    elif policy == "CYCLICAL":
        level = (roce or 0) / 100
        quality_score = 5 if level >= .15 else 4 if level >= .10 else 3 if level >= .07 else 2 if level >= .05 else 1
        trend = str(item.get("roce_trend") or "")
    elif policy == "REAL_ESTATE":
        quality_score = 3 if item.get("evidence_ready") else 1
        trend = "IKKE_DOKUMENTERT"
    else:
        level = (roce or 0) / 100
        quality_score = 5 if level >= .20 else 4 if level >= .12 else 3 if level >= .09 else 2 if level >= .06 else 1
        trend = str(item.get("roce_trend") or "")

    if quality_state == "INSUFFICIENT":
        quality_score = min(quality_score, 2)
    elif quality_state in {"WEAK", "SECTOR_METRIC_REQUIRED"}:
        quality_score = min(quality_score, 2)
    elif quality_state == "QUALITY_WEAKENING":
        quality_score = min(quality_score, 4)

    trend_upper = trend.upper()
    trend_score = 5 if trend_upper in {"FORBEDRENDE", "IMPROVING"} else 3 if trend_upper in {"STABIL", "STABLE"} else 1 if trend_upper in {"SVEKKENDE", "WEAKENING"} else 2

    price = _positive(item.get("price"))
    fair = _positive(item.get("fair_price_scenario"))
    if price and fair:
        ratio = price / fair
        valuation_score = 5 if ratio <= .75 else 4 if ratio <= .90 else 3 if ratio <= 1.05 else 2 if ratio <= 1.20 else 1
    else:
        normalized_pe = _positive(item.get("normalized_pe"))
        reported_pe = _positive(item.get("reported_pe"))
        # Without a valid comparable/sector scenario, absolute P/E is not
        # rewarded as "cheap" across unrelated industries.
        valuation_score = 3 if normalized_pe else 1
        if normalized_pe and normalized_pe > 40:
            valuation_score = 2
        if normalized_pe and reported_pe and normalized_pe > reported_pe * 1.5:
            valuation_score = min(valuation_score, 2)
        if policy in {"CYCLICAL", "REAL_ESTATE"}:
            valuation_score = min(valuation_score, 2 if not fair else valuation_score)

    age = _number(item.get("financial_age_days"))
    eps_years = len(item.get("annual_eps_history") or [])
    return_years = len(item.get("roe_history") or []) if policy == "FINANCIAL" else len(item.get("roce_history_pct") or [])
    data_score = 1
    if price and age is not None and 0 <= age <= 480:
        data_score = 2
    if item.get("evidence_ready"):
        data_score = 3
    if item.get("evidence_ready") and eps_years >= 4 and return_years >= 4:
        data_score = 4
    if data_score >= 4 and age is not None and age <= 365 and not item.get("provider_partial"):
        data_score = 5

    cap = 5
    subtype = str(item.get("sector_subtype") or "")
    if policy == "FINANCIAL":
        # ROE alone cannot establish bank capital adequacy or insurer
        # underwriting/solvency. Keep the summary conservative until those
        # sector metrics are explicitly documented.
        sector_specific = bool(item.get("sector_specific_evidence"))
        if not sector_specific:
            data_score = min(data_score, 4)
            cap = min(cap, 4)
    if policy == "CYCLICAL" and not item.get("cycle_valuation_evidence"):
        cap = min(cap, 4)
    if policy == "REAL_ESTATE" and not item.get("sector_specific_evidence"):
        data_score = min(data_score, 2)
        cap = min(cap, 2)
    if quality_state == "INSUFFICIENT":
        cap = min(cap, 2)

    weighted = quality_score * .35 + valuation_score * .25 + trend_score * .20 + data_score * .20
    stars = max(1, min(cap, int(math.floor(weighted + .5))))
    # A 5-star headline must never contradict a 1-3/5 subscore. The grade
    # text promises simultaneously strong quality, valuation, trend and data.
    if stars >= 5 and min(quality_score, valuation_score, trend_score, data_score) < 4:
        stars = 4
    label = {5: "Svært sterk", 4: "Sterk", 3: "Middels", 2: "Svak", 1: "Svært svak"}[stars]

    weakest_name, weakest_score = min(
        (("kvalitet", quality_score), ("prising", valuation_score), ("trend", trend_score), ("datagrunnlag", data_score)),
        key=lambda pair: pair[1],
    )
    next_text = {
        "kvalitet": "For neste stjerne: sterkere og mer vedvarende sektorjustert kapitalavkastning.",
        "prising": "For neste stjerne: bedre dokumentert prisingsmargin mot relevante sammenlignbare selskaper.",
        "trend": "For neste stjerne: tydeligere stabilisering eller forbedring i kapitalavkastningen.",
        "datagrunnlag": "For neste stjerne: mer komplett og ferskt sektortilpasset datagrunnlag.",
    }[weakest_name]
    if stars >= 5:
        next_text = "5 stjerner krever at kvalitet, prising, trend og datagrunnlag samtidig forblir sterke."

    reasons: list[str] = []
    if trend_score == 5:
        reasons.append("kapitalavkastningen forbedres")
    elif trend_score == 3:
        reasons.append("kapitalavkastningen er stabil")
    if valuation_score >= 4:
        reasons.append("prisingen har tydelig margin mot scenario")
    if quality_score >= 4:
        reasons.append("sektorjustert kvalitet er sterk")
    if data_score >= 4:
        reasons.append("datagrunnlaget er godt dokumentert")
    if not reasons:
        reasons.append("flere nøkkelforhold krever fortsatt dokumentasjon")
    why_now = "Hvorfor nå: " + ", ".join(reasons[:3]) + "."

    item.update({
        "overall_stars": stars,
        "overall_grade_label": label,
        "overall_grade_color": _score_color(stars),
        "quality_score": quality_score,
        "quality_color": _score_color(quality_score),
        "valuation_score": valuation_score,
        "valuation_color": _score_color(valuation_score),
        "trend_score": trend_score,
        "trend_color": _score_color(trend_score),
        "data_score": data_score,
        "data_color": _score_color(data_score),
        "grade_confidence": "HØY" if data_score >= 4 else "MIDDELS" if data_score == 3 else "LAV",
        "why_now": why_now,
        "next_star_requirement": next_text,
        "grade_method": "1-5 stjerner: 35% sektorjustert kvalitet, 25% prising, 20% trend, 20% datagrunnlag; sektorbevis kan sette tak på graden.",
    })


def _effective_financial_date(raw: Mapping[str, Any]) -> datetime | None:
    direct = _date(raw.get("financial_date"))
    if direct:
        return direct
    for value in raw.get("fiscal_periods") or []:
        candidate = _date(value)
        if candidate:
            return candidate
    return None



def evaluate_company(raw: Mapping[str, Any], *, assumed_pe: float | None = None, as_of: datetime | None = None) -> dict[str, Any]:
    """Active Quality v1.2: sector-aware quality evidence first, valuation second."""
    now = as_of or datetime.now(timezone.utc)
    ticker = _safe_ticker(raw.get("ticker"))
    if not ticker:
        raise ValueError("Ugyldig ticker")
    policy = _sector_policy(raw)
    financial_subtype = _financial_subtype(raw) if policy == "FINANCIAL" else policy
    price = _positive(raw.get("price"))
    annual_eps = [n for n in (_number(x) for x in (raw.get("annual_eps") or [])) if n is not None][:10]
    reported_eps = _positive(raw.get("trailing_eps"))
    forward_eps = _positive(raw.get("forward_eps"))
    normalized_eps = median(annual_eps[:5]) if len(annual_eps) >= 3 and median(annual_eps[:5]) > 0 else None
    financial_date = _effective_financial_date(raw)
    financial_age = (now - financial_date).days if financial_date else None
    warnings: list[str] = list(raw.get("provider_warnings") or [])

    if financial_age is None or financial_age < 0 or financial_age > 480:
        warnings.append("Regnskapets dato mangler eller er for gammel til en verdsettelse.")
    if not normalized_eps:
        warnings.append("Mangler tre sammenlignbare årsresultater med positiv normalisert inntjening.")
    if price is None:
        warnings.append("Kurs mangler.")

    fcf = _number(raw.get("free_cash_flow"))
    fcf_history = [n for n in (_number(x) for x in (raw.get("free_cash_flow_history") or [])) if n is not None][:10]
    fcf_positive_ratio = (sum(1 for n in fcf_history[:5] if n > 0) / len(fcf_history[:5])) if fcf_history else None
    if policy not in {"FINANCIAL", "REAL_ESTATE"}:
        if fcf is None and not fcf_history:
            warnings.append("Fri kontantstrøm mangler.")
        elif fcf is not None and fcf <= 0:
            warnings.append("Siste fri kontantstrøm er ikke positiv.")
        if fcf_positive_ratio is not None and fcf_positive_ratio < 0.60:
            warnings.append("Fri kontantstrøm har vært ustabil over historikken.")

    latest_roce = _number(raw.get("roce"))
    roce_history = [n for n in (_number(x) for x in (raw.get("roce_history") or [])) if n is not None][:10]
    median_roce = median(roce_history[:5]) if len(roce_history) >= 3 else latest_roce
    roe_history = [n for n in (_number(x) for x in (raw.get("roe_history") or [])) if n is not None][:10]
    latest_roe = roe_history[0] if roe_history else None
    median_roe = median(roe_history[:5]) if len(roe_history) >= 3 else latest_roe

    roce_trend = "IKKE_DOKUMENTERT"
    if len(roce_history) >= 3:
        older = median(roce_history[1:min(5, len(roce_history))])
        delta = roce_history[0] - older
        roce_trend = "FORBEDRENDE" if delta >= .02 else "SVEKKENDE" if delta <= -.02 else "STABIL"
    roe_trend = "IKKE_DOKUMENTERT"
    if len(roe_history) >= 3:
        older = median(roe_history[1:min(5, len(roe_history))])
        delta = roe_history[0] - older
        roe_trend = "FORBEDRENDE" if delta >= .02 else "SVEKKENDE" if delta <= -.02 else "STABIL"

    if policy == "FINANCIAL":
        if len(roe_history) < 3:
            warnings.append("Finansselskap: minst tre år med ROE-historikk er ikke dokumentert.")
        if median_roe is None:
            warnings.append("Finansselskap: dokumentert ROE mangler; industriell ROCE brukes ikke som erstatning.")
        if financial_subtype == "BANK" and not raw.get("cet1_ratio") and not raw.get("capital_ratio"):
            warnings.append("Bank: CET1/kapitaldekning er ikke dokumentert; ROE alene gir ikke full sektorvurdering.")
        if financial_subtype == "INSURANCE" and not raw.get("combined_ratio") and not raw.get("solvency_ratio"):
            warnings.append("Forsikring: combined ratio/solvens er ikke dokumentert; ROE alene gir ikke full sektorvurdering.")
    elif policy == "REAL_ESTATE":
        ffo = _positive(raw.get("ffo_per_share") or raw.get("affo_per_share"))
        nav = _positive(raw.get("nav_per_share"))
        if not ffo and not nav:
            warnings.append("Eiendom: FFO/AFFO eller NAV mangler. Vanlig P/E alene er ikke nok for kvalitets-/prisvurdering.")
    else:
        if len(roce_history) < 3:
            warnings.append("Kapitalavkastning over minst tre regnskapsår er ikke dokumentert.")
        if median_roce is None:
            warnings.append("Dokumentert kapitalavkastning (ROCE/ROACE) mangler.")
        if roce_trend == "SVEKKENDE":
            warnings.append("Kapitalavkastningen er klart svakere enn nyere historikk.")
        elif roce_trend == "FORBEDRENDE":
            warnings.append("Kapitalavkastningen er klart forbedret mot nyere historikk.")

    pe_now = price / reported_eps if price and reported_eps else None
    pe_normal = price / normalized_eps if price and normalized_eps else None
    if pe_now and pe_normal and pe_normal > pe_now * 1.40:
        warnings.append("Lav P/E ved dagens kurs kan skyldes uvanlig høy inntjening; normalisert P/E er betydelig høyere.")

    industry = str(raw.get("industry") or "Ukjent")
    proxies = relevant_prices(industry, verified_exposure=raw.get("verified_exposure"))
    if proxies and not raw.get("verified_exposure"):
        warnings.append("Råvarekoblingen er bransjebasert. Faktisk prisfølsomhet er ikke verifisert.")

    multiple = _positive(assumed_pe)
    if multiple and not 4 <= multiple <= 40:
        raise ValueError("Valgt P/E-forutsetning må være mellom 4 og 40")

    date_ok = financial_age is not None and 0 <= financial_age <= 480
    fcf_supports = ((fcf_positive_ratio is not None and fcf_positive_ratio >= .60)
                    or (fcf_positive_ratio is None and fcf is not None and fcf > 0))

    review_reason_category = "QUALITY_WEAK"
    capital_return_method = ""
    if policy == "FINANCIAL":
        enough = bool(price and normalized_eps and len(roe_history) >= 3 and median_roe is not None and date_ok)
        improving = roe_trend == "FORBEDRENDE" and latest_roe is not None and latest_roe >= .12
        quality_ok = bool(enough and ((median_roe is not None and median_roe >= .10) or improving))
        quality_state = (
            "INSUFFICIENT" if not enough else
            "IMPROVING" if quality_ok and roe_trend == "FORBEDRENDE" else
            "QUALITY_WEAKENING" if quality_ok and roe_trend == "SVEKKENDE" else
            "QUALITY" if quality_ok else
            "WATCH" if median_roe is not None and median_roe >= .08 else "WEAK"
        )
        capital_return_method = "Finans/forsikring vurderes med flerårig ROE; industriell ROCE og vanlig FCF er ikke kvalitetsporter."
        review_reason_category = "MISSING_DATA" if not enough else "QUALITY_WEAK"
    elif policy == "REAL_ESTATE":
        ffo = _positive(raw.get("ffo_per_share") or raw.get("affo_per_share"))
        nav = _positive(raw.get("nav_per_share"))
        enough = bool(price and date_ok and (ffo or nav))
        quality_ok = False
        quality_state = "SECTOR_METRIC_REQUIRED" if not enough else "WATCH"
        capital_return_method = "Eiendom krever FFO/AFFO og/eller NAV samt balanse/rentedekning; P/E alene brukes ikke som kvalitetssignal."
        review_reason_category = "SECTOR_METRIC_REQUIRED"
    elif policy == "CYCLICAL":
        enough = bool(price and normalized_eps and median_roce is not None and len(roce_history) >= 3 and date_ok)
        latest_supports = latest_roce is not None and latest_roce >= .12
        persistent_supports = median_roce is not None and median_roce >= .09
        improving_supports = roce_trend == "FORBEDRENDE" and latest_supports
        cyclical_fcf = ((fcf_positive_ratio is not None and fcf_positive_ratio >= .50)
                        or (fcf_positive_ratio is None and fcf is not None and fcf > 0))
        quality_ok = bool(enough and cyclical_fcf and (persistent_supports or improving_supports))
        quality_state = (
            "INSUFFICIENT" if not enough else
            "IMPROVING" if quality_ok and roce_trend == "FORBEDRENDE" else
            "QUALITY_WEAKENING" if quality_ok and roce_trend == "SVEKKENDE" else
            "QUALITY" if quality_ok else
            "WATCH" if median_roce is not None and median_roce >= .06 else "WEAK"
        )
        capital_return_method = "Syklisk/råvare vurderes på flerårig ROCE, FCF gjennom syklus og trend; 12% er ikke en absolutt diskvalifikasjonsgrense."
        review_reason_category = "MISSING_DATA" if not enough else ("CYCLICAL_REVIEW" if not quality_ok else "")
    elif policy == "CAPITAL_INTENSIVE":
        enough = bool(price and normalized_eps and median_roce is not None and len(roce_history) >= 3 and date_ok)
        latest_supports = latest_roce is not None and latest_roce >= .10
        persistent_supports = median_roce is not None and median_roce >= .08
        improving_supports = roce_trend == "FORBEDRENDE" and latest_supports
        capital_fcf = ((fcf_positive_ratio is not None and fcf_positive_ratio >= .50)
                       or (fcf_positive_ratio is None and fcf is not None and fcf > 0))
        quality_ok = bool(enough and capital_fcf and (persistent_supports or improving_supports))
        quality_state = (
            "INSUFFICIENT" if not enough else
            "IMPROVING" if quality_ok and roce_trend == "FORBEDRENDE" else
            "QUALITY_WEAKENING" if quality_ok and roce_trend == "SVEKKENDE" else
            "QUALITY" if quality_ok else
            "WATCH" if median_roce is not None and median_roce >= .06 else "WEAK"
        )
        capital_return_method = "Kapitalintensiv infrastruktur/utility/telekom vurderes med lavere ROCE-referanse, flerårig FCF og trend; standard 12% brukes ikke som absolutt grense."
        review_reason_category = "MISSING_DATA" if not enough else "CAPITAL_INTENSIVE_REVIEW"
    else:
        enough = bool(price and normalized_eps and median_roce is not None and len(roce_history) >= 3 and date_ok)
        latest_supports = latest_roce is not None and latest_roce >= .12
        persistent_supports = median_roce is not None and median_roce >= .12
        improving_supports = roce_trend == "FORBEDRENDE" and latest_supports
        quality_ok = bool(enough and fcf_supports and (persistent_supports or improving_supports))
        quality_state = (
            "INSUFFICIENT" if not enough else
            "IMPROVING" if quality_ok and roce_trend == "FORBEDRENDE" else
            "QUALITY_WEAKENING" if quality_ok and roce_trend == "SVEKKENDE" else
            "QUALITY" if quality_ok else
            "WATCH" if median_roce is not None and median_roce >= .09 else "WEAK"
        )
        capital_return_method = "Standardmodellen bruker siste og median ROCE/ROACE, trend og flerårig FCF."
        review_reason_category = "MISSING_DATA" if not enough else "QUALITY_WEAK"

    if quality_state in {"QUALITY", "IMPROVING"}:
        review_reason_category = "QUALITY_CONFIRMED"
    elif quality_state == "QUALITY_WEAKENING":
        review_reason_category = "QUALITY_WEAKENING"
    elif quality_state == "INSUFFICIENT":
        review_reason_category = "MISSING_DATA"
    elif quality_state == "SECTOR_METRIC_REQUIRED":
        review_reason_category = "SECTOR_METRIC_REQUIRED"
    elif quality_state == "WEAK":
        review_reason_category = "QUALITY_WEAK"
    elif quality_state == "WATCH" and not review_reason_category:
        review_reason_category = "QUALITY_REVIEW"

    fair_price = round(normalized_eps * multiple, 2) if quality_ok and normalized_eps and multiple and policy != "REAL_ESTATE" else None
    earnings_dispersion = (median([abs(value - normalized_eps) for value in annual_eps[:5]]) / normalized_eps) if normalized_eps else 0
    entry_buffer = max(.03, min(.15, earnings_dispersion)) if normalized_eps else None

    if not quality_ok:
        group = "Ufullstendig / krever vurdering"
    elif fair_price is None:
        group = "Kvalitetsselskap"
    elif price <= fair_price * (1 - entry_buffer):
        group = GROUPS[0]
    elif price <= fair_price * 1.10:
        group = GROUPS[1]
    else:
        group = GROUPS[2]
    if enough and multiple is None and policy not in {"REAL_ESTATE", "CYCLICAL"}:
        warnings.append("Inngangsområde krever en begrunnet P/E-forutsetning; ingen kursgrense er beregnet.")
    if policy == "CYCLICAL" and multiple is None:
        warnings.append("Syklisk selskap: automatisk peer-P/E brukes ikke som eneste inngangsscenario; syklus/NAV må vurderes.")
    if policy == "REAL_ESTATE":
        warnings.append("Eiendom holdes til vurdering til sektorrelevante FFO/AFFO/NAV-data er dokumentert.")

    valuation_method = {
        "FINANCIAL": "Finans: normalisert EPS/P-E kan brukes som prisindikasjon, men kvalitet avgjøres med ROE-evidens.",
        "REAL_ESTATE": "Eiendom: P/E alene er utilstrekkelig; FFO/AFFO/NAV kreves før inngangsscenario.",
        "CYCLICAL": "Syklisk: normalisert EPS er støtteinformasjon; peer-P/E alene brukes ikke som inngangsscenario.",
        "CAPITAL_INTENSIVE": "Kapitalintensiv: kvalitet bruker bransjetilpasset ROCE/FCF; pris vurderes mot relevante peers når grunnlaget er tilstrekkelig.",
        "STANDARD": "Standard: kvalitet vurderes før pris; verdsettelse bruker normalisert EPS og eksplisitt/peer P/E.",
    }[policy]

    result = {
        "ticker": ticker, "name": str(raw.get("name") or ticker)[:100],
        "exchange": str(raw.get("exchange") or _fallback_exchange(ticker) or "Børs ikke dokumentert")[:100],
        "country": str(raw.get("country") or "Ukjent")[:80], "industry": industry[:100],
        "currency": str(raw.get("currency") or "")[:8], "price": price,
        "sector_policy": policy, "sector_subtype": financial_subtype, "review_reason_category": review_reason_category,
        "sector_specific_evidence": bool(
            (policy == "FINANCIAL" and (raw.get("cet1_ratio") or raw.get("capital_ratio") or raw.get("combined_ratio") or raw.get("solvency_ratio")))
            or (policy == "REAL_ESTATE" and (raw.get("ffo_per_share") or raw.get("affo_per_share")) and raw.get("nav_per_share"))
        ),
        "cycle_valuation_evidence": bool(raw.get("nav_per_share") or raw.get("cycle_nav") or raw.get("asset_value_per_share")),
        "roce_pct": round(median_roce * 100, 1) if median_roce is not None else None,
        "roce_latest_pct": round(latest_roce * 100, 1) if latest_roce is not None else None,
        "roce_history_pct": [round(x * 100, 2) for x in roce_history],
        "roce_trend": roce_trend,
        "roe_pct": round(median_roe * 100, 1) if median_roe is not None else None,
        "roe_latest_pct": round(latest_roe * 100, 1) if latest_roe is not None else None,
        "roe_trend": roe_trend, "quality_state": quality_state,
        "capital_return_method": capital_return_method,
        "reported_pe": round(pe_now, 2) if pe_now else None,
        "forward_pe": round(price / forward_eps, 2) if price and forward_eps else None,
        "normalized_pe": round(pe_normal, 2) if pe_normal else None,
        "normalized_eps": round(normalized_eps, 3) if normalized_eps else None,
        "annual_eps_history": annual_eps,
        "fiscal_periods": list(raw.get("fiscal_periods") or []),
        "operating_margin_history": list(raw.get("operating_margin_history") or []),
        "debt_history": list(raw.get("debt_history") or []),
        "equity_history": list(raw.get("equity_history") or []),
        "roe_history": roe_history,
        "sector": str(raw.get("sector") or "")[:100],
        "is_financial": policy == "FINANCIAL",
        "financial_date": financial_date.date().isoformat() if financial_date else None,
        "financial_age_days": financial_age, "free_cash_flow": fcf,
        "free_cash_flow_history": fcf_history, "fcf_positive_ratio": round(fcf_positive_ratio, 3) if fcf_positive_ratio is not None else None,
        "assumed_pe": multiple, "fair_price_scenario": fair_price,
        "entry_range_scenario": [round(fair_price * (1 - entry_buffer), 2), fair_price] if fair_price else None,
        "entry_buffer_pct": round(entry_buffer * 100, 1) if entry_buffer is not None else None,
        "group": group, "evidence_ready": bool(enough), "quality_evidence_ready": quality_ok, "warnings": warnings,
        "market_drivers": proxies, "verified_exposure": bool(raw.get("verified_exposure")),
        "valuation_method": valuation_method,
        "source": str(raw.get("source") or "Ukjent")[:140], "provider_partial": bool(raw.get("provider_partial")),
        "observed_at": now.isoformat(timespec="seconds"), "model_version": "quality_v1.3@1.3",
    }
    _apply_grade(result)
    return result

def rank_results(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {name: [] for name in (*GROUPS, "Ufullstendig / krever vurdering")}
    for row in rows:
        grouped[str(row.get("group")) if row.get("group") in grouped else "Ufullstendig / krever vurdering"].append(dict(row))
    grouped[GROUPS[0]].sort(key=lambda x: (x.get("overall_stars") or 0, (x.get("fair_price_scenario") or 0) / max(x.get("price") or 1, .01), x.get("roe_pct") or x.get("roce_pct") or 0), reverse=True)
    grouped[GROUPS[1]].sort(key=lambda x: (x.get("overall_stars") or 0, x.get("roe_pct") or x.get("roce_pct") or 0, -(x.get("normalized_pe") or 999)), reverse=True)
    grouped[GROUPS[2]].sort(key=lambda x: (-(x.get("overall_stars") or 0), (x.get("price") or 999999) / max(x.get("fair_price_scenario") or 1, .01), -(x.get("roe_pct") or x.get("roce_pct") or 0)))
    return grouped


def add_peer_context(results: list[dict[str, Any]]) -> None:
    """Use only 3+ comparable names and expose the exact peer basis."""
    for item in results:
        if not item.get("quality_evidence_ready") or item.get("assumed_pe") is not None:
            continue
        if item.get("sector_policy") in {"CYCLICAL", "REAL_ESTATE"}:
            item["warnings"].append("Automatisk peer-P/E er deaktivert for denne bransjepolicyen.")
            continue
        peer_rows = [other for other in results if other is not item
                     and other.get("industry", "").casefold() == item.get("industry", "").casefold()
                     and other.get("country", "Ukjent").casefold() == item.get("country", "Ukjent").casefold()
                     and other.get("sector_policy") == item.get("sector_policy")
                     and other.get("evidence_ready") and _positive(other.get("normalized_pe"))]
        if len(peer_rows) < 3:
            item["warnings"].append("For få sammenlignbare selskaper til å beregne bransjebasert inngangsscenario.")
            continue
        peers = [float(other["normalized_pe"]) for other in peer_rows]
        multiple = median(peers)
        eps = item.get("normalized_eps")
        fair = round(eps * multiple, 2)
        buffer = (item.get("entry_buffer_pct") or 3) / 100
        price = item.get("price") or 0
        item.update(
            assumed_pe=round(multiple, 2), fair_price_scenario=fair,
            entry_range_scenario=[round(fair * (1 - buffer), 2), fair],
            group=(GROUPS[0] if price <= fair * (1 - buffer) else GROUPS[1] if price <= fair * 1.10 else GROUPS[2]),
            peer_count=len(peers),
            peer_tickers=[str(other.get("ticker") or "") for other in peer_rows],
            peer_normalized_pe=[round(float(other["normalized_pe"]), 2) for other in peer_rows],
            peer_basis_quality="THIN" if len(peers) == 3 else "OK",
            valuation_basis="Median normalisert P/E hos sammenlignbare aksjer i samme land/bransje/policy",
        )
        item["warnings"].append("Peer-scenario er en sammenligning, ikke kursmål; primærkilder må kontrolleres før varsling.")
        if len(peers) == 3:
            item["warnings"].append("Peer-grunnlaget er tynt: scenarioet bygger på minimum tre sammenlignbare selskaper.")
        _apply_grade(item)

def run_screen(symbols: Sequence[str], provider: Callable[[str], Mapping[str, Any]], *, assumed_pe: float | None = None,
               progress: Callable[[dict[str, Any]], None] | None = None, deadline_seconds: int = MAX_SECONDS,
               memory_guard: Callable[[], bool] | None = None) -> dict[str, Any]:
    if any(not _safe_ticker(s) for s in symbols):
        raise ValueError("Ukjent eller deaktivert marked i tickerlisten")
    selected = list(dict.fromkeys(_safe_ticker(s) for s in symbols))
    if not selected or len(selected) > MAX_SYMBOLS:
        raise ValueError(f"Velg mellom 1 og {MAX_SYMBOLS} gyldige aksjer per kjøring")
    start = time.monotonic()
    before_cpu = resource.getrusage(resource.RUSAGE_SELF)
    before_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    results: list[dict[str, Any]] = []
    shadow_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    stop_reason = ""
    for index, ticker in enumerate(selected):
        if time.monotonic() - start >= max(1, min(deadline_seconds, MAX_SECONDS)):
            stop_reason = "Tidsgrense nådd"
            break
        if memory_guard and not memory_guard():
            stop_reason = "Ressursgrense nådd eller obligatorisk rapport startet"
            break
        if progress:
            progress({"stage": "Henter og vurderer", "ticker": ticker, "completed": index, "total": len(selected)})
        stage = "Vurdert"
        try:
            row = dict(provider(ticker) or {})
            row["ticker"] = ticker
            active = evaluate_company(row, assumed_pe=assumed_pe)
            results.append(active)
            try:
                from quality_model_v2 import evaluate_shadow
                shadow_rows.append(evaluate_shadow(row, active))
            except Exception:
                # Shadow must never make the active screen fail.
                pass
        except Exception as exc:
            stage = "Feil ved henting"
            # Provider messages may contain authenticated URLs or request data.
            failures.append({"ticker": ticker, "error": type(exc).__name__})
        if progress:
            progress({"stage": stage, "ticker": ticker, "completed": index + 1, "total": len(selected)})
    if assumed_pe is None:
        add_peer_context(results)
    # Peer valuation may change the active group after V2 was evaluated. Keep
    # the shadow comparison bound to the final active V1.1 result.
    final_active = {str(row.get("ticker")): row for row in results}
    for shadow in shadow_rows:
        active = final_active.get(str(shadow.get("ticker")))
        if active:
            shadow["active_v11_group"] = active.get("group")
            shadow["active_v11_quality_state"] = active.get("quality_state")
    after_cpu = resource.getrusage(resource.RUSAGE_SELF)
    after_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds = sum(after.ru_utime - before.ru_utime + after.ru_stime - before.ru_stime for before, after in
                      ((before_cpu, after_cpu), (before_children, after_children)))
    try:
        from quality_model_v2 import summarize_shadow
        quality_v2_shadow = summarize_shadow(shadow_rows)
    except Exception:
        quality_v2_shadow = {"shadow_only": True, "production_effect": False, "evaluated": 0, "rows": []}
    return {"state": "PARTIAL" if stop_reason or failures else "COMPLETED", "stop_reason": stop_reason,
            "selected": len(selected), "selected_symbols": selected, "assumed_pe": assumed_pe,
            "completed": len(results) + len(failures), "failures": failures,
            "elapsed_seconds": round(time.monotonic() - start, 2), "cpu_seconds": round(cpu_seconds, 2),
            "groups": rank_results(results), "quality_v2_shadow": quality_v2_shadow,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "shadow_only": True}
