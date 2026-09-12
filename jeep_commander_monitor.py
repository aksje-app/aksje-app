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
import io
import json
import os
import re
import threading
import zipfile
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests

from durable_runtime import read_json, write_json
from notifier import normalize_notification_result, send_pushover_alert
from storage_architecture import runtime_data_path


MODULE_NAME = "Jeep Commander 2.2"
CONFIG_KEY = "temporary/jeep_commander_22/config.json"
STATE_KEY = "temporary/jeep_commander_22/state.json"
CONFIG_PATH = runtime_data_path("temporary", "jeep_commander_22", "config.json")
STATE_PATH = runtime_data_path("temporary", "jeep_commander_22", "state.json")
INTERVAL_MINUTES = 120
DATAFORSEO_ENDPOINT = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
DATAFORSEO_UNIT_ESTIMATE_USD = 0.020  # observed depth-20 Live cost; reserved before every call
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
        "schema_version": 3,
        "name": MODULE_NAME,
        "active": True,
        "module_mode": "ACTIVE",
        "years": [2025, 2026],
        "max_km": 20000,
        "area": "CEARA",
        "preferred_color": "PRETO",
        "include_other_colors": True,
        "interval_minutes": INTERVAL_MINUTES,
        "night_pause_enabled": True,
        "night_pause_start": 0,
        "night_pause_end": 7,
        "dataforseo_enabled": False,
        "dataforseo_monthly_cap_usd": 12.0,
        "dataforseo_trial_cap_usd": 0.15,
        "pushover": True,
        "include_dealer_network": True,
        "max_pages_per_source": 4,
        "max_detail_checks": 40,
        "manual_urls": [],
        "transport_estimate_brl": 0,
        "fees_estimate_brl": 0,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(days=90)).isoformat(),
    }


