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
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,19}", ticker):
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


def evaluate_company(raw: Mapping[str, Any], *, assumed_pe: float | None = None, as_of: datetime | None = None) -> dict[str, Any]:
    """No precise entry price without dated earnings, cash flow and a justified multiple."""
    now = as_of or datetime.now(timezone.utc)
    ticker = _safe_ticker(raw.get("ticker"))
    if not ticker:
        raise ValueError("Ugyldig ticker")
    price = _positive(raw.get("price"))
    annual_eps = [_number(n) for n in (raw.get("annual_eps") or [])]
    annual_eps = [n for n in annual_eps if n is not None][:5]
    reported_eps = _positive(raw.get("trailing_eps"))
    forward_eps = _positive(raw.get("forward_eps"))
    normalized_eps = median(annual_eps) if len(annual_eps) >= 3 and median(annual_eps) > 0 else None
    financial_date = _date(raw.get("financial_date"))
    financial_age = (now - financial_date).days if financial_date else None
    warnings: list[str] = []
    if financial_age is None or financial_age < 0 or financial_age > 480:
        warnings.append("Regnskapets dato mangler eller er for gammel til en verdsettelse.")
    if not normalized_eps:
        warnings.append("Mangler tre sammenlignbare årsresultater med positiv normalisert inntjening.")
    if price is None:
        warnings.append("Kurs mangler.")
    fcf = _number(raw.get("free_cash_flow"))
    if fcf is None:
        warnings.append("Fri kontantstrøm mangler.")
    elif fcf <= 0:
        warnings.append("Fri kontantstrøm er ikke positiv.")
    roce = _number(raw.get("roce"))
    roce_history = [n for n in (_number(x) for x in (raw.get("roce_history") or [])) if n is not None]
    if len(roce_history) >= 3:
        roce = median(roce_history[:5])
    else:
        warnings.append("Kapitalavkastning over minst tre regnskapsår er ikke dokumentert.")
    if roce is None:
        warnings.append("Dokumentert kapitalavkastning (ROCE/ROACE) mangler.")
    if roce is not None and roce < 0.12:
        warnings.append("Kapitalavkastningen er under kvalitetsgrensen i denne screeningmodellen.")
    pe_now = price / reported_eps if price and reported_eps else None
    pe_normal = price / normalized_eps if price and normalized_eps else None
    if pe_now and pe_normal and pe_normal > pe_now * 1.40:
        warnings.append("Lav rapportert P/E kan skyldes uvanlig høy inntjening; normalisert P/E er betydelig høyere.")
    industry = str(raw.get("industry") or "Ukjent")
    proxies = relevant_prices(industry, verified_exposure=raw.get("verified_exposure"))
    if proxies and not raw.get("verified_exposure"):
        warnings.append("Råvarekoblingen er bransjebasert. Råvarepris og selskapets faktiske prisfølsomhet er ikke hentet eller verifisert i denne vurderingen.")
    multiple = _positive(assumed_pe)
    if multiple and not 4 <= multiple <= 40:
        raise ValueError("Valgt P/E-forutsetning må være mellom 4 og 40")
    enough = bool(price and normalized_eps and fcf is not None and roce is not None
                  and len(roce_history) >= 3 and financial_age is not None and 0 <= financial_age <= 480)
    # Explicit user scenario, not an algorithm's claim about intrinsic value.
    fair_price = round(normalized_eps * multiple, 2) if enough and multiple else None
    earnings_dispersion = (median([abs(value - normalized_eps) for value in annual_eps]) / normalized_eps) if normalized_eps else 0
    entry_buffer = max(.03, min(.15, earnings_dispersion)) if normalized_eps else None
    cash_quality = enough and fcf > 0 and roce >= 0.12
    if not cash_quality:
        group = "Ufullstendig / krever vurdering"
    elif fair_price is None:
        group = "Kvalitetsselskap"
    elif price <= fair_price * (1 - entry_buffer):
        group = GROUPS[0]
    elif price <= fair_price * 1.10:
        group = GROUPS[1]
    else:
        group = GROUPS[2]
    if enough and multiple is None:
        warnings.append("Inngangsområde krever en begrunnet P/E-forutsetning; ingen kursgrense er beregnet.")
    return {
        "ticker": ticker, "name": str(raw.get("name") or ticker)[:100],
        "country": str(raw.get("country") or "Ukjent")[:80], "industry": industry[:100],
        "currency": str(raw.get("currency") or "")[:8], "price": price,
        "roce_pct": round(roce * 100, 1) if roce is not None else None,
        "capital_return_method": "Median EBIT / (totale eiendeler - kortsiktig gjeld), inntil fem årsregnskap. Ikke selskapets justerte ROACE.",
        "reported_pe": round(pe_now, 2) if pe_now else None,
        "forward_pe": round(price / forward_eps, 2) if price and forward_eps else None,
        "normalized_pe": round(pe_normal, 2) if pe_normal else None,
        "normalized_eps": round(normalized_eps, 3) if normalized_eps else None,
        "financial_date": financial_date.date().isoformat() if financial_date else None,
        "financial_age_days": financial_age,
        "free_cash_flow": fcf, "assumed_pe": multiple, "fair_price_scenario": fair_price,
        "entry_range_scenario": [round(fair_price * (1 - entry_buffer), 2), fair_price] if fair_price else None,
        "entry_buffer_pct": round(entry_buffer * 100, 1) if entry_buffer is not None else None,
        "group": group, "evidence_ready": bool(enough), "warnings": warnings,
        "market_drivers": proxies, "verified_exposure": bool(raw.get("verified_exposure")),
        "valuation_method": "Illustrasjon med normalisert EPS og eksplisitt valgt P/E; ingen kjøpsordre.",
        "source": str(raw.get("source") or "Ukjent")[:140], "observed_at": now.isoformat(timespec="seconds"),
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
    """Use only 3+ other comparable, data-ready industry peers; no cross-sector fallback."""
    for item in results:
        if not item.get("evidence_ready") or item.get("assumed_pe") is not None:
            continue
        peers = [other["normalized_pe"] for other in results if other is not item
                 and other.get("industry", "").casefold() == item.get("industry", "").casefold()
                 and other.get("country", "Ukjent").casefold() == item.get("country", "Ukjent").casefold()
                 and other.get("evidence_ready") and _positive(other.get("normalized_pe"))]
        if len(peers) < 3:
            item["warnings"].append("For få sammenlignbare selskaper til å beregne bransjebasert inngangsscenario.")
            continue
        multiple = median(peers)
        eps = item.get("normalized_eps")
        fair = round(eps * multiple, 2)
        # Peer screening is observational, not a verified intrinsic value.
        buffer = (item.get("entry_buffer_pct") or 3) / 100
        price = item.get("price") or 0
        item.update(assumed_pe=round(multiple, 2), fair_price_scenario=fair,
                    entry_range_scenario=[round(fair * (1 - buffer), 2), fair],
                    group=(GROUPS[0] if price <= fair * (1 - buffer) else GROUPS[1] if price <= fair * 1.10 else GROUPS[2]),
                    peer_count=len(peers), valuation_basis="Median P/E hos sammenlignbare aksjer i samme kjøring")
        item["warnings"].append("Peer-scenario bygger på tredjeparts nøkkeltall; kontroll mot primærkilder kreves før varsling.")


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
            results.append(evaluate_company(row, assumed_pe=assumed_pe))
        except Exception as exc:
            stage = "Feil ved henting"
            # Provider messages may contain authenticated URLs or request data.
            failures.append({"ticker": ticker, "error": type(exc).__name__})
        if progress:
            progress({"stage": stage, "ticker": ticker, "completed": index + 1, "total": len(selected)})
    if assumed_pe is None:
        add_peer_context(results)
    after_cpu = resource.getrusage(resource.RUSAGE_SELF)
    after_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds = sum(after.ru_utime - before.ru_utime + after.ru_stime - before.ru_stime for before, after in
                      ((before_cpu, after_cpu), (before_children, after_children)))
    return {"state": "PARTIAL" if stop_reason or failures else "COMPLETED", "stop_reason": stop_reason,
            "selected": len(selected), "selected_symbols": selected, "assumed_pe": assumed_pe,
            "completed": len(results) + len(failures), "failures": failures,
            "elapsed_seconds": round(time.monotonic() - start, 2), "cpu_seconds": round(cpu_seconds, 2),
            "groups": rank_results(results),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "shadow_only": True}
