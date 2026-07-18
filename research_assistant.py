"""AI Research Assistant v18.6.84.

Read-only company research workspace. Data is collected from configured/public
providers, cached in the runtime area and rendered with explicit source and
freshness metadata. The module never places trades or changes strategy rules.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from storage_architecture import runtime_cache_path, runtime_data_path

RESEARCH_DATA_DIR = runtime_data_path("research")
RESEARCH_CACHE_DIR = runtime_cache_path("research")
LATEST_REPORT = RESEARCH_DATA_DIR / "latest_research.json"
HISTORY_DIR = RESEARCH_DATA_DIR / "history"

CACHE_TTL_SECONDS = {
    "profile": 7 * 24 * 3600,
    "fundamentals": 24 * 3600,
    "news": 30 * 60,
    "competitors": 30 * 24 * 3600,
}


@dataclass
class ResearchSource:
    name: str
    provider: str
    retrieved_at: str
    url: str = ""
    status: str = "OK"
    note: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _cache_path(ticker: str, section: str) -> Path:
    safe = "".join(ch for ch in ticker.upper() if ch.isalnum() or ch in ".-_")
    return RESEARCH_CACHE_DIR / safe / f"{section}.json"


def _read_cache(ticker: str, section: str) -> Optional[Dict[str, Any]]:
    path = _cache_path(ticker, section)
    if not path.exists():
        return None
    ttl = CACHE_TTL_SECONDS.get(section, 3600)
    if time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_cache(ticker: str, section: str, payload: Mapping[str, Any]) -> None:
    _atomic_write(_cache_path(ticker, section), dict(payload))


def _get_yfinance_ticker(ticker: str):
    import yfinance as yf  # type: ignore
    return yf.Ticker(ticker)


def fetch_profile(ticker: str, *, force: bool = False) -> Dict[str, Any]:
    if not force:
        cached = _read_cache(ticker, "profile")
        if cached:
            cached["cache_hit"] = True
            return cached
    retrieved = _now_iso()
    try:
        obj = _get_yfinance_ticker(ticker)
        info = obj.info or {}
        quote_type = str(info.get("quoteType") or "")
        payload = {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "description": info.get("longBusinessSummary") or "",
            "sector": info.get("sector") or "Ukjent",
            "industry": info.get("industry") or "Ukjent",
            "country": info.get("country") or "",
            "website": info.get("website") or "",
            "employees": info.get("fullTimeEmployees"),
            "market_cap": _safe_float(info.get("marketCap")),
            "currency": info.get("currency") or info.get("financialCurrency") or "",
            "exchange": info.get("exchange") or "",
            "quote_type": quote_type,
            "officers": [
                {"name": x.get("name"), "title": x.get("title")}
                for x in (info.get("companyOfficers") or [])[:8] if isinstance(x, Mapping)
            ],
            "retrieved_at": retrieved,
            "cache_hit": False,
            "source": asdict(ResearchSource("Selskapsprofil", "Yahoo Finance via yfinance", retrieved, info.get("website") or "")),
        }
    except Exception as exc:
        payload = {"ticker": ticker.upper(), "name": ticker.upper(), "retrieved_at": retrieved, "error": str(exc), "cache_hit": False,
                   "source": asdict(ResearchSource("Selskapsprofil", "Yahoo Finance via yfinance", retrieved, status="ERROR", note=str(exc)))}
    _write_cache(ticker, "profile", payload)
    return payload


def fetch_fundamentals(ticker: str, *, force: bool = False) -> Dict[str, Any]:
    if not force:
        cached = _read_cache(ticker, "fundamentals")
        if cached:
            cached["cache_hit"] = True
            return cached
    retrieved = _now_iso()
    try:
        info = (_get_yfinance_ticker(ticker).info or {})
        keys = {
            "price": "currentPrice", "pe_trailing": "trailingPE", "pe_forward": "forwardPE",
            "price_to_book": "priceToBook", "ev_ebitda": "enterpriseToEbitda",
            "roe": "returnOnEquity", "gross_margin": "grossMargins", "operating_margin": "operatingMargins",
            "profit_margin": "profitMargins", "revenue_growth": "revenueGrowth", "earnings_growth": "earningsGrowth",
            "debt_to_equity": "debtToEquity", "free_cash_flow": "freeCashflow", "operating_cash_flow": "operatingCashflow",
            "total_revenue": "totalRevenue", "ebitda": "ebitda", "eps_trailing": "trailingEps",
            "dividend_yield": "dividendYield", "beta": "beta", "target_mean_price": "targetMeanPrice",
            "recommendation_mean": "recommendationMean", "number_of_analysts": "numberOfAnalystOpinions",
        }
        metrics = {out: _safe_float(info.get(src)) for out, src in keys.items()}
        payload = {"ticker": ticker.upper(), "metrics": metrics, "retrieved_at": retrieved, "cache_hit": False,
                   "source": asdict(ResearchSource("Fundamentale nøkkeltall", "Yahoo Finance via yfinance", retrieved))}
    except Exception as exc:
        payload = {"ticker": ticker.upper(), "metrics": {}, "retrieved_at": retrieved, "error": str(exc), "cache_hit": False,
                   "source": asdict(ResearchSource("Fundamentale nøkkeltall", "Yahoo Finance via yfinance", retrieved, status="ERROR", note=str(exc)))}
    _write_cache(ticker, "fundamentals", payload)
    return payload


def fetch_news(ticker: str, *, force: bool = False, limit: int = 15) -> Dict[str, Any]:
    if not force:
        cached = _read_cache(ticker, "news")
        if cached:
            cached["cache_hit"] = True
            return cached
    retrieved = _now_iso()
    rows: List[Dict[str, Any]] = []
    error = ""
    try:
        raw = _get_yfinance_ticker(ticker).news or []
        for item in raw[: max(1, int(limit))]:
            content = item.get("content") if isinstance(item, Mapping) else None
            node = content if isinstance(content, Mapping) else item
            title = node.get("title") or "Uten tittel"
            summary = node.get("summary") or node.get("description") or ""
            provider = node.get("provider") or {}
            canonical = node.get("canonicalUrl") or node.get("clickThroughUrl") or {}
            url = canonical.get("url") if isinstance(canonical, Mapping) else (node.get("link") or "")
            published = node.get("pubDate") or node.get("providerPublishTime") or ""
            text = f"{title} {summary}".lower()
            category = "Annet"
            for label, terms in {
                "Resultater": ("earnings", "results", "quarter", "revenue", "profit"),
                "Oppkjøp": ("acquisition", "merger", "takeover", "buyout"),
                "Produkter": ("product", "launch", "approval", "contract"),
                "Regulering": ("regulator", "regulation", "lawsuit", "court", "fda"),
                "Ledelse": ("ceo", "cfo", "management", "board"),
                "Analytikere": ("analyst", "upgrade", "downgrade", "price target"),
            }.items():
                if any(term in text for term in terms):
                    category = label
                    break
            positive_terms = ("beat", "growth", "upgrade", "record", "approval", "wins", "raises")
            negative_terms = ("miss", "downgrade", "decline", "lawsuit", "cuts", "warning", "loss")
            score = sum(term in text for term in positive_terms) - sum(term in text for term in negative_terms)
            impact = "Positiv" if score > 0 else "Negativ" if score < 0 else "Nøytral"
            rows.append({"title": title, "summary": summary, "publisher": provider.get("displayName") if isinstance(provider, Mapping) else "",
                         "published": published, "url": url or "", "category": category, "impact": impact})
    except Exception as exc:
        error = str(exc)
    payload = {"ticker": ticker.upper(), "items": rows, "retrieved_at": retrieved, "cache_hit": False, "error": error,
               "source": asdict(ResearchSource("Nyheter", "Yahoo Finance via yfinance", retrieved, status="ERROR" if error else "OK", note=error))}
    _write_cache(ticker, "news", payload)
    return payload


def infer_competitors(profile: Mapping[str, Any], *, force: bool = False) -> Dict[str, Any]:
    ticker = str(profile.get("ticker") or "").upper()
    if not force:
        cached = _read_cache(ticker, "competitors")
        if cached:
            cached["cache_hit"] = True
            return cached
    # Transparent heuristic list, deliberately marked as suggestions rather than authoritative peers.
    peer_map = {
        "Technology": ["MSFT", "AAPL", "GOOGL", "AMZN", "META", "NVDA"],
        "Healthcare": ["LLY", "NVO", "JNJ", "ABBV", "AZN", "MRK"],
        "Financial Services": ["JPM", "BAC", "GS", "MS", "C", "WFC"],
        "Energy": ["XOM", "CVX", "SHEL", "BP", "TTE", "EQNR.OL"],
        "Industrials": ["GE", "HON", "CAT", "DE", "MMM", "RTX"],
    }
    sector = str(profile.get("sector") or "")
    suggestions = [x for x in peer_map.get(sector, []) if x != ticker][:5]
    retrieved = _now_iso()
    payload = {"ticker": ticker, "sector": sector, "suggested_peers": suggestions, "method": "Sektorbasert forslag – må verifiseres av bruker",
               "retrieved_at": retrieved, "cache_hit": False,
               "source": asdict(ResearchSource("Konkurrentforslag", "Intern transparent sektorheuristikk", retrieved,
                                                note="Forslag er ikke en autoritativ konkurrentliste."))}
    _write_cache(ticker, "competitors", payload)
    return payload


def build_insights(profile: Mapping[str, Any], fundamentals: Mapping[str, Any], news: Mapping[str, Any]) -> Dict[str, List[str]]:
    m = fundamentals.get("metrics") or {}
    positives: List[str] = []
    risks: List[str] = []
    catalysts: List[str] = []
    growth = _safe_float(m.get("revenue_growth"))
    margin = _safe_float(m.get("operating_margin"))
    debt = _safe_float(m.get("debt_to_equity"))
    pe = _safe_float(m.get("pe_forward"))
    if growth is not None:
        (positives if growth > 0.10 else risks if growth < 0 else catalysts).append(f"Omsetningsvekst: {growth:.1%}.")
    if margin is not None:
        (positives if margin > 0.15 else risks if margin < 0.05 else catalysts).append(f"Driftsmargin: {margin:.1%}.")
    if debt is not None and debt > 150:
        risks.append(f"Gjeld/egenkapital er høy ({debt:.0f}).")
    if pe is not None and pe > 35:
        risks.append(f"Høy forward P/E ({pe:.1f}) øker verdsettelsesrisikoen.")
    for item in (news.get("items") or [])[:8]:
        title = str(item.get("title") or "")
        if item.get("impact") == "Positiv":
            catalysts.append(title)
        elif item.get("impact") == "Negativ":
            risks.append(title)
    if not positives:
        positives.append("Ingen tydelig positiv konklusjon kan trekkes fra tilgjengelige nøkkeltall alene.")
    if not risks:
        risks.append("Datagrunnlaget viser ingen åpenbar enkeltstående risiko; dette er ikke det samme som fravær av risiko.")
    if not catalysts:
        catalysts.append("Ingen tydelig katalysator identifisert i tilgjengelige nyheter.")
    return {"positive_drivers": positives[:8], "risks": risks[:8], "catalysts": catalysts[:8]}


def collect_research(ticker: str, *, force: bool = False) -> Dict[str, Any]:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker kan ikke være tom.")
    profile = fetch_profile(ticker, force=force)
    fundamentals = fetch_fundamentals(ticker, force=force)
    news = fetch_news(ticker, force=force)
    competitors = infer_competitors(profile, force=force)
    insights = build_insights(profile, fundamentals, news)
    report = {
        "version": "v18.6.84", "generated_at": _now_iso(), "ticker": ticker,
        "profile": profile, "fundamentals": fundamentals, "news": news,
        "competitors": competitors, "insights": insights,
        "disclaimer": "Beslutningsstøtte, ikke investeringsråd. Verifiser alltid tall mot primærkilder.",
        "learning_loop": "OFF", "trading_side_effects": False,
    }
    _atomic_write(LATEST_REPORT, report)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _atomic_write(HISTORY_DIR / ticker / f"research_{stamp}.json", report)
    return report


def investment_memo_markdown(report: Mapping[str, Any]) -> str:
    p = report.get("profile") or {}
    m = (report.get("fundamentals") or {}).get("metrics") or {}
    ins = report.get("insights") or {}
    lines = [
        f"# Investeringsnotat – {p.get('name') or report.get('ticker')}", "",
        f"**Ticker:** {report.get('ticker')}  ", f"**Generert:** {report.get('generated_at')}  ",
        "", "## Selskap", str(p.get("description") or "Ingen selskapsbeskrivelse tilgjengelig."), "",
        "## Nøkkeltall",
    ]
    for key in ("price", "pe_forward", "ev_ebitda", "roe", "operating_margin", "revenue_growth", "debt_to_equity", "free_cash_flow"):
        lines.append(f"- **{key}:** {m.get(key)}")
    lines += ["", "## Positive drivere"] + [f"- {x}" for x in ins.get("positive_drivers", [])]
    lines += ["", "## Risiko"] + [f"- {x}" for x in ins.get("risks", [])]
    lines += ["", "## Katalysatorer"] + [f"- {x}" for x in ins.get("catalysts", [])]
    lines += ["", "## Kilder"]
    for section in ("profile", "fundamentals", "news", "competitors"):
        src = (report.get(section) or {}).get("source") or {}
        lines.append(f"- {src.get('name', section)} – {src.get('provider', '')}, hentet {src.get('retrieved_at', '')}")
    lines += ["", "> Beslutningsstøtte, ikke investeringsråd. Verifiser alltid tall mot primærkilder."]
    return "\n".join(lines)


def answer_research_question(report: Mapping[str, Any], question: str) -> str:
    q = (question or "").lower()
    ins = report.get("insights") or {}
    p = report.get("profile") or {}
    if any(word in q for word in ("risiko", "risk", "svak")):
        return "\n".join(f"• {x}" for x in ins.get("risks", []))
    if any(word in q for word in ("katalys", "driver", "positiv", "opp-side")):
        rows = list(ins.get("positive_drivers", [])) + list(ins.get("catalysts", []))
        return "\n".join(f"• {x}" for x in rows)
    if any(word in q for word in ("selskap", "business", "forretning", "hva gjør")):
        return str(p.get("description") or "Ingen selskapsbeskrivelse er tilgjengelig i kildedataene.")
    return ("Jeg kan besvare spørsmål om selskapet, nøkkeltall, risikoer, katalysatorer og nyhetsbildet. "
            "Svaret er begrenset til dataene i denne research-rapporten og bruker ikke skjulte eller ukjente kilder.")


def render_research_assistant() -> None:
    import streamlit as st
    try:
        import pandas as pd  # type: ignore
    except Exception:
        pd = None  # type: ignore

    st.markdown("### 🤖 Research – AI Research Assistant")
    st.caption("Sporbar, read-only selskapsresearch. Ingen handler, regelendringer eller Learning Loop.")
    c1, c2, c3 = st.columns([1.2, 0.8, 0.8])
    ticker = c1.text_input("Ticker", value=st.session_state.get("research_ticker_v18684", "NVO"), key="research_ticker_v18684").strip().upper()
    force = c2.checkbox("Oppdater kilder", value=False, key="research_force_v18684")
    run = c3.button("Kjør research", type="primary", use_container_width=True, key="research_run_v18684")

    report = st.session_state.get("research_report_v18684")
    if run:
        try:
            with st.spinner("Henter og strukturerer research …"):
                report = collect_research(ticker, force=force)
            st.session_state["research_report_v18684"] = report
            st.success("Research fullført.")
        except Exception as exc:
            st.error(f"Research kunne ikke fullføres: {exc}")
            return
    if not report:
        st.info("Velg ticker og kjør research. Eksempel for Oslo Børs: EQNR.OL.")
        return

    profile = report.get("profile") or {}
    metrics = (report.get("fundamentals") or {}).get("metrics") or {}
    name = profile.get("name") or report.get("ticker")
    st.markdown(f"#### {name} ({report.get('ticker')})")
    a, b, c, d = st.columns(4)
    a.metric("Sektor", profile.get("sector") or "Ukjent")
    b.metric("Markedsverdi", f"{profile.get('market_cap'):,.0f}" if profile.get("market_cap") else "–")
    c.metric("Forward P/E", f"{metrics.get('pe_forward'):.2f}" if metrics.get("pe_forward") is not None else "–")
    d.metric("Omsetningsvekst", f"{metrics.get('revenue_growth'):.1%}" if metrics.get("revenue_growth") is not None else "–")

    tabs = st.tabs(["📄 Selskap", "📊 Fundamentalt", "📰 Nyheter", "🏭 Konkurrenter", "📝 Investeringsnotat", "💬 Spør research", "📚 Kilder"])
    with tabs[0]:
        st.write(profile.get("description") or "Ingen beskrivelse tilgjengelig.")
        st.json({k: profile.get(k) for k in ("sector", "industry", "country", "exchange", "currency", "employees", "website")})
    with tabs[1]:
        rows = [{"Nøkkeltall": k, "Verdi": v} for k, v in metrics.items()]
        st.dataframe(pd.DataFrame(rows) if pd is not None else rows, use_container_width=True, hide_index=True)
        ins = report.get("insights") or {}
        col1, col2, col3 = st.columns(3)
        col1.markdown("**Positive drivere**\n\n" + "\n".join(f"- {x}" for x in ins.get("positive_drivers", [])))
        col2.markdown("**Risiko**\n\n" + "\n".join(f"- {x}" for x in ins.get("risks", [])))
        col3.markdown("**Katalysatorer**\n\n" + "\n".join(f"- {x}" for x in ins.get("catalysts", [])))
    with tabs[2]:
        items = (report.get("news") or {}).get("items") or []
        if items:
            st.dataframe(pd.DataFrame(items) if pd is not None else items, use_container_width=True, hide_index=True,
                         column_config={"url": st.column_config.LinkColumn("Kilde")})
        else:
            st.warning("Ingen nyheter tilgjengelig fra konfigurert leverandør.")
    with tabs[3]:
        peers = (report.get("competitors") or {}).get("suggested_peers") or []
        st.write("Foreslåtte peers:", ", ".join(peers) if peers else "Ingen forslag")
        st.caption((report.get("competitors") or {}).get("method") or "")
    with tabs[4]:
        memo = investment_memo_markdown(report)
        st.markdown(memo)
        st.download_button("Last ned Markdown", memo.encode("utf-8"), file_name=f"research_{report.get('ticker')}.md", mime="text/markdown")
        st.download_button("Last ned JSON", json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8"), file_name=f"research_{report.get('ticker')}.json", mime="application/json")
        st.caption("PDF kan lagres fra nettleserens utskriftsdialog.")
    with tabs[5]:
        question = st.text_area("Spørsmål", placeholder="Hvilke risikoer er viktigst?", key="research_question_v18684")
        if st.button("Svar fra rapporten", key="research_answer_v18684"):
            st.markdown(answer_research_question(report, question))
    with tabs[6]:
        source_rows = []
        for section in ("profile", "fundamentals", "news", "competitors"):
            source = (report.get(section) or {}).get("source") or {}
            source_rows.append({"Del": section, **source, "cache_hit": (report.get(section) or {}).get("cache_hit", False)})
        st.dataframe(pd.DataFrame(source_rows) if pd is not None else source_rows, use_container_width=True, hide_index=True,
                     column_config={"url": st.column_config.LinkColumn("Original")})
        st.warning(report.get("disclaimer"))
