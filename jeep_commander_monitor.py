"""Temporary, isolated Jeep Commander 2.2 listing monitor.

The monitor deliberately shares only the existing Render cron and Pushover
transport with the investment application.  Configuration, observations and
deduplication state live below their own durable namespace and can be purged
without touching reports, learning data or portfolios.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import html as html_lib
import json
import os
import re
import threading
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests

from durable_runtime import read_json, write_json
from notifier import normalize_notification_result, send_pushover_alert
from storage_architecture import runtime_data_path


MODULE_NAME = "Jeep Commander 2.2"
CONFIG_KEY = "temporary/jeep_commander_22/config.json"
STATE_KEY = "temporary/jeep_commander_22/state.json"
CONFIG_PATH = runtime_data_path("temporary", "jeep_commander_22", "config.json")
STATE_PATH = runtime_data_path("temporary", "jeep_commander_22", "state.json")
INTERVAL_MINUTES = 15
_PROCESS_LOCK = threading.Lock()
_PG_ADVISORY_LOCK_ID = 22122026
_NORTHEAST_STATES = {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"}
_STATE_DISTANCE_KM = {
    "CE": 0, "RN": 520, "PB": 690, "PI": 600, "PE": 800,
    "MA": 900, "AL": 1060, "SE": 1240, "BA": 1210,
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def default_config(*, now: datetime | None = None) -> dict[str, Any]:
    created = (now or _now()).astimezone(timezone.utc)
    return {
        "schema_version": 1,
        "name": MODULE_NAME,
        "active": True,
        "years": [2025, 2026],
        "max_km": 20000,
        "area": "CEARA",
        "preferred_color": "PRETO",
        "include_other_colors": True,
        "interval_minutes": INTERVAL_MINUTES,
        "pushover": True,
        "include_dealer_network": True,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(days=90)).isoformat(),
    }


def _normalize_config(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    base = default_config()
    base.update(raw)
    years_set: set[int] = set()
    for year in base.get("years") or []:
        try:
            parsed_year = int(year)
        except (TypeError, ValueError):
            continue
        if parsed_year in {2025, 2026}:
            years_set.add(parsed_year)
    years = sorted(years_set)
    base["years"] = years or [2025, 2026]
    base["max_km"] = 35000 if int(base.get("max_km") or 20000) == 35000 else 20000
    base["area"] = str(base.get("area") or "CEARA").upper()
    if base["area"] not in {"CEARA", "NORDESTE", "BRASIL"}:
        base["area"] = "CEARA"
    base["interval_minutes"] = INTERVAL_MINUTES
    return base


def load_config() -> dict[str, Any]:
    stored = read_json(CONFIG_KEY, CONFIG_PATH, None)
    if not isinstance(stored, dict):
        stored = default_config()
        write_json(CONFIG_KEY, CONFIG_PATH, stored)
    return _normalize_config(stored)


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_config(config)
    normalized["updated_at"] = _now().isoformat()
    write_json(CONFIG_KEY, CONFIG_PATH, normalized)
    return normalized


def load_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, dict) else {}


def _save_state(state: dict[str, Any]) -> dict[str, Any]:
    write_json(STATE_KEY, STATE_PATH, state)
    return state


def purge_temporary_module() -> None:
    """Disable and erase all listing/history state without touching other data."""
    disabled = default_config()
    disabled.update({"active": False, "deleted_at": _now().isoformat()})
    write_json(CONFIG_KEY, CONFIG_PATH, disabled)
    write_json(STATE_KEY, STATE_PATH, {"state": "DELETED", "deleted_at": _now().isoformat()})
    for path in (CONFIG_PATH, STATE_PATH):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def _global_lock():
    if not _PROCESS_LOCK.acquire(blocking=False):
        yield False
        return
    connection = None
    acquired = True
    try:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if database_url:
            try:
                import psycopg2
                connection = psycopg2.connect(database_url, connect_timeout=5)
                cursor = connection.cursor()
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (_PG_ADVISORY_LOCK_ID,))
                acquired = bool(cursor.fetchone()[0])
            except Exception:
                acquired = True  # local process remains serialized
        yield acquired
    finally:
        if connection is not None:
            try:
                if acquired:
                    cursor = connection.cursor()
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (_PG_ADVISORY_LOCK_ID,))
                connection.close()
            except Exception:
                pass
        _PROCESS_LOCK.release()


def build_source_urls(config: dict[str, Any]) -> list[dict[str, str]]:
    """Return low-rate public searches. Result filtering is always local and strict."""
    years = sorted(config.get("years") or [2025, 2026])
    low, high = years[0], years[-1]
    area = str(config.get("area") or "CEARA")
    if area == "CEARA":
        wm = f"https://www.webmotors.com.br/carros/ce-fortaleza/jeep/commander/de.{low}/ate.{high}"
        olx_base = "https://www.olx.com.br/autos-e-pecas/carros-vans-e-utilitarios/jeep/commander/overl-22-td-4x4-diesel-aut/{year}/estado-ce"
    elif area == "NORDESTE":
        wm = f"https://www.webmotors.com.br/carros/regiao-nordeste/jeep/commander/de.{low}/ate.{high}"
        olx_base = "https://www.olx.com.br/regiao-nordeste/autos-e-pecas/carros-vans-e-utilitarios/jeep/commander/overl-22-td-4x4-diesel-aut/{year}"
    else:
        wm = f"https://www.webmotors.com.br/carros/estoque/jeep/commander/de.{low}/ate.{high}"
        olx_base = "https://www.olx.com.br/autos-e-pecas/carros-vans-e-utilitarios/jeep/commander/overl-22-td-4x4-diesel-aut/{year}/estado-brasil"
    sources = [
        {"source": "Webmotors", "query": f"{low}-{high}", "url": wm, "channel": "MARKETPLACE", "default_seller_type": "UKJENT"},
        *({"source": "OLX", "query": str(year), "url": olx_base.format(year=year), "channel": "MARKETPLACE", "default_seller_type": "UKJENT"} for year in years),
        *({"source": "Mobiauto", "query": str(year), "url": f"https://www.mobiauto.com.br/comprar/carros/sp-sao-paulo/jeep/commander/ano-{year}", "channel": "MARKETPLACE", "default_seller_type": "UKJENT"} for year in years),
    ]
    if config.get("include_dealer_network", True):
        # Dealer-owned inventories complement the marketplaces. Filtering for
        # year, engine, mileage and geography remains local and identical.
        sources.extend([
            {"source": "Localiza Seminovos", "query": area, "url": "https://seminovos.localiza.com/carros/jeep/commander", "channel": "DEALER_NETWORK", "default_seller_type": "FORHANDLER"},
            {"source": "Seminovos.com.br", "query": area, "url": "https://seminovos.com.br/carros/jeep/commander", "channel": "DEALER_NETWORK", "default_seller_type": "FORHANDLER"},
        ])
    return sources


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9,.-]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[-1]
        cleaned = cleaned.replace(",", "." if len(tail) <= 2 else "")
    elif cleaned.count(".") > 1 or ("." in cleaned and len(cleaned.rsplit(".", 1)[-1]) == 3):
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except Exception:
        return None


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, "", [], {}):
            return lowered[key.lower()]
    return None


def _location(raw: Any) -> tuple[str, str]:
    if isinstance(raw, dict):
        city = _first(raw, ("city", "cidade", "addressLocality"))
        state = _first(raw, ("state", "uf", "estado", "addressRegion"))
        return str(city or "").strip(), str(state or "").strip().upper()[:2]
    text = str(raw or "")
    match = re.search(r"([A-Za-zÀ-ÿ .'-]+)[,/-]\s*([A-Z]{2})\b", text)
    return (match.group(1).strip(), match.group(2)) if match else (text.strip(), "")


def _vehicle_years(item: dict[str, Any], blob: str) -> tuple[int | None, int | None, list[int]]:
    """Read Brazilian fabrication/model year without treating both as model years."""
    production_raw = _first(item, ("fabricationYear", "manufactureYear", "productionYear", "anoFabricacao"))
    model_raw = _first(item, ("modelYear", "vehicleModelYear", "anoModelo"))
    production_year = int(_number(production_raw)) if _number(production_raw) in {2024.0, 2025.0, 2026.0, 2027.0} else None
    model_year = int(_number(model_raw)) if _number(model_raw) in {2024.0, 2025.0, 2026.0, 2027.0} else None

    # Marketplaces commonly abbreviate the pair in the title as 2025/2026.
    pair = re.search(r"\b(202[4-7])\s*[/|-]\s*(202[4-7])\b", str(blob or ""))
    if pair:
        production_year = production_year or int(pair.group(1))
        model_year = model_year or int(pair.group(2))
    found = [int(year) for year in re.findall(r"\b(202[4-7])\b", str(blob or ""))]
    if model_year is None and found:
        model_year = found[-1]
    if production_year is None and found:
        production_year = found[0]
    display_years = []
    for year in (production_year, model_year):
        if year is not None and year not in display_years:
            display_years.append(year)
    return production_year, model_year, display_years


def _seller_details(item: dict[str, Any], *, source: str, default_seller_type: str = "UKJENT") -> tuple[str, str, bool]:
    raw = _first(item, ("seller", "dealer", "store", "loja", "advertiser", "provider"))
    mapping = raw if isinstance(raw, dict) else {}
    name = str(_first(mapping, ("name", "legalName", "tradeName", "nome")) or (raw if isinstance(raw, str) else "")).strip()
    type_blob = " ".join(str(value or "") for value in (
        _first(mapping, ("@type", "type", "sellerType", "advertiserType")),
        _first(item, ("sellerType", "advertiserType", "tipoVendedor")), name, source,
    )).lower()
    if any(token in type_blob for token in ("person", "pessoa física", "pessoa fisica", "particular", "privado")):
        seller_type = "PRIVAT"
    elif any(token in type_blob for token in ("dealer", "organization", "loja", "concession", "seminovos", "revenda")):
        seller_type = "FORHANDLER"
    else:
        seller_type = default_seller_type if default_seller_type in {"PRIVAT", "FORHANDLER"} else "UKJENT"
    authorized = seller_type == "FORHANDLER" and any(token in type_blob for token in ("autorizad", "concessionária jeep", "concessionaria jeep", "jeep dealer"))
    return name, seller_type, authorized


def _candidate_from_dict(item: dict[str, Any], *, source: str, base_url: str, default_seller_type: str = "UKJENT") -> dict[str, Any] | None:
    title = _first(item, ("name", "title", "subject", "vehicleTitle", "version"))
    url = _first(item, ("url", "link", "permalink", "detailUrl", "vehicleUrl"))
    offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
    price = _first(item, ("price", "salePrice", "vehiclePrice", "listPrice")) or _first(offers, ("price", "lowPrice"))
    mileage = _first(item, ("mileageFromOdometer", "mileage", "kilometers", "km", "odometer"))
    if isinstance(mileage, dict):
        mileage = _first(mileage, ("value", "maxValue"))
    description = _first(item, ("description", "subtitle", "details"))
    blob = " ".join(str(v) for v in (title, description, _first(item, ("model", "version", "fuel", "traction"))) if v)
    if "commander" not in blob.lower() and "commander" not in str(url or "").lower():
        return None
    if not url or _number(price) is None:
        return None
    location_raw = _first(item, ("location", "address", "sellerLocation"))
    city, state = _location(location_raw)
    if isinstance(location_raw, dict):
        city2, state2 = _location(location_raw)
        city, state = city or city2, state or state2
    city = city or str(_first(item, ("city", "cidade")) or "").strip()
    state = state or str(_first(item, ("state", "uf")) or "").strip().upper()[:2]
    generic_year = _first(item, ("year", "vehicleYear", "ano"))
    year_blob = blob + " " + str(generic_year or "")
    production_year, model_year, years = _vehicle_years(item, year_blob)
    color = str(_first(item, ("color", "vehicleColor", "cor")) or "").strip()
    absolute_url = urljoin(base_url, str(url))
    raw_id = _first(item, ("id", "vehicleId", "adId", "listingId"))
    listing_id = str(raw_id or hashlib.sha256(absolute_url.encode()).hexdigest()[:20])
    seller_name, seller_type, authorized = _seller_details(item, source=source, default_seller_type=default_seller_type)
    return {
        "id": f"{source.lower()}:{listing_id}", "source": source,
        "title": html_lib.unescape(str(title or "Jeep Commander")).strip(),
        "description": html_lib.unescape(str(description or "")).strip()[:1000],
        "url": absolute_url, "price_brl": int(round(float(_number(price) or 0))),
        "km": int(round(float(_number(mileage) or 0))) if _number(mileage) is not None else None,
        "years": years, "production_year": production_year, "model_year": model_year,
        "color": color, "city": city, "state": state,
        "seller_name": seller_name, "seller_type": seller_type,
        "authorized_jeep": authorized,
        "raw_text": html_lib.unescape(blob),
    }


def parse_marketplace_html(content: str, *, source: str, base_url: str, default_seller_type: str = "UKJENT") -> list[dict[str, Any]]:
    """Parse structured public payloads without bypassing bot protection."""
    payloads: list[Any] = []
    for match in re.finditer(
        r'<script[^>]+(?:type=["\']application/ld\+json["\']|id=["\']__NEXT_DATA__["\'])[^>]*>(.*?)</script>',
        str(content or ""), flags=re.I | re.S,
    ):
        try:
            payloads.append(json.loads(html_lib.unescape(match.group(1)).strip()))
        except Exception:
            continue
    results: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for item in _walk(payload):
            candidate = _candidate_from_dict(item, source=source, base_url=base_url, default_seller_type=default_seller_type)
            if candidate:
                results[candidate["id"]] = candidate
    for candidate in _parse_visible_listing_cards(content, source=source, base_url=base_url, default_seller_type=default_seller_type):
        results[candidate["id"]] = candidate
    return list(results.values())


def _plain_text(fragment: str) -> str:
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", str(fragment or ""), flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html_lib.unescape(value)).strip()


def _parse_visible_listing_cards(content: str, *, source: str, base_url: str, default_seller_type: str = "UKJENT") -> list[dict[str, Any]]:
    """Parse server-rendered OLX/Mobiauto/Webmotors result cards.

    Marketplace pages frequently keep each title in an anchor while mileage,
    colour, price and location follow as siblings.  A bounded segment ending
    at the next Commander anchor preserves that card without relying on CSS
    class names that change often.
    """
    page = str(content or "")
    anchors = list(re.finditer(
        r"<a\b(?P<attrs>[^>]*\bhref\s*=\s*[\"'][^\"']+[\"'][^>]*)>(?P<body>.*?)</a>",
        page, flags=re.I | re.S,
    ))
    commander_anchors = [match for match in anchors if "commander" in _plain_text(match.group("body")).lower()]
    rows: dict[str, dict[str, Any]] = {}
    colors = ("Preto", "Preta", "Branco", "Branca", "Cinza", "Prata", "Azul", "Vermelho", "Verde", "Dourado", "Marrom")
    for index, match in enumerate(commander_anchors):
        title = _plain_text(match.group("body"))
        end = commander_anchors[index + 1].start() if index + 1 < len(commander_anchors) else min(len(page), match.end() + 5000)
        segment = _plain_text(page[match.start():end])
        if not re.search(r"\b2[.,]2\b", segment) or not ("diesel" in segment.lower() or re.search(r"\btd\b", segment.lower())):
            continue
        km_match = re.search(r"\b([0-9]{1,3}(?:[.]?[0-9]{3})*)\s*km\b", segment, flags=re.I)
        prices = re.findall(r"R\$\s*([0-9]{1,3}(?:[.]?[0-9]{3})+)", segment, flags=re.I)
        if not km_match or not prices:
            continue
        href_match = re.search(r"\bhref\s*=\s*[\"']([^\"']+)[\"']", match.group("attrs"), flags=re.I)
        if not href_match:
            continue
        url = urljoin(base_url, html_lib.unescape(href_match.group(1)))
        location_matches = re.findall(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'-]{1,45})\s*[-–]\s*([A-Z]{2})\b", segment)
        city, state = location_matches[-1] if location_matches else ("", "")
        color = next((name for name in colors if re.search(rf"\b{name}\b", segment, flags=re.I)), "")
        segment_lower = segment.lower()
        if any(token in segment_lower for token in ("pessoa física", "pessoa fisica", "particular", "vendedor privado")):
            seller_type = "PRIVAT"
        elif any(token in segment_lower for token in ("concessionária", "concessionaria", "loja", "revenda")):
            seller_type = "FORHANDLER"
        else:
            seller_type = default_seller_type
        authorized = seller_type == "FORHANDLER" and any(token in segment_lower for token in ("autorizada jeep", "concessionária jeep", "concessionaria jeep"))
        production_year, model_year, years = _vehicle_years({}, segment)
        listing_id = hashlib.sha256(url.split("?", 1)[0].encode()).hexdigest()[:20]
        row = {
            "id": f"{source.lower()}:{listing_id}", "source": source, "title": title,
            "description": segment[:1500], "raw_text": segment, "url": url,
            "price_brl": int(_number(prices[-1]) or 0), "km": int(_number(km_match.group(1)) or 0),
            "years": years, "production_year": production_year, "model_year": model_year,
            "color": color, "city": city.strip(), "state": state.upper(),
            "seller_name": "", "seller_type": seller_type,
            "authorized_jeep": authorized,
        }
        if row["price_brl"] > 0 and _valid_url(url):
            rows[row["id"]] = row
    return list(rows.values())


def _valid_url(value: str) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_black(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(token in normalized for token in ("preto", "preta", "black", "nero"))


def _is_target(listing: dict[str, Any], config: dict[str, Any]) -> bool:
    return _target_rejection_reason(listing, config) == ""


def _target_rejection_reason(listing: dict[str, Any], config: dict[str, Any]) -> str:
    text = " ".join(str(listing.get(key) or "") for key in ("title", "description", "raw_text")).lower()
    if "commander" not in text or not re.search(r"\b2[.,]2\b", text):
        return "ikke Commander 2.2"
    if not ("diesel" in text or "turbodiesel" in text or re.search(r"\btd\b", text)):
        return "ikke diesel"
    # Jeep's 2.2 diesel configuration is 4x4 even when a marketplace omits it
    # from the abbreviated title; an explicit conflicting 4x2 is rejected.
    if "4x2" in text or "4 x 2" in text:
        return "eksplisitt 4x2"
    model_year = listing.get("model_year")
    if model_year is None:
        # Compatibility for already parsed state: in a Brazilian year pair the
        # final/highest stored value is the model year.
        stored_years = [int(year) for year in listing.get("years") or []]
        model_year = stored_years[-1] if stored_years else None
    if model_year not in set(config.get("years") or []):
        return "modellår utenfor valget"
    km = listing.get("km")
    if km is None or int(km) > int(config.get("max_km") or 20000):
        return "km mangler eller over grensen"
    state = str(listing.get("state") or "").upper()
    area = str(config.get("area") or "CEARA")
    if area == "CEARA" and state != "CE":
        return "utenfor Ceará"
    if area == "NORDESTE" and state not in _NORTHEAST_STATES:
        return "utenfor Nordøst-Brasil"
    if not config.get("include_other_colors", True) and not _is_black(
        f"{listing.get('color', '')} {text}"
    ):
        return "annen farge er deaktivert"
    if not _valid_url(str(listing.get("url") or "")) or float(listing.get("price_brl") or 0) <= 0:
        return "ugyldig lenke eller pris"
    return ""


def _enrich_and_rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    prices = sorted(float(row["price_brl"]) for row in rows)
    median = prices[len(prices) // 2]
    min_price, max_price = min(prices), max(prices)
    spread = max(1.0, max_price - min_price)
    ranked = []
    for row in rows:
        item = dict(row)
        price = float(item["price_brl"])
        km = max(0, int(item.get("km") or 0))
        black = _is_black(f"{item.get('color', '')} {item.get('raw_text', '')}")
        local = str(item.get("state") or "").upper() == "CE"
        item["black"] = black
        item["local"] = local
        item["distance_from_fortaleza_km"] = _STATE_DISTANCE_KM.get(str(item.get("state") or "").upper())
        item["price_advantage_pct"] = round((median - price) / median * 100, 1) if median else 0.0
        # Price dominates; black and local are preferences, never hard gates.
        item["value_score"] = round(
            60 * (max_price - price) / spread + 25 * (1 - min(km, 35000) / 35000)
            + (10 if black else 0) + (5 if local else 0), 2
        )
        ranked.append(item)
    return sorted(ranked, key=lambda row: (-float(row["value_score"]), float(row["price_brl"]), int(row.get("km") or 0)))


def _dedupe_signature(item: dict[str, Any]) -> str:
    """Conservative cross-site identity without inventing a VIN.

    Listings are combined only when model year, exact odometer, location and
    normalized variant agree and prices are close. Distinct cars are therefore
    preferred over an unsafe merge when information is incomplete.
    """
    title = re.sub(r"\b(?:jeep|commander|diesel|turbo|at9|4x4)\b", " ", str(item.get("title") or "").lower())
    variant = re.sub(r"[^a-z0-9]+", "", title)[:40]
    parts = (
        item.get("model_year"), item.get("km"), str(item.get("city") or "").lower().strip(),
        str(item.get("state") or "").upper(), variant,
    )
    return hashlib.sha256("|".join(str(value or "") for value in parts).encode()).hexdigest()[:24]


def _deduplicate_across_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_dedupe_signature(row), []).append(dict(row))
    result: list[dict[str, Any]] = []
    for signature, candidates in groups.items():
        # Do not merge implausibly different prices even when sparse metadata
        # happens to match.
        clusters: list[list[dict[str, Any]]] = []
        for candidate in sorted(candidates, key=lambda value: float(value.get("price_brl") or 0)):
            price = float(candidate.get("price_brl") or 0)
            matching = next((cluster for cluster in clusters if abs(price - float(cluster[0].get("price_brl") or 0)) <= max(5000, price * .025)), None)
            if matching is None:
                clusters.append([candidate])
            else:
                matching.append(candidate)
        for cluster_index, cluster in enumerate(clusters):
            best = min(cluster, key=lambda value: float(value.get("price_brl") or 0))
            sources = sorted({str(value.get("source") or "") for value in cluster if value.get("source")})
            alternatives = [{"source": value.get("source"), "url": value.get("url"), "price_brl": value.get("price_brl")} for value in cluster]
            merged = dict(best)
            merged["id"] = f"vehicle:{signature}:{cluster_index}"
            merged["sources"] = sources
            merged["source_count"] = len(sources)
            merged["alternatives"] = alternatives
            merged["source"] = sources[0] if len(sources) == 1 else " + ".join(sources)
            result.append(merged)
    return result


def _fetch_sources(config: dict[str, Any], fetcher: Callable[..., Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JeepCommanderMonitor/1.0; low-rate personal search)"}
    for source in build_source_urls(config):
        try:
            response = fetcher(source["url"], headers=headers, timeout=18)
            status = int(getattr(response, "status_code", 0) or 0)
            if status in {403, 429}:
                raise RuntimeError(f"kilden blokkerte forespørselen (HTTP {status})")
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            body = str(getattr(response, "text", "") or "")
            parsed = parse_marketplace_html(
                body, source=source["source"], base_url=source["url"],
                default_seller_type=source.get("default_seller_type", "UKJENT"),
            )
            visible = _plain_text(body).lower()
            explicit_empty = bool(re.search(
                r"(?:^|[.!?])\s*(?:nenhum anúncio|nenhum veículo|não encontramos veículos|0 veículos disponíveis)",
                visible,
            ))
            if not parsed and not explicit_empty:
                raise RuntimeError("ingen lesbare annonser; kildeformatet kan ha blitt endret")
            rows.extend(parsed)
            sources.append({**source, "state": "OK", "parsed": len(parsed), "error": ""})
        except Exception as exc:
            sources.append({**source, "state": "FAILED", "parsed": 0, "error": str(exc)[:300]})
    return rows, sources


def _format_brl(value: Any) -> str:
    try:
        return f"R$ {float(value):,.0f}".replace(",", ".")
    except Exception:
        return "ukjent pris"


def _message(item: dict[str, Any], reason: str) -> str:
    production_year = item.get("production_year")
    model_year = item.get("model_year")
    years = (
        f"{production_year}/{model_year}" if production_year and model_year and production_year != model_year
        else str(model_year or production_year or "år ukjent")
    )
    location = ", ".join(part for part in (item.get("city"), item.get("state")) if part) or "sted ukjent"
    distance = item.get("distance_from_fortaleza_km")
    distance_text = "lokal i Ceará" if item.get("local") else (f"ca. {distance} km (delstatsestimat)" if distance is not None else "avstand ukjent")
    color = item.get("color") or ("sort" if item.get("black") else "farge ikke oppgitt")
    seller_type = {"PRIVAT": "privatannonse", "FORHANDLER": "vanlig forhandler", "UKJENT": "selgertype ikke oppgitt"}.get(str(item.get("seller_type") or "UKJENT"), "selgertype ikke oppgitt")
    if item.get("authorized_jeep"):
        seller_type = "autorisert Jeep-forhandler"
    seller = f" · {item.get('seller_name')}" if item.get("seller_name") else ""
    sources = item.get("sources") or [item.get("source")]
    source_text = ", ".join(str(value) for value in sources if value)
    return (
        f"{reason}\n{item.get('title') or MODULE_NAME}\n"
        f"{years} · {int(item.get('km') or 0):,} km · {color}\n"
        f"{_format_brl(item.get('price_brl'))} · {location} · {distance_text}\n"
        f"{seller_type}{seller} · {len(sources)} kilde(r)\n"
        f"Pris mot median: {float(item.get('price_advantage_pct') or 0):+.1f}% · {source_text}"
    ).replace(",", " ")


def _events(current: list[dict[str, Any]], previous: dict[str, Any], *, first_success: bool) -> list[tuple[dict[str, Any], str]]:
    old = dict(previous.get("listings") or {})
    events: list[tuple[dict[str, Any], str]] = []
    if first_success:
        return events
    old_best = max((float(item.get("value_score") or 0) for item in old.values() if isinstance(item, dict)), default=-1.0)
    for item in current:
        prior = old.get(item["id"])
        if not isinstance(prior, dict):
            reason = "🚙 Nytt treff"
            if float(item.get("value_score") or 0) >= old_best + 8:
                reason = "🏆 Nytt og tydelig bedre tilbud"
            events.append((item, reason))
            continue
        old_price = float(prior.get("price_brl") or 0)
        new_price = float(item.get("price_brl") or 0)
        if old_price > 0 and new_price < old_price:
            cut = (old_price - new_price) / old_price * 100
            if old_price - new_price >= 500 or cut >= 0.3:
                events.append((item, f"💰 Prisfall {_format_brl(old_price)} → {_format_brl(new_price)} (-{cut:.1f}%)"))
                continue
        old_sources = set(prior.get("sources") or [prior.get("source")])
        new_sources = set(item.get("sources") or [item.get("source")])
        added = sorted(str(value) for value in new_sources - old_sources if value)
        if added:
            events.append((item, f"🔎 Samme bil funnet hos ny kilde: {', '.join(added)}"))
    return events


def run_due_monitor(
    *, force: bool = False, notify: bool = True, source: str = "scheduled_cron",
    fetcher: Callable[..., Any] | None = None, sender: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    config = load_config()
    now = _now()
    state = load_state()
    if not config.get("active", True):
        return {"state": "DISABLED", "checked": 0, "sent": 0}
    expires = _parse_time(config.get("expires_at"))
    if expires is not None and now >= expires:
        config["active"] = False
        save_config(config)
        state.update({"state": "EXPIRED", "last_cycle_at": now.isoformat()})
        _save_state(state)
        return {"state": "EXPIRED", "checked": 0, "sent": 0}
    last = _parse_time(state.get("last_cycle_at"))
    if not force and last is not None and (now - last).total_seconds() < INTERVAL_MINUTES * 60:
        return {"state": "NOT_DUE", "next_check_at": (last + timedelta(minutes=INTERVAL_MINUTES)).isoformat(), "checked": 0, "sent": 0}
    with _global_lock() as acquired:
        if not acquired:
            return {"state": "LOCKED", "checked": 0, "sent": 0}
        fetcher = fetcher or requests.get
        sender = sender or send_pushover_alert
        raw_rows, sources = _fetch_sources(config, fetcher)
        successful = [row for row in sources if row["state"] == "OK"]
        if not successful:
            result = {
                **state, "state": "FAILED_SOURCES", "last_cycle_at": now.isoformat(),
                "last_error": "; ".join(f"{row['source']}: {row['error']}" for row in sources)[:1000],
                "sources": sources, "source": source,
            }
            _save_state(result)
            return {"state": "FAILED_SOURCES", "checked": 0, "sent": 0, "sources": sources, "error": result["last_error"]}
        rejection_counts: dict[str, int] = {}
        accepted = []
        for row in raw_rows:
            reason = _target_rejection_reason(row, config)
            if reason:
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            else:
                accepted.append(row)
        current = _enrich_and_rank(_deduplicate_across_sources(accepted))
        first_success = not bool(state.get("baseline_created_at"))
        events = _events(current, state, first_success=first_success)
        pending_map: dict[str, tuple[dict[str, Any], str]] = {}
        for pending in state.get("pending_notifications") or []:
            if not isinstance(pending, dict) or not isinstance(pending.get("listing"), dict):
                continue
            item, reason = dict(pending["listing"]), str(pending.get("reason") or "🚙 Nytt treff")
            key = f"{item.get('id')}:{item.get('price_brl')}:{reason}"
            pending_map[key] = (item, reason)
        for item, reason in events:
            key = f"{item.get('id')}:{item.get('price_brl')}:{reason}"
            pending_map[key] = (item, reason)
        pending = list(pending_map.values())
        sent, send_errors, unsent = 0, [], []
        if notify and config.get("pushover", True):
            for item, reason in pending[:5]:
                ok, detail = normalize_notification_result(sender(
                    _message(item, reason), title=f"🚙 {MODULE_NAME}",
                    url=item["url"], url_title="Åpne bilannonsen",
                ))
                if ok:
                    sent += 1
                else:
                    send_errors.append(str(detail or "ukjent Pushover-feil"))
                    unsent.append((item, reason))
            unsent.extend(pending[5:])
        else:
            unsent = pending
        compact = {
            item["id"]: {key: item.get(key) for key in (
                "id", "source", "title", "url", "price_brl", "km", "years",
                "production_year", "model_year", "color",
                "city", "state", "black", "local", "distance_from_fortaleza_km",
                "price_advantage_pct", "value_score", "seller_name", "seller_type",
                "authorized_jeep", "sources", "source_count", "alternatives",
            )} for item in current[:200]
        }
        result = {
            "state": "DEGRADED" if len(successful) < len(sources) or send_errors else "COMPLETED",
            "last_cycle_at": now.isoformat(), "last_success_at": now.isoformat(),
            "last_automatic_at": now.isoformat() if source == "scheduled_cron" else state.get("last_automatic_at"),
            "next_check_at": (now + timedelta(minutes=INTERVAL_MINUTES)).isoformat(),
            "baseline_created_at": state.get("baseline_created_at") or now.isoformat(),
            "first_run_seeded": first_success, "checked_raw": len(raw_rows), "matches": len(current),
            "new_or_changed": len(events), "sent": sent, "send_errors": send_errors,
            "pending_notifications": [{"listing": item, "reason": reason} for item, reason in unsent[:100]],
            "sources": sources, "listings": compact, "ranked": current[:50], "source": source,
            "rejection_counts": rejection_counts,
            "config_snapshot": {key: config.get(key) for key in ("years", "max_km", "area", "preferred_color", "include_dealer_network")},
            "last_error": "; ".join(send_errors)[:1000],
        }
        _save_state(result)
        return {key: result[key] for key in ("state", "matches", "new_or_changed", "sent", "sources", "first_run_seeded", "next_check_at")}


def render_streamlit_module(st: Any) -> None:
    config = load_config()
    state = load_state()
    st.subheader("🚙 Jeep Commander 2.2")
    st.caption("Midlertidig bruktbilsøk. Egen lagring; påvirker ikke aksjer, Autonomi, rapporter eller læring.")

    years_value = set(config.get("years") or [2025, 2026])
    year_label = st.radio(
        "Modellår", ["2025 og 2026", "Bare 2026", "Bare 2025"], horizontal=True,
        index=0 if years_value == {2025, 2026} else (1 if years_value == {2026} else 2),
        key="jeep_commander_years_v19220_rc1631ch",
    )
    max_km = st.radio(
        "Maks kilometer", [20000, 35000], horizontal=True,
        format_func=lambda value: f"Inntil {value:,} km".replace(",", " "),
        index=1 if int(config.get("max_km") or 20000) == 35000 else 0,
        key="jeep_commander_km_v19220_rc1631ch",
    )
    area_options = {"Fortaleza / Ceará": "CEARA", "Nordøst-Brasil": "NORDESTE", "Hele Brasil": "BRASIL"}
    current_area = next((label for label, value in area_options.items() if value == config.get("area")), "Fortaleza / Ceará")
    area_label = st.selectbox("Søkeområde", list(area_options), index=list(area_options).index(current_area), key="jeep_commander_area_v19220_rc1631ch")
    active = st.toggle("Automatisk søk hvert 15. minutt", value=bool(config.get("active", True)), key="jeep_commander_active_v19220_rc1631ch")
    pushover = st.toggle("Pushover ved nye funn, prisfall eller tydelig bedre tilbud", value=bool(config.get("pushover", True)), key="jeep_commander_push_v19220_rc1631ch")
    other_colors = st.toggle("Ta med andre farger når prisen er bedre", value=bool(config.get("include_other_colors", True)), key="jeep_commander_colors_v19220_rc1631ch")
    dealer_network = st.toggle(
        "Søk også i forhandlernettverk",
        value=bool(config.get("include_dealer_network", True)),
        help="Supplerer Webmotors, OLX og Mobiauto med forhandlernes egne bruktbillister.",
        key="jeep_commander_dealers_v19220_rc1631ci",
    )

    left, right = st.columns(2)
    if left.button("Lagre søkevalg", key="jeep_commander_save_v19220_rc1631ch", width="stretch"):
        years = [2025, 2026] if year_label == "2025 og 2026" else ([2026] if year_label == "Bare 2026" else [2025])
        save_config({**config, "years": years, "max_km": max_km, "area": area_options[area_label], "active": active, "pushover": pushover, "include_other_colors": other_colors, "include_dealer_network": dealer_network})
        st.success("Søkevalgene er lagret og brukes ved neste Cron-kontroll.")
        st.rerun()
    if right.button("Søk nå", key="jeep_commander_scan_v19220_rc1631ch", width="stretch"):
        with st.spinner("Kontrollerer markedsplassene …"):
            result = run_due_monitor(force=True, notify=True, source="manual")
        if result.get("state") == "FAILED_SOURCES":
            st.error(f"Ingen kilde kunne leses. Dette vises som kildefeil, ikke som null treff. {result.get('error', '')}")
        else:
            st.success(f"Kontroll ferdig: {result.get('matches', 0)} gyldige treff, {result.get('sent', 0)} varsler sendt.")
        st.rerun()

    state_name = str(state.get("state") or "NOT_STARTED")
    if state_name == "FAILED_SOURCES":
        st.error(f"Kildefeil: {state.get('last_error') or 'ukjent feil'}")
    elif state_name in {"COMPLETED", "DEGRADED"}:
        st.success(f"Siste søk {state.get('last_success_at')} · {state.get('matches', 0)} treff · neste {state.get('next_check_at')}")
    else:
        st.info("Første søk er ikke kjørt ennå. Første vellykkede kontroll lager en referanse uten varselflom.")

    rows = list(state.get("ranked") or [])
    if rows:
        st.markdown("#### Beste treff")
        for item in rows[:20]:
            title = f"{item.get('title')} · {_format_brl(item.get('price_brl'))} · {int(item.get('km') or 0):,} km".replace(",", " ")
            with st.expander(title):
                st.write(_message(item, "Sort foretrukket" if item.get("black") else "Billigere alternativ farge"))
                st.link_button("Åpne annonsen", item["url"], width="stretch")
                alternatives = list(item.get("alternatives") or [])
                if len(alternatives) > 1:
                    st.caption(f"Samme bil er funnet i {len(alternatives)} annonser. Billigste annonse åpnes over.")
                    st.dataframe(alternatives, width="stretch", hide_index=True)
    st.markdown("#### Kildestatus")
    if state.get("sources"):
        st.dataframe(state["sources"], width="stretch", hide_index=True)
        failed = [row for row in state["sources"] if row.get("state") != "OK"]
        if failed:
            st.warning(f"{len(failed)} kilde(r) kunne ikke kontrolleres. Treffantallet er derfor ikke komplett; se feilen per kilde.")
    if state.get("rejection_counts"):
        st.caption("Annonser som ble lest, men avvist av søkevalgene:")
        st.dataframe(
            [{"Årsak": reason, "Antall": count} for reason, count in state["rejection_counts"].items()],
            width="stretch", hide_index=True,
        )

    st.markdown("#### Midlertidighet")
    st.caption(f"Automatisk utløp: {config.get('expires_at')}. Sletting gjelder bare denne bilmodulen.")
    confirm = st.checkbox("Jeg bekrefter sletting av bilsøket", key="jeep_commander_delete_confirm_v19220_rc1631ch")
    if st.button("Slett Jeep Commander-modulen og søkedata", disabled=not confirm, key="jeep_commander_delete_v19220_rc1631ch"):
        purge_temporary_module()
        st.success("Bilmodulen er deaktivert og alle dens egne søkedata er slettet.")
        st.rerun()