def _normalize_config(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    legacy_schema = int(raw.get("schema_version") or 3) < 3
    base = default_config()
    base.update(raw)
    if legacy_schema:
        if int(raw.get("interval_minutes") or 60) == 60:
            base["interval_minutes"] = 120
        if int(raw.get("night_pause_start", 1)) == 1 and int(raw.get("night_pause_end", 6)) == 6:
            base["night_pause_start"], base["night_pause_end"] = 0, 7
        if float(_number(raw.get("dataforseo_monthly_cap_usd")) or 10.0) == 10.0:
            base["dataforseo_monthly_cap_usd"] = 12.0
        if float(_number(raw.get("dataforseo_trial_cap_usd")) or 0.10) == 0.10:
            base["dataforseo_trial_cap_usd"] = 0.15
        base["schema_version"] = 3
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
    interval = int(base.get("interval_minutes") or INTERVAL_MINUTES)
    base["interval_minutes"] = interval if interval in {30, 60, 120} else INTERVAL_MINUTES
    mode = str(raw.get("module_mode") if "module_mode" in raw else ("ACTIVE" if raw.get("active", True) else "PAUSED")).upper()
    base["module_mode"] = mode if mode in {"ACTIVE", "PAUSED", "STOPPED"} else "ACTIVE"
    base["active"] = base["module_mode"] == "ACTIVE"
    base["night_pause_enabled"] = bool(base.get("night_pause_enabled", True))
    base["night_pause_start"] = min(23, max(0, int(base.get("night_pause_start", 0))))
    base["night_pause_end"] = min(23, max(0, int(base.get("night_pause_end", 7))))
    base["dataforseo_enabled"] = bool(base.get("dataforseo_enabled", False))
    base["dataforseo_monthly_cap_usd"] = min(25.0, max(0.10, float(_number(base.get("dataforseo_monthly_cap_usd")) or 12.0)))
    base["dataforseo_trial_cap_usd"] = min(1.0, max(0.01, float(_number(base.get("dataforseo_trial_cap_usd")) or 0.15)))
    base["manual_urls"] = [str(value).strip() for value in base.get("manual_urls") or [] if _valid_url(str(value).strip())][:20]
    base["transport_estimate_brl"] = max(0, int(_number(base.get("transport_estimate_brl")) or 0))
    base["fees_estimate_brl"] = max(0, int(_number(base.get("fees_estimate_brl")) or 0))
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


def _progress(callback: Callable[[str, int, str], None] | None, stage: str, percent: int, detail: str) -> None:
    if callback:
        callback(stage, min(100, max(0, int(percent))), detail)


def _night_pause(config: dict[str, Any], now: datetime) -> tuple[bool, str]:
    if not config.get("night_pause_enabled", True):
        return False, ""
    local = now.astimezone(ZoneInfo("America/Fortaleza"))
    start, end = int(config.get("night_pause_start", 0)), int(config.get("night_pause_end", 7))
    paused = start <= local.hour < end if start < end else (local.hour >= start or local.hour < end)
    return paused, f"Nattpause {start:02d}:00–{end:02d}:00 (Fortaleza); lokal tid {local:%H:%M}"


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
        wm = f"https://www.webmotors.com.br/carros/ce-fortaleza/jeep/commander/22-turbo-diesel-overland-at9/de.{low}/ate.{high}"
        olx_base = "https://www.olx.com.br/autos-e-pecas/carros-vans-e-utilitarios/jeep/commander/overl-22-td-4x4-diesel-aut/{year}/estado-ce"
        mobi_scope = "ce-fortaleza"
        localiza_url = "https://seminovos.localiza.com/carros/ce-fortaleza/jeep/commander?categorias=suv"
    elif area == "NORDESTE":
        wm = f"https://www.webmotors.com.br/carros/regiao-nordeste/jeep/commander/22-turbo-diesel-overland-at9/de.{low}/ate.{high}"
        olx_base = "https://www.olx.com.br/regiao-nordeste/autos-e-pecas/carros-vans-e-utilitarios/jeep/commander/overl-22-td-4x4-diesel-aut/{year}"
        mobi_scope = "brasil"
        localiza_url = "https://seminovos.localiza.com/carros/jeep/commander?categorias=suv"
    else:
        wm = f"https://www.webmotors.com.br/carros/estoque/jeep/commander/22-turbo-diesel-overland-at9/de.{low}/ate.{high}"
        olx_base = "https://www.olx.com.br/autos-e-pecas/carros-vans-e-utilitarios/jeep/commander/overl-22-td-4x4-diesel-aut/{year}/estado-brasil"
        mobi_scope = "brasil"
        localiza_url = "https://seminovos.localiza.com/carros/jeep/commander?categorias=suv"
    sources = [
        {"source": "Webmotors", "query": f"{low}-{high}", "url": wm, "channel": "MARKETPLACE", "default_seller_type": "UKJENT"},
        *({"source": "OLX", "query": str(year), "url": olx_base.format(year=year), "channel": "MARKETPLACE", "default_seller_type": "UKJENT"} for year in years),
        *({"source": "Mobiauto", "query": str(year), "url": f"https://www.mobiauto.com.br/comprar/carros/{mobi_scope}/jeep/commander/ano-{year}", "channel": "MARKETPLACE", "default_seller_type": "UKJENT"} for year in years),
    ]
    if config.get("include_dealer_network", True):
        # Dealer-owned inventories complement the marketplaces. Filtering for
        # year, engine, mileage and geography remains local and identical.
        sources.extend([
            {"source": "Localiza Seminovos", "query": area, "url": localiza_url, "channel": "DEALER_NETWORK", "default_seller_type": "FORHANDLER"},
            {"source": "Seminovos.com.br", "query": area, "url": "https://seminovos.com.br/carros/jeep/commander", "channel": "DEALER_NETWORK", "default_seller_type": "FORHANDLER"},
        ])
    for index, url in enumerate(config.get("manual_urls") or [], 1):
        sources.append({"source": f"Manuell kandidat {index}", "query": "direktelenke", "url": url, "channel": "MANUAL", "default_seller_type": "UKJENT"})
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
    vin = str(_first(item, ("vehicleIdentificationNumber", "vin", "chassis", "chassi")) or "").strip().upper()
    equipment_blob = f"{blob} {description or ''}".lower()
    equipment = {
        "elektrisk_bakluke": any(x in equipment_blob for x in ("porta-malas elétrico", "porta malas elétrico", "electric tailgate")),
        "elektrisk_passasjersete": any(x in equipment_blob for x in ("banco passageiro elétrico", "banco do passageiro elétrico")),
        "panoramatak": any(x in equipment_blob for x in ("teto solar panorâmico", "teto panorâmico", "panoramic")),
        "adas": any(x in equipment_blob for x in ("adas", "piloto automático adaptativo", "frenagem autônoma")),
        "syv_seter": any(x in equipment_blob for x in ("7 lugares", "sete lugares", "7 assentos")),
    }
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
        "vin": vin, "equipment": equipment,
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
        text = f"{item.get('description', '')} {item.get('raw_text', '')}".lower()
        quality_flags = []
        if not item.get("vin"):
            quality_flags.append("chassisnummer ikke oppgitt")
        if not any(token in text for token in ("revisão", "revisoes", "revisões", "histórico de manutenção", "servicehistor")):
            quality_flags.append("servicehistorikk ikke dokumentert")
        if not any(token in text for token in ("garantia", "warranty")):
            quality_flags.append("garanti ikke oppgitt")
        if price < median * .72:
            quality_flags.append("uvanlig lav pris – kontroller annonsen")
        item["quality_flags"] = quality_flags
        # Price dominates; black and local are preferences, never hard gates.
        item["value_score"] = round(
            60 * (max_price - price) / spread + 25 * (1 - min(km, 35000) / 35000)
            + (10 if black else 0) + (5 if local else 0)
            + (3 if item.get("authorized_jeep") else (1 if item.get("seller_type") == "FORHANDLER" else 0))
            + min(3, sum(1 for value in (item.get("equipment") or {}).values() if value)), 2
        )
        ranked.append(item)
    return sorted(ranked, key=lambda row: (-float(row["value_score"]), float(row["price_brl"]), int(row.get("km") or 0)))


def _dedupe_signature(item: dict[str, Any]) -> str:
    """Conservative cross-site identity without inventing a VIN.

    Listings are combined only when model year, exact odometer, location and
    normalized variant agree and prices are close. Distinct cars are therefore
    preferred over an unsafe merge when information is incomplete.
    """
    vin = re.sub(r"[^A-Z0-9]", "", str(item.get("vin") or "").upper())
    if len(vin) >= 11:
        return "vin-" + hashlib.sha256(vin.encode()).hexdigest()[:20]
    title = re.sub(r"\b(?:jeep|commander|diesel|turbo|at9|4x4)\b", " ", str(item.get("title") or "").lower())
    variant = re.sub(r"[^a-z0-9]+", "", title)[:40]
    parts = (
        item.get("production_year"), item.get("model_year"), item.get("km"),
        str(item.get("city") or "").lower().strip(), str(item.get("state") or "").upper(),
        variant, str(item.get("color") or "").lower().strip(),
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


def _pagination_links(content: str, *, base_url: str) -> list[str]:
    """Return explicit same-site pagination links; never guess protected URLs."""
    host = urlparse(base_url).netloc.lower()
    found: list[str] = []
    for match in re.finditer(r"<a\b(?P<attrs>[^>]*href\s*=\s*[\"'][^\"']+[\"'][^>]*)>(?P<body>.*?)</a>", str(content or ""), flags=re.I | re.S):
        label = _plain_text(match.group("body")).strip().lower()
        attrs = match.group("attrs")
        href_match = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", attrs, flags=re.I)
        if not href_match:
            continue
        aria_next = bool(re.search(r"(?:próxima|proxima|next|seguinte)", f"{label} {attrs}", flags=re.I))
        numeric = bool(re.fullmatch(r"\d{1,2}", label))
        if not (aria_next or numeric):
            continue
        url = urljoin(base_url, html_lib.unescape(href_match.group(1)))
        parsed = urlparse(url)
        if parsed.netloc.lower() == host and url != base_url and url not in found:
            found.append(url)
    return found


def _merge_detail(summary: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(summary)
    for key in ("description", "raw_text", "color", "city", "state", "seller_name", "seller_type", "vin"):
        if detail.get(key) not in (None, "", [], {}):
            merged[key] = detail[key]
    for key in ("km", "production_year", "model_year", "years"):
        if merged.get(key) in (None, "", [], {}) and detail.get(key) not in (None, "", [], {}):
            merged[key] = detail[key]
    merged["authorized_jeep"] = bool(summary.get("authorized_jeep") or detail.get("authorized_jeep"))
    merged["equipment"] = {
        key: bool(value or (detail.get("equipment") or {}).get(key))
        for key, value in (summary.get("equipment") or {}).items()
    } or dict(detail.get("equipment") or {})
    merged["detail_checked"] = True
    return merged


def dataforseo_credentials_ready() -> bool:
    return bool(os.getenv("DATAFORSEO_LOGIN", "").strip() and os.getenv("DATAFORSEO_PASSWORD", "").strip())


def _dataforseo_queries(config: dict[str, Any]) -> list[dict[str, str]]:
    years = sorted(int(value) for value in config.get("years") or [2025, 2026])
    year_terms = " OR ".join(f'\"{year}\"' for year in years)
    area = str(config.get("area") or "CEARA")
    place = {"CEARA": "Ceará Fortaleza", "NORDESTE": "Nordeste Brasil", "BRASIL": "Brasil"}[area]
    core = f'\"Jeep Commander\" \"2.2\" diesel ({year_terms}) {place}'
    return [
        {"source": "DataForSEO → Webmotors", "domain": "webmotors.com.br", "keyword": f"site:webmotors.com.br/comprar/jeep/commander {core}"},
        {"source": "DataForSEO → OLX", "domain": "olx.com.br", "keyword": f"site:olx.com.br/autos-e-pecas {core} R$ km"},
    ]


def _dataforseo_candidate(item: dict[str, Any], *, source: str, domain: str) -> dict[str, Any] | None:
    url = str(item.get("url") or item.get("link") or "").strip()
    parsed = urlparse(url)
    if not _valid_url(url) or domain not in parsed.netloc.lower():
        return None
    # OLX commonly uses a descriptive slug ending in a long numeric listing id.
    olx_numeric_ad = domain == "olx.com.br" and bool(re.search(r"-[0-9]{7,}/?$", parsed.path.lower()))
    if not olx_numeric_ad and not any(token in parsed.path.lower() for token in ("/anuncio", "/ad/", "/comprar/", "/carro/", "/veiculo/")):
        return None
    title = html_lib.unescape(str(item.get("title") or "")).strip()
    description = html_lib.unescape(str(item.get("description") or item.get("snippet") or "")).strip()
    blob = f"{title} {description}"
    if "commander" not in blob.lower():
        return None
    price_matches = re.findall(r"R\$\s*([0-9]{1,3}(?:[.]?[0-9]{3})+)", blob, flags=re.I)
    km_match = re.search(r"\b([0-9]{1,3}(?:[.]?[0-9]{3})*)\s*km\b", blob, flags=re.I)
    city, state = _location(blob)
    production_year, model_year, years = _vehicle_years({}, blob)
    raw_id = hashlib.sha256(url.split("?", 1)[0].encode()).hexdigest()[:20]
    return {
        "id": f"{source.lower()}:{raw_id}", "source": source, "title": title or MODULE_NAME,
        "description": description, "raw_text": blob, "url": url,
        "price_brl": int(_number(price_matches[-1]) or 0) if price_matches else None,
        "km": int(_number(km_match.group(1)) or 0) if km_match else None,
        "years": years, "production_year": production_year, "model_year": model_year,
        "color": next((name for name in ("Preto", "Branco", "Cinza", "Prata", "Azul", "Vermelho") if name.lower() in blob.lower()), ""),
        "city": city, "state": state, "seller_name": "", "seller_type": "UKJENT",
        "authorized_jeep": False, "discovery_channel": "SEARCH_INDEX",
    }


def _dataforseo_item_diagnostic(item: dict[str, Any], *, source: str, domain: str) -> dict[str, Any]:
    """Explain exactly why one organic search result was accepted or rejected."""
    url = str(item.get("url") or item.get("link") or "").strip()
    title = html_lib.unescape(str(item.get("title") or "")).strip()
    description = html_lib.unescape(str(item.get("description") or item.get("snippet") or "")).strip()
    parsed = urlparse(url)
    reason = "GODKJENT_INDIVIDUELL_ANNONSE"
    if not _valid_url(url):
        reason = "UGYLDIG_ELLER_MANGLENDE_URL"
    elif domain not in parsed.netloc.lower():
        reason = "FEIL_DOMENE"
    elif not (domain == "olx.com.br" and re.search(r"-[0-9]{7,}/?$", parsed.path.lower())) and not any(token in parsed.path.lower() for token in ("/anuncio", "/ad/", "/comprar/", "/carro/", "/veiculo/")):
        reason = "URL_IKKE_GJENKJENT_SOM_ENKELTANNONSE"
    elif "commander" not in f"{title} {description}".lower():
        reason = "COMMANDER_MANGLER_I_TITTEL_OG_UTDRAG"
    accepted = reason == "GODKJENT_INDIVIDUELL_ANNONSE"
    return {
        "source": source, "accepted": accepted, "decision": "GODKJENT" if accepted else "FORKASTET",
        "reason": reason, "result_type": str(item.get("type") or ""),
        "domain": parsed.netloc.lower(), "path": parsed.path,
        "url": url, "title": title[:500], "description": description[:1000],
    }


def build_dataforseo_diagnostic_zip(validation: dict[str, Any], usage: dict[str, Any] | None = None) -> bytes:
    """Create a credential-free diagnostic archive suitable for support."""
    safe = {
        "module": MODULE_NAME, "generated_at": _now().isoformat(),
        "app_version": __import__("app_version").APP_VERSION,
        "validation": validation, "usage": dict(usage or {}),
        "security": "API-login, API-passord, HTTP-headere og autentisering er ikke inkludert.",
    }
    encoded = json.dumps(safe, ensure_ascii=False, indent=2, default=str)
    for secret in (value for value in (os.getenv("DATAFORSEO_LOGIN", ""), os.getenv("DATAFORSEO_PASSWORD", "")) if value):
        encoded = encoded.replace(secret, "[FJERNET]")
    summary = [
        "Jeep Commander 2.2 – DataForSEO-diagnose",
        f"Versjon: {safe['app_version']}", f"Tid: {safe['generated_at']}",
        f"Godkjent: {bool(validation.get('passed'))}",
        f"OLX individuelle annonser: {(validation.get('counts') or {}).get('olx', 0)}",
        f"Webmotors individuelle annonser: {(validation.get('counts') or {}).get('webmotors', 0)}",
        f"Organiske resultater: {sum(int(row.get('organic_items') or 0) for row in validation.get('sources') or [])}",
        f"Forkastede resultater: {sum(int(row.get('rejected_items') or 0) for row in validation.get('sources') or [])}",
        "Ingen API-hemmeligheter er inkludert.",
    ]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("LES_MEG.txt", "\n".join(summary) + "\n")
        archive.writestr("dataforseo_diagnose.json", encoded)
    return output.getvalue()


def _dataforseo_month_usage(state: dict[str, Any], now: datetime) -> tuple[str, float]:
    month = now.strftime("%Y-%m")
    usage = state.get("dataforseo_usage") if isinstance(state.get("dataforseo_usage"), dict) else {}
    return month, float(usage.get("estimated_usd") or 0) if usage.get("month") == month else 0.0


def _fetch_dataforseo(
    config: dict[str, Any], state: dict[str, Any], *, post: Callable[..., Any], validation: bool = False,
    progress: Callable[[str, int, str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    now = _now()
    month, used = _dataforseo_month_usage(state, now)
    queries = _dataforseo_queries(config)
    cap = float(config.get("dataforseo_trial_cap_usd") if validation else config.get("dataforseo_monthly_cap_usd") or 0)
    if not dataforseo_credentials_ready():
        return [], [{"source": row["source"], "channel": "SEARCH_INDEX", "state": "NOT_CONFIGURED", "parsed": 0, "error": "DATAFORSEO_LOGIN/PASSWORD mangler"} for row in queries], {"month": month, "estimated_usd": used, "calls": 0}
    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    running_cost = used
    calls = 0
    auth = (os.getenv("DATAFORSEO_LOGIN", "").strip(), os.getenv("DATAFORSEO_PASSWORD", "").strip())
    for index, query in enumerate(queries):
        # The Live endpoint/account accepts one task per request.  Enforce the
        # cap before every request so a successful first source can never make
        # the second source overspend the configured limit.
        if running_cost + DATAFORSEO_UNIT_ESTIMATE_USD > cap + 1e-9:
            source_rows.append({"source": query["source"], "query": query["keyword"], "channel": "SEARCH_INDEX", "state": "COST_CAP", "parsed": 0, "organic_items": 0, "error": f"kostnadssperre ${cap:.2f}"})
            continue
        payload = [{"keyword": query["keyword"], "location_name": "Brazil", "language_code": "pt", "device": "desktop", "depth": 20}]
        try:
            _progress(progress, "DATAFORSEO", 64 + index * 14, f"Søker {query['source']} ({index + 1}/{len(queries)})")
            calls += 1
            response = post(DATAFORSEO_ENDPOINT, auth=auth, json=payload, timeout=30)
            status = int(getattr(response, "status_code", 0) or 0)
            if status != 200:
                raise RuntimeError(f"DataForSEO HTTP {status}")
            data = response.json()
            tasks = data.get("tasks") if isinstance(data, dict) else None
            if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
                raise RuntimeError("DataForSEO-svar mangler én gyldig task")
            task = tasks[0]
            task_cost = float(task.get("cost") or DATAFORSEO_UNIT_ESTIMATE_USD)
            running_cost += task_cost
            _progress(progress, "DATAFORSEO_RESULT", 72 + index * 14, f"Tolker {query['source']}")
            task_status = int(task.get("status_code") or 0)
            items: list[dict[str, Any]] = []
            for result in task.get("result") or []:
                if isinstance(result, dict):
                    items.extend(value for value in result.get("items") or [] if isinstance(value, dict) and value.get("type") == "organic")
            diagnostics = [_dataforseo_item_diagnostic(value, source=query["source"], domain=query["domain"]) for value in items]
            candidates = [candidate for value in items if (candidate := _dataforseo_candidate(value, source=query["source"], domain=query["domain"]))]
            rows.extend(candidates)
            ok = task_status in {20000, 0} and bool(task)
            source_rows.append({
                "source": query["source"], "query": query["keyword"], "channel": "SEARCH_INDEX",
                "state": "OK" if ok else "FAILED", "parsed": len(candidates), "organic_items": len(items),
                "accepted_items": sum(1 for row in diagnostics if row["accepted"]),
                "rejected_items": sum(1 for row in diagnostics if not row["accepted"]),
                "diagnostics": diagnostics,
                "task_status_code": task_status, "task_status_message": str(task.get("status_message") or "")[:300],
                "error": "" if ok else str(task.get("status_message") or "ugyldig API-svar")[:300],
            })
        except Exception as exc:
            source_rows.append({"source": query["source"], "query": query["keyword"], "channel": "SEARCH_INDEX", "state": "FAILED", "parsed": 0, "organic_items": 0, "error": str(exc)[:300]})
    return rows, source_rows, {
        "month": month, "estimated_usd": round(running_cost, 6),
        "last_cost_usd": round(max(0.0, running_cost - used), 6), "calls": calls,
    }


def _fetch_sources(
    config: dict[str, Any], fetcher: Callable[..., Any],
    progress: Callable[[str, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    detail_budget = max(0, min(80, int(config.get("max_detail_checks") or 40)))
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JeepCommanderMonitor/1.0; low-rate personal search)"}
    source_list = build_source_urls(config)
    for source_index, source in enumerate(source_list):
        if cancel_check and cancel_check():
            sources.append({"source": source["source"], "channel": source.get("channel"), "state": "CANCELLED", "parsed": 0, "error": "Jobben ble stoppet før denne kilden"})
            break
        _progress(progress, "SOURCE", 10 + int(52 * source_index / max(1, len(source_list))), f"Leser {source['source']} ({source_index + 1}/{len(source_list)})")
        try:
            queue = [source["url"]]
            visited: set[str] = set()
            source_rows: dict[str, dict[str, Any]] = {}
            max_pages = max(1, min(6, int(config.get("max_pages_per_source") or 4)))
            while queue and len(visited) < max_pages:
                page_url = queue.pop(0)
                if page_url in visited:
                    continue
                response = fetcher(page_url, headers=headers, timeout=18)
                status = int(getattr(response, "status_code", 0) or 0)
                if status in {403, 429}:
                    raise RuntimeError(f"kilden blokkerte forespørselen (HTTP {status})")
                if status != 200:
                    raise RuntimeError(f"HTTP {status}")
                body = str(getattr(response, "text", "") or "")
                parsed = parse_marketplace_html(
                    body, source=source["source"], base_url=page_url,
                    default_seller_type=source.get("default_seller_type", "UKJENT"),
                )
                visible = _plain_text(body).lower()
                explicit_empty = bool(re.search(
                    r"(?:nenhum anúncio|nenhum veículo|não encontramos veículos|0 veículos disponíveis|nenhum resultado)",
                    visible,
                ))
                if not parsed and not explicit_empty and not visited:
                    raise RuntimeError("ingen lesbare annonser; kildeformatet kan ha blitt endret")
                visited.add(page_url)
                for item in parsed:
                    source_rows[item["id"]] = item
                for url in _pagination_links(body, base_url=page_url):
                    if url not in visited and url not in queue:
                        queue.append(url)
            detail_checked = 0
            for listing_id, item in list(source_rows.items()):
                if detail_budget <= 0 or not _valid_url(str(item.get("url") or "")):
                    break
                try:
                    detail_response = fetcher(item["url"], headers=headers, timeout=18)
                    if int(getattr(detail_response, "status_code", 0) or 0) != 200:
                        continue
                    detail_rows = parse_marketplace_html(
                        str(getattr(detail_response, "text", "") or ""), source=source["source"],
                        base_url=item["url"], default_seller_type=source.get("default_seller_type", "UKJENT"),
                    )
                    if detail_rows:
                        same = next((value for value in detail_rows if value.get("url") == item.get("url")), detail_rows[0])
                        source_rows[listing_id] = _merge_detail(item, same)
                    detail_checked += 1
                    detail_budget -= 1
                except Exception:
                    continue
            rows.extend(source_rows.values())
            sources.append({**source, "state": "OK", "parsed": len(source_rows), "pages_fetched": len(visited), "details_checked": detail_checked, "error": ""})
        except Exception as exc:
            sources.append({**source, "state": "FAILED", "parsed": 0, "pages_fetched": 0, "error": str(exc)[:300]})
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
    first_price = float(item.get("first_price_brl") or item.get("price_brl") or 0)
    previous_price = float(item.get("previous_price_brl") or item.get("price_brl") or 0)
    current_price = float(item.get("price_brl") or 0)
    price_line = ""
    if previous_price and current_price != previous_price:
        delta = current_price - previous_price
        pct = delta / previous_price * 100
        price_line = f"\nForrige → ny: {_format_brl(previous_price)} → {_format_brl(current_price)} ({_format_brl(abs(delta))} {'opp' if delta > 0 else 'ned'} / {pct:+.2f}%)"
    history_line = f"\nFørst funnet: {item.get('first_seen_at')} · første pris {_format_brl(first_price)}" if item.get("first_seen_at") else ""
    total_cost = int(item.get("estimated_total_brl") or current_price)
    total_line = f"\nEstimert totalt til Fortaleza: {_format_brl(total_cost)}" if total_cost > current_price else ""
    equipment = [name.replace("_", " ") for name, present in (item.get("equipment") or {}).items() if present]
    equipment_line = f"\nUtstyr funnet: {', '.join(equipment)}" if equipment else ""
    quality_line = f"\nKontroller: {'; '.join(item.get('quality_flags') or [])}" if item.get("quality_flags") else ""
    return (
        f"{reason}\n{item.get('title') or MODULE_NAME}\n"
        f"{years} · {int(item.get('km') or 0):,} km · {color}\n"
        f"{_format_brl(item.get('price_brl'))} · {location} · {distance_text}{price_line}{history_line}{total_line}{equipment_line}{quality_line}\n"
        f"{seller_type}{seller} · {len(sources)} kilde(r)\n"
        f"Pris mot median: {float(item.get('price_advantage_pct') or 0):+.1f}% · {source_text}"
    ).replace(",", " ")


def _apply_listing_history(current: list[dict[str, Any]], previous: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    old = dict(previous.get("listings") or {})
    enriched: list[dict[str, Any]] = []
    for raw in current:
        item = dict(raw)
        prior = old.get(item["id"]) if isinstance(old.get(item["id"]), dict) else {}
        price = int(item.get("price_brl") or 0)
        prior_price = int(prior.get("price_brl") or price)
        history = [dict(value) for value in prior.get("price_history") or [] if isinstance(value, dict)]
        if not history:
            history.append({"at": prior.get("first_seen_at") or now.isoformat(), "price_brl": int(prior.get("first_price_brl") or prior_price)})
        if price != prior_price:
            history.append({"at": now.isoformat(), "price_brl": price})
        item.update({
            "first_seen_at": prior.get("first_seen_at") or now.isoformat(),
            "last_seen_at": now.isoformat(),
            "first_price_brl": int(prior.get("first_price_brl") or prior_price or price),
            "previous_price_brl": prior_price,
            "last_price_change_at": now.isoformat() if price != prior_price else prior.get("last_price_change_at"),
            "price_history": history[-30:],
        })
        enriched.append(item)
    return enriched


def _events(current: list[dict[str, Any]], previous: dict[str, Any], *, first_success: bool) -> list[tuple[dict[str, Any], str]]:
    old = dict(previous.get("listings") or {})
    events: list[tuple[dict[str, Any], str]] = []
    if first_success:
        return events
    old_best = max((float(item.get("value_score") or 0) for item in old.values() if isinstance(item, dict)), default=-1.0)
    for item in current:
        prior = old.get(item["id"])
        if not isinstance(prior, dict):
            reason = "🔵🆕 Nytt treff"
            if float(item.get("value_score") or 0) >= old_best + 8:
                reason = "🟣🏆 Nytt og tydelig bedre tilbud"
            events.append((item, reason))
            continue
        old_price = float(prior.get("price_brl") or 0)
        new_price = float(item.get("price_brl") or 0)
        if old_price > 0 and new_price < old_price:
            cut = (old_price - new_price) / old_price * 100
            if old_price - new_price >= 500 or cut >= 0.3:
                events.append((item, f"🟢⬇️ Prisfall {_format_brl(old_price)} → {_format_brl(new_price)} (-{_format_brl(old_price-new_price)} / -{cut:.2f}%)"))
                continue
        if old_price > 0 and new_price > old_price:
            rise = (new_price - old_price) / old_price * 100
            if new_price - old_price >= 500 or rise >= 0.3:
                events.append((item, f"🔴⬆️ Prisøkning {_format_brl(old_price)} → {_format_brl(new_price)} (+{_format_brl(new_price-old_price)} / +{rise:.2f}%)"))
                continue
        old_sources = set(prior.get("sources") or [prior.get("source")])
        new_sources = set(item.get("sources") or [item.get("source")])
        added = sorted(str(value) for value in new_sources - old_sources if value)
        if added:
            events.append((item, f"🟣🔎 Samme bil funnet hos ny kilde: {', '.join(added)}"))
    return events


def _availability_events(
    current: list[dict[str, Any]], previous: dict[str, Any], successful_sources: set[str],
) -> tuple[list[tuple[dict[str, Any], str]], dict[str, Any]]:
    old = {key: value for key, value in (previous.get("listings") or {}).items() if isinstance(value, dict)}
    missing = {key: dict(value) for key, value in (previous.get("missing_listings") or {}).items() if isinstance(value, dict)}
    current_ids = {item["id"] for item in current}
    events: list[tuple[dict[str, Any], str]] = []
    for item in current:
        if item["id"] in missing:
            events.append((item, "🔵↩️ Annonsen er publisert igjen"))
            missing.pop(item["id"], None)
    for item_id, item in old.items():
        if item_id in current_ids:
            continue
        item_sources = {str(value) for value in item.get("sources") or [item.get("source")] if value}
        if item_sources and not item_sources.issubset(successful_sources):
            continue
        entry = dict(missing.get(item_id) or {"listing": item, "misses": 0, "alerted": False})
        entry["misses"] = int(entry.get("misses") or 0) + 1
        if entry["misses"] >= 2 and not entry.get("alerted"):
            events.append((dict(entry.get("listing") or item), "⚫❌ Annonsen er borte eller markert solgt etter to komplette kontroller"))
            entry["alerted"] = True
        missing[item_id] = entry
    return events, missing


def run_due_monitor(
    *, force: bool = False, notify: bool = True, source: str = "scheduled_cron",
    fetcher: Callable[..., Any] | None = None, sender: Callable[..., Any] | None = None,
    dataforseo_post: Callable[..., Any] | None = None,
    progress: Callable[[str, int, str], None] | None = None,
) -> dict[str, Any]:
    config = load_config()
    now = _now()
    state = load_state()
    mode = str(config.get("module_mode") or "ACTIVE")
    _progress(progress, "START", 2, "Kontrollerer modulstatus og tidsplan")
    if mode == "STOPPED":
        return {"state": "STOPPED", "checked": 0, "sent": 0}
    if mode == "PAUSED" and source == "scheduled_cron":
        return {"state": "PAUSED", "checked": 0, "sent": 0}
    night_paused, night_reason = _night_pause(config, now)
    if source == "scheduled_cron" and night_paused:
        previous_skip = _parse_time(state.get("last_night_skip_at"))
        interval = int(config.get("interval_minutes") or INTERVAL_MINUTES)
        newly_skipped = previous_skip is None or (now - previous_skip).total_seconds() >= interval * 60
        skipped = int(state.get("night_skipped_cycles") or 0) + (1 if newly_skipped else 0)
        local = now.astimezone(ZoneInfo("America/Fortaleza"))
        end_local = local.replace(hour=int(config.get("night_pause_end", 7)), minute=0, second=0, microsecond=0)
        if end_local <= local:
            end_local += timedelta(days=1)
        state.update({"state": "NIGHT_PAUSE", "night_skipped_cycles": skipped, "last_skip_reason": night_reason, "next_check_at": end_local.astimezone(timezone.utc).isoformat()})
        if newly_skipped:
            state["last_night_skip_at"] = now.isoformat()
        _save_state(state)
        return {"state": "NIGHT_PAUSE", "checked": 0, "sent": 0, "reason": night_reason, "night_skipped_cycles": skipped, "next_check_at": state["next_check_at"]}
    expires = _parse_time(config.get("expires_at"))
    if expires is not None and now >= expires:
        config["active"] = False
        save_config(config)
        state.update({"state": "EXPIRED", "last_cycle_at": now.isoformat()})
        _save_state(state)
        return {"state": "EXPIRED", "checked": 0, "sent": 0}
    last = _parse_time(state.get("last_cycle_at"))
    interval_minutes = int(config.get("interval_minutes") or INTERVAL_MINUTES)
    if not force and last is not None and (now - last).total_seconds() < interval_minutes * 60:
        return {"state": "NOT_DUE", "next_check_at": (last + timedelta(minutes=interval_minutes)).isoformat(), "checked": 0, "sent": 0}
    with _global_lock() as acquired:
        if not acquired:
            return {"state": "LOCKED", "checked": 0, "sent": 0}
        fetcher = fetcher or requests.get
        sender = sender or send_pushover_alert
        _progress(progress, "DIRECT_SOURCES", 8, "Starter direkte markedsplass- og forhandlersøk")
        def cancelled() -> bool:
            latest = load_config()
            return str(latest.get("module_mode") or "ACTIVE") == "STOPPED" or bool(latest.get("cancel_requested"))
        raw_rows, sources = _fetch_sources(config, fetcher, progress=progress, cancel_check=cancelled)
        if cancelled():
            state.update({"state": "CANCELLED", "last_cycle_at": now.isoformat(), "sources": sources})
            _save_state(state)
            return {"state": "CANCELLED", "checked": len(raw_rows), "sent": 0, "sources": sources}
        dataforseo_usage = state.get("dataforseo_usage") or {}
        dataforseo_ran = False
        if config.get("dataforseo_enabled") and state.get("dataforseo_validation_passed"):
            indexed, indexed_sources, dataforseo_usage = _fetch_dataforseo(
                config, state, post=dataforseo_post or requests.post, validation=False, progress=progress,
            )
            raw_rows.extend(indexed)
            sources.extend(indexed_sources)
            dataforseo_ran = any(row.get("state") == "OK" for row in indexed_sources)
        successful = [row for row in sources if row["state"] == "OK"]
        if not successful:
            result = {
                **state, "state": "FAILED_SOURCES", "last_cycle_at": now.isoformat(),
                "last_error": "; ".join(f"{row['source']}: {row['error']}" for row in sources)[:1000],
                "sources": sources, "source": source,
            }
            _save_state(result)
            return {"state": "FAILED_SOURCES", "checked": 0, "sent": 0, "sources": sources, "error": result["last_error"]}
        _progress(progress, "FILTER", 84, "Kontrollerer modell, år, kilometer, sted og pris")
        rejection_counts: dict[str, int] = {}
        accepted = []
        for row in raw_rows:
            reason = _target_rejection_reason(row, config)
            if reason:
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            else:
                accepted.append(row)
        _progress(progress, "RANK", 89, "Fjerner duplikater og sammenligner pris og kvalitet")
        current = _enrich_and_rank(_deduplicate_across_sources(accepted))
        for item in current:
            transport = 0 if item.get("local") else int(config.get("transport_estimate_brl") or 0)
            item["estimated_transport_brl"] = transport
            item["estimated_fees_brl"] = int(config.get("fees_estimate_brl") or 0)
            item["estimated_total_brl"] = int(item.get("price_brl") or 0) + transport + item["estimated_fees_brl"]
        current = _apply_listing_history(current, state, now)
        first_success = not bool(state.get("baseline_created_at"))
        events = _events(current, state, first_success=first_success)
        dataforseo_first_baseline = dataforseo_ran and not bool(state.get("dataforseo_baseline_created_at"))
        if dataforseo_first_baseline:
            events = [
                (item, reason) for item, reason in events
                if not any(str(value).startswith("DataForSEO") for value in item.get("sources") or [item.get("source")])
            ]
        availability_events, missing_listings = _availability_events(
            current, state, {str(row.get("source")) for row in successful if row.get("channel") != "SEARCH_INDEX"},
        )
        if not first_success:
            events.extend(availability_events)
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
        _progress(progress, "NOTIFY", 94, "Kontrollerer nye funn og prisendringer")
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
                "vin", "equipment", "first_seen_at", "last_seen_at", "first_price_brl",
                "previous_price_brl", "last_price_change_at", "price_history",
                "quality_flags", "estimated_transport_brl", "estimated_fees_brl", "estimated_total_brl",
            )} for item in current[:200]
        }
        result = {
            "state": "DEGRADED" if len(successful) < len(sources) or send_errors else "COMPLETED",
            "last_cycle_at": now.isoformat(), "last_success_at": now.isoformat(),
            "last_automatic_at": now.isoformat() if source == "scheduled_cron" else state.get("last_automatic_at"),
            "next_check_at": (now + timedelta(minutes=interval_minutes)).isoformat(),
            "baseline_created_at": state.get("baseline_created_at") or now.isoformat(),
            "first_run_seeded": first_success, "checked_raw": len(raw_rows), "matches": len(current),
            "new_or_changed": len(events), "sent": sent, "send_errors": send_errors,
            "pending_notifications": [{"listing": item, "reason": reason} for item, reason in unsent[:100]],
            "missing_listings": missing_listings,
            "sources": sources, "listings": compact, "ranked": current[:50], "source": source,
            "rejection_counts": rejection_counts,
            "dataforseo_usage": dataforseo_usage,
            "dataforseo_validation_passed": bool(state.get("dataforseo_validation_passed")),
            "dataforseo_validation": state.get("dataforseo_validation") or {},
            "dataforseo_baseline_created_at": (now.isoformat() if dataforseo_first_baseline else state.get("dataforseo_baseline_created_at")),
            "config_snapshot": {key: config.get(key) for key in ("years", "max_km", "area", "preferred_color", "include_dealer_network")},
            "last_error": "; ".join(send_errors)[:1000],
        }
        _save_state(result)
        _progress(progress, "DONE", 100, f"Ferdig: {len(current)} gyldige treff, {sent} varsler")
        return {key: result[key] for key in ("state", "matches", "new_or_changed", "sent", "sources", "first_run_seeded", "next_check_at")}


def validate_dataforseo(*, post: Callable[..., Any] | None = None, progress: Callable[[str, int, str], None] | None = None) -> dict[str, Any]:
    """One quiet, cost-capped proof run. It never sends Pushover."""
    config, state = load_config(), load_state()
    _progress(progress, "START", 5, "Kontrollerer API-oppsett og kostnadssperre")
    rows, sources, usage = _fetch_dataforseo(config, state, post=post or requests.post, validation=True, progress=progress)
    counts = {
        "olx": sum(1 for row in rows if "olx.com.br" in urlparse(str(row.get("url") or "")).netloc.lower()),
        "webmotors": sum(1 for row in rows if "webmotors.com.br" in urlparse(str(row.get("url") or "")).netloc.lower()),
    }
    passed = counts["olx"] > 0 and counts["webmotors"] > 0 and all(row.get("state") == "OK" for row in sources)
    validation = {
        "passed": passed, "at": _now().isoformat(), "counts": counts,
        "individual_urls": len(rows), "complete_candidates": sum(1 for row in rows if not _target_rejection_reason(row, {**config, "area": "BRASIL"})),
        "pushover_sent": 0, "sources": sources,
        "message": "Godkjent: individuelle OLX- og Webmotors-lenker funnet." if passed else "Ikke godkjent: begge markedsplassene må gi minst én individuell annonselenke.",
    }
    state.update({"dataforseo_validation_passed": passed, "dataforseo_validation": validation, "dataforseo_usage": usage})
    _save_state(state)
    _progress(progress, "DONE", 100, validation["message"])
    return validation


def render_streamlit_module(st: Any) -> None:
    config = load_config()
    state = load_state()
    st.markdown("""
    <style>
    div[data-testid="stExpander"] {background:#071525 !important;border:1px solid #29445f !important;border-radius:12px;}
    div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary * {color:#f4f8fc !important;background:transparent !important;}
    .jeep-result-card {background:#0b1d30;color:#f4f8fc;border:1px solid #31516f;border-radius:10px;padding:14px 16px;line-height:1.55;}
    .jeep-result-card strong {color:#62d6ff;}.jeep-result-card .price {color:#70e29b;font-size:1.15rem;font-weight:800;}
    .jeep-result-card .muted {color:#c3d1df;}.jeep-result-card * {background:transparent !important;}
    </style>
    """, unsafe_allow_html=True)
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
    mode_labels = {"Aktiv": "ACTIVE", "Pauset – behold historikk": "PAUSED", "Stoppet – ingen søk eller varsler": "STOPPED"}
    current_mode_label = next((label for label, value in mode_labels.items() if value == config.get("module_mode")), "Aktiv")
    mode_label = st.radio(
        "Driftstilstand", list(mode_labels), horizontal=True, index=list(mode_labels).index(current_mode_label),
        help="Pauset stopper automatiske kjøringer, men tillater Søk nå. Stoppet blokkerer alle søk og varsler. Historikken beholdes i begge tilfeller.",
        key="jeep_commander_mode_v19220_rc1631cl",
    )
    mode_actions = st.columns(3)
    if mode_actions[0].button("▶️ Aktiver nå", key="jeep_mode_active_now_v19220_rc1631cl", width="stretch"):
        save_config({**config, "module_mode": "ACTIVE", "active": True, "cancel_requested": False}); st.rerun()
    if mode_actions[1].button("⏸ Pause nå", key="jeep_mode_pause_now_v19220_rc1631cl", width="stretch"):
        save_config({**config, "module_mode": "PAUSED", "active": False}); st.rerun()
    if mode_actions[2].button("⏹ Stopp nå", key="jeep_mode_stop_now_v19220_rc1631cl", width="stretch"):
        save_config({**config, "module_mode": "STOPPED", "active": False}); st.rerun()
    interval_minutes = st.radio(
        "Søkeintervall", [120, 60, 30], horizontal=True,
        format_func=lambda value: "Hver 2. time" if value == 120 else f"Hvert {value}. minutt",
        index=[120, 60, 30].index(int(config.get("interval_minutes") or 120)),
        key="jeep_commander_interval_v19220_rc1631ck",
    )
    active = mode_labels[mode_label] == "ACTIVE"
    pushover = st.toggle("Pushover ved nye funn, prisfall eller tydelig bedre tilbud", value=bool(config.get("pushover", True)), key="jeep_commander_push_v19220_rc1631ch")
    other_colors = st.toggle("Ta med andre farger når prisen er bedre", value=bool(config.get("include_other_colors", True)), key="jeep_commander_colors_v19220_rc1631ch")
    dealer_network = st.toggle(
        "Søk også i forhandlernettverk",
        value=bool(config.get("include_dealer_network", True)),
        help="Supplerer Webmotors, OLX og Mobiauto med forhandlernes egne bruktbillister.",
        key="jeep_commander_dealers_v19220_rc1631ci",
    )
    night_pause_enabled = st.toggle(
        "Nattpause for automatiske søk (Fortaleza-tid)", value=bool(config.get("night_pause_enabled", True)),
        key="jeep_commander_night_pause_v19220_rc1631cl",
    )
    night_left, night_right = st.columns(2)
    night_start = night_left.number_input("Pause fra kl.", min_value=0, max_value=23, value=int(config.get("night_pause_start", 0)), step=1, disabled=not night_pause_enabled, key="jeep_night_start_v19220_rc1631co")
    night_end = night_right.number_input("Start igjen kl.", min_value=0, max_value=23, value=int(config.get("night_pause_end", 7)), step=1, disabled=not night_pause_enabled, key="jeep_night_end_v19220_rc1631co")
    credentials_ready = dataforseo_credentials_ready()
    validation = state.get("dataforseo_validation") if isinstance(state.get("dataforseo_validation"), dict) else {}
    validated = bool(state.get("dataforseo_validation_passed"))
    dataforseo_enabled = st.toggle(
        "Bruk DataForSEO for OLX og Webmotors",
        value=bool(config.get("dataforseo_enabled", False)),
        disabled=not (credentials_ready and validated),
        help="Kan først aktiveres etter en vellykket, stille test. Søkeindeksen erstatter ikke en garanti om komplett lager.",
        key="jeep_commander_dataforseo_v19220_rc1631ck",
    )
    dataforseo_monthly_cap = st.number_input(
        "Maks estimert DataForSEO-bruk per måned (USD)", min_value=1.0, max_value=25.0,
        value=float(config.get("dataforseo_monthly_cap_usd") or 12.0), step=1.0,
        help="Hard sperre. Med søk hver andre time kl. 07–23 og to markedsplasser er estimatet ca. USD 10,80 per 30 dager ved USD 0,020 per API-søk.",
        key="jeep_commander_dataforseo_cap_v19220_rc1631ck",
    )
    usage = state.get("dataforseo_usage") if isinstance(state.get("dataforseo_usage"), dict) else {}
    if not credentials_ready:
        st.warning("DataForSEO er ikke konfigurert. Legg DATAFORSEO_LOGIN og DATAFORSEO_PASSWORD inn som hemmelige Render-variabler for både web og scheduler.")
    elif validated:
        st.success(f"DataForSEO-test godkjent · OLX {validation.get('counts', {}).get('olx', 0)} · Webmotors {validation.get('counts', {}).get('webmotors', 0)} · estimert månedsbruk ${float(usage.get('estimated_usd') or 0):.4f}")
    else:
        st.info("DataForSEO er konfigurert, men ikke godkjent. Testen er stille og sender ingen Pushover.")
    validation_sources = list(validation.get("sources") or [])
    olx_test = next((row for row in validation_sources if "OLX" in str(row.get("source"))), {})
    webmotors_test = next((row for row in validation_sources if "Webmotors" in str(row.get("source"))), {})
    status_cols = st.columns(4)
    status_cols[0].success("✅ API konfigurert") if credentials_ready else status_cols[0].error("❌ API mangler")
    status_cols[1].success(f"✅ OLX: {validation.get('counts', {}).get('olx', 0)}") if olx_test.get("state") == "OK" and validation.get('counts', {}).get('olx', 0) else status_cols[1].error(f"❌ OLX: {olx_test.get('error') or ('0 individuelle annonser' if olx_test else 'ikke testet')}")
    status_cols[2].success(f"✅ Webmotors: {validation.get('counts', {}).get('webmotors', 0)}") if webmotors_test.get("state") == "OK" and validation.get('counts', {}).get('webmotors', 0) else status_cols[2].error(f"❌ Webmotors: {webmotors_test.get('error') or ('0 individuelle annonser' if webmotors_test else 'ikke testet')}")
    status_cols[3].success("✅ 0 Pushover sendt") if validation else status_cols[3].info("Ingen test kjørt")
    if validation:
        st.caption(f"Siste API-test: {validation.get('at')} · individuelle lenker {validation.get('individual_urls', 0)} · komplette kandidater {validation.get('complete_candidates', 0)} · estimert bruk ${float(usage.get('estimated_usd') or 0):.4f}")
        with st.expander("🔎 DataForSEO-diagnose – se hva som ble funnet og forkastet", expanded=not validated):
            diagnosis_rows = []
            for source_row in validation_sources:
                st.markdown(
                    f"**{source_row.get('source')}** · organiske resultater {source_row.get('organic_items', 0)} · "
                    f"godkjent {source_row.get('accepted_items', 0)} · forkastet {source_row.get('rejected_items', 0)}"
                )
                for item in source_row.get("diagnostics") or []:
                    diagnosis_rows.append({
                        "Kilde": source_row.get("source"), "Resultat": item.get("decision"),
                        "Årsak": item.get("reason"), "Tittel": item.get("title"),
                        "Domene": item.get("domain"), "URL": item.get("url"),
                    })
            if diagnosis_rows:
                st.dataframe(diagnosis_rows, width="stretch", hide_index=True)
            else:
                st.info("API-et returnerte ingen organiske resultater som kunne diagnostiseres. Kildestatusen over viser eventuell API-feil.")
            st.download_button(
                "⬇️ Last ned sikker diagnose-ZIP",
                data=build_dataforseo_diagnostic_zip(validation, usage),
                file_name=f"Jeep_Commander_2_2_DataForSEO_diagnose_{__import__('app_version').APP_VERSION}.zip",
                mime="application/zip", width="stretch",
                key="jeep_dataforseo_diagnostic_zip_v19220_rc1631cn",
            )

    busy = bool(st.session_state.get("jeep_commander_job_v19220_rc1631cl"))
    if st.button("Test DataForSEO uten varsler", disabled=not credentials_ready or busy or mode_labels[mode_label] == "STOPPED", key="jeep_commander_dataforseo_test_v19220_rc1631cl"):
        st.session_state["jeep_commander_job_v19220_rc1631cl"] = "TEST"
        st.rerun()
    manual_urls_text = st.text_area(
        "Annonser som alltid skal følges (én lenke per linje)",
        value="\n".join(config.get("manual_urls") or []),
        help="Lim inn en annonse som ikke blir funnet automatisk. Den kontrolleres videre for prisendringer.",
        key="jeep_commander_manual_urls_v19220_rc1631cj",
    )
    cost_left, cost_right = st.columns(2)
    transport_estimate = cost_left.number_input(
        "Transport til Fortaleza (R$)", min_value=0, max_value=50000,
        value=int(config.get("transport_estimate_brl") or 0), step=500,
        key="jeep_commander_transport_v19220_rc1631cj",
    )
    fees_estimate = cost_right.number_input(
        "Dokumenter/andre kostnader (R$)", min_value=0, max_value=50000,
        value=int(config.get("fees_estimate_brl") or 0), step=500,
        key="jeep_commander_fees_v19220_rc1631cj",
    )

    left, right = st.columns(2)
    if left.button("Lagre søkevalg", key="jeep_commander_save_v19220_rc1631ch", width="stretch"):
        years = [2025, 2026] if year_label == "2025 og 2026" else ([2026] if year_label == "Bare 2026" else [2025])
        manual_urls = [line.strip() for line in manual_urls_text.splitlines() if _valid_url(line.strip())]
        save_config({**config, "years": years, "max_km": max_km, "area": area_options[area_label], "active": active, "module_mode": mode_labels[mode_label], "interval_minutes": interval_minutes, "night_pause_enabled": night_pause_enabled, "night_pause_start": night_start, "night_pause_end": night_end, "dataforseo_enabled": dataforseo_enabled, "dataforseo_monthly_cap_usd": dataforseo_monthly_cap, "pushover": pushover, "include_other_colors": other_colors, "include_dealer_network": dealer_network, "manual_urls": manual_urls, "transport_estimate_brl": transport_estimate, "fees_estimate_brl": fees_estimate})
        st.success("Søkevalgene er lagret og brukes ved neste Cron-kontroll.")
        st.rerun()
    if right.button("Søk nå", disabled=busy or mode_labels[mode_label] == "STOPPED", key="jeep_commander_scan_v19220_rc1631cl", width="stretch"):
        st.session_state["jeep_commander_job_v19220_rc1631cl"] = "SEARCH"
        st.rerun()

    pending_job = st.session_state.get("jeep_commander_job_v19220_rc1631cl")
    if pending_job:
        progress_bar = st.progress(0, text="Starter …")
        def update_progress(stage: str, percent: int, detail: str) -> None:
            progress_bar.progress(percent, text=f"{percent}% · {detail}")
        if pending_job == "TEST":
            validate_dataforseo(progress=update_progress)
        else:
            run_due_monitor(force=True, notify=True, source="manual", progress=update_progress)
        st.session_state["jeep_commander_job_v19220_rc1631cl"] = ""
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
                message = html_lib.escape(_message(item, "Sort foretrukket" if item.get("black") else "Billigere alternativ farge")).replace("\n", "<br>")
                st.markdown(f'<div class="jeep-result-card">{message}</div>', unsafe_allow_html=True)
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
