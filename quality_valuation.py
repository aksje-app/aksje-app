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

def _sector_policy(raw: Mapping[str, Any]) -> str:
    """Route quality evidence to metrics that fit the business model."""
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
        "steel", "commodity", "tankers", "dry bulk", "offshore",
    )):
        return "CYCLICAL"
    return "STANDARD"


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
        "STANDARD": "Standard: kvalitet vurderes før pris; verdsettelse bruker normalisert EPS og eksplisitt/peer P/E.",
    }[policy]

    return {
        "ticker": ticker, "name": str(raw.get("name") or ticker)[:100],
        "country": str(raw.get("country") or "Ukjent")[:80], "industry": industry[:100],
        "currency": str(raw.get("currency") or "")[:8], "price": price,
        "sector_policy": policy, "review_reason_category": review_reason_category,
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
        "observed_at": now.isoformat(timespec="seconds"), "model_version": "quality_v1.2@1.2",
    }

def rank_results(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {name: [] for name in (*GROUPS, "Ufullstendig / krever vurdering")}
    for row in rows:
        grouped[str(row.get("group")) if row.get("group") in grouped else "Ufullstendig / krever vurdering"].append(dict(row))
    grouped[GROUPS[0]].sort(key=lambda x: ((x.get("fair_price_scenario") or 0) / max(x.get("price") or 1, .01), x.get("roce_pct") or 0), reverse=True)
    grouped[GROUPS[1]].sort(key=lambda x: (x.get("roce_pct") or 0, -(x.get("normalized_pe") or 999)), reverse=True)
    grouped[GROUPS[2]].sort(key=lambda x: ((x.get("price") or 999999) / max(x.get("fair_price_scenario") or 1, .01), -(x.get("roce_pct") or 0)))
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
            valuation_basis="Median normalisert P/E hos sammenlignbare aksjer i samme land/bransje/policy",
        )
        item["warnings"].append("Peer-scenario er en sammenligning, ikke kursmål; primærkilder må kontrolleres før varsling.")

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
