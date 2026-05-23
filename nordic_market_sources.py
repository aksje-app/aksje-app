from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote_plus


NORDIC_SUFFIXES = (".OL", ".ST", ".CO", ".HE")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def ticker_root(ticker: str) -> str:
    text = _clean(ticker).upper()
    for suffix in NORDIC_SUFFIXES + (".SA",):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def market_family(ticker: str, market: str | None = None) -> str:
    symbol = _clean(ticker).upper()
    market_text = _clean(market).lower()
    if symbol.endswith(".OL") or "norge" in market_text or "oslo" in market_text:
        return "Norge"
    if symbol.endswith(".ST") or "sverige" in market_text or "stockholm" in market_text:
        return "Sverige"
    if symbol.endswith(".CO") or "danmark" in market_text or "copenhagen" in market_text:
        return "Danmark"
    if symbol.endswith(".HE") or "finland" in market_text or "helsinki" in market_text:
        return "Finland"
    if symbol.endswith(".SA") or "brasil" in market_text or "brazil" in market_text:
        return "Brasil"
    if symbol and "." not in symbol:
        return "USA"
    return market or ""


def local_market_source_links(ticker: str, company: str | None = None, market: str | None = None) -> list[dict[str, str]]:
    symbol = _clean(ticker).upper()
    root = ticker_root(symbol)
    name = _clean(company)
    query_name = name or root
    family = market_family(symbol, market)
    links: list[dict[str, str]] = []

    def add(title: str, source: str, url: str, detail: str) -> None:
        links.append({
            "type": "kildediagnostikk",
            "title": title,
            "source": source,
            "published": "",
            "url": url,
            "detail": detail,
            "market": family,
        })

    if family == "Norge":
        add(
            "Borsmeldinger og primarinnsider-sok",
            "Oslo Bors NewsWeb",
            f"https://newsweb.oslobors.no/search?query={quote_plus(root)}",
            "Offisiell kilde for meldinger, flagging og primarinnsidehandler paa Oslo Bors.",
        )
        add(
            "Lokalt sok etter insider/bjellesau",
            "Norden-kildesok",
            _search_url(f'site:newsweb.oslobors.no {root} {query_name} primærinnsider flagging kontrakt guiding'),
            "Sokelenke for norske meldinger, eierhendelser og katalysatorer.",
        )
    elif family == "Sverige":
        add(
            "Insyn og flagging",
            "Finansinspektionen",
            "https://marknadssok.fi.se/publiceringsklient",
            "Offisiell svensk kilde for insynshandel og flagging. Sjekk ticker/navn manuelt.",
        )
        add(
            "Svenske bolagsmeddelanden",
            "Nasdaq Nordic",
            "https://www.nasdaqomxnordic.com/news/companynews",
            "Offisiell nordisk meldingsside for selskapsnyheter.",
        )
        add(
            "Lokalt sok etter insyn/katalysator",
            "Norden-kildesok",
            _search_url(f'{root} {query_name} insynshandel flaggning bolagsmeddelande order guidning'),
            "Sokelenke for svenske insider-, flaggings- og nyhetsspor.",
        )
    elif family == "Danmark":
        add(
            "Danske selskabsmeddelelser",
            "Nasdaq Nordic",
            "https://www.nasdaqomxnordic.com/news/companynews",
            "Offisiell nordisk meldingsside for danske selskapsmeldinger.",
        )
        add(
            "Managers transactions / OAM",
            "Finanstilsynet Danmark",
            "https://oasm.finanstilsynet.dk/",
            "Dansk OAM-kilde for offentliggjorte meldinger. Sjekk ticker/navn manuelt.",
        )
        add(
            "Lokalt sok etter ledende medarbejdere/katalysator",
            "Norden-kildesok",
            _search_url(f'{root} {query_name} ledende medarbejdere selskabsmeddelelse insider kontrakt guidance'),
            "Sokelenke for danske insider-, OAM- og katalysatorspor.",
        )
    elif family == "Finland":
        add(
            "Managers transactions",
            "FIN-FSA",
            "https://www.finanssivalvonta.fi/en/capital-markets/issuers-and-investors/managers-transactions/",
            "Finsk offisiell side for ledertransaksjoner. Sjekk selskap/navn manuelt.",
        )
        add(
            "Finske selskapsmeldinger",
            "Nasdaq Nordic",
            "https://www.nasdaqomxnordic.com/news/companynews",
            "Offisiell nordisk meldingsside for finske selskapsmeldinger.",
        )
        add(
            "Lokalt sok etter johtohenkilo/katalysator",
            "Norden-kildesok",
            _search_url(f'{root} {query_name} managers transactions company announcement guidance contract'),
            "Sokelenke for finske insider-, meldings- og katalysatorspor.",
        )
    elif family == "Brasil":
        add(
            "CVM selskapsmeldinger",
            "CVM RAD",
            "https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx",
            "Brasiliansk kilde for company filings og meldinger. Sjekk ticker/navn manuelt.",
        )
        add(
            "Lokalt sok etter fatos relevantes/insider",
            "Brasil-kildesok",
            _search_url(f'{root} {query_name} fato relevante insiders acionistas guidance contrato'),
            "Sokelenke for brasilianske meldinger, eierhendelser og katalysatorer.",
        )
    return links


def local_news_queries(ticker: str, company: str | None = None, market: str | None = None) -> list[str]:
    root = ticker_root(ticker)
    name = _clean(company)
    base = " ".join(x for x in (root, name) if x)
    family = market_family(ticker, market)
    if family == "Norge":
        terms = ("primarinnsider", "flagging", "borsmelding", "kontrakt", "guiding", "ordrebok")
    elif family == "Sverige":
        terms = ("insynshandel", "flaggning", "bolagsmeddelande", "order", "guidning")
    elif family == "Danmark":
        terms = ("ledende medarbejdere", "selskabsmeddelelse", "kontrakt", "guidance")
    elif family == "Finland":
        terms = ("managers transactions", "company announcement", "guidance", "contract")
    elif family == "Brasil":
        terms = ("fato relevante", "acionistas", "guidance", "contrato")
    else:
        terms = ("insider", "ownership", "guidance", "contract", "earnings")
    return [f"{base} {term}".strip() for term in terms if base]


def local_market_source_diagnostics(row: Mapping[str, Any], *, horizon: str = "3m") -> list[dict[str, str]]:
    ticker = _clean(row.get("ticker"))
    if not ticker:
        return []
    company = _clean(row.get("name") or row.get("company"))
    market = _clean(row.get("market"))
    links = local_market_source_links(ticker, company, market)
    if not links:
        return []
    months = {"1m": "1 mnd", "3m": "3 mnd", "6m": "6 mnd", "12m": "12 mnd"}.get(horizon, horizon)
    diagnostics: list[dict[str, str]] = []
    for link in links:
        item = dict(link)
        item["status"] = "manuell kilde"
        item["window"] = months
        diagnostics.append(item)
    return diagnostics


def merge_source_diagnostics(existing: Any, additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in list(existing or []) + list(additions or []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        marker = (str(item.get("title") or "").lower(), str(item.get("url") or "").lower())
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(item)
    return merged


__all__ = [
    "local_market_source_diagnostics",
    "local_market_source_links",
    "local_news_queries",
    "market_family",
    "merge_source_diagnostics",
    "ticker_root",
]
