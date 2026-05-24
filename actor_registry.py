from __future__ import annotations

import json
import re
import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence


ACTOR_REGISTRY_SETTINGS_KEY = "alpha_radar_actor_registry_v1863bd"
ACTOR_HIT_LOG_SETTINGS_KEY = "alpha_radar_actor_hit_log_v1863bi"
ACTOR_REGISTRY_FILE = Path("data/alpha_radar_actor_registry.json")
LEGACY_BJELLESAU_FILE = Path("data/alpha_radar_bjellesauer.json")

ACTOR_TYPES = ("Bjellesau", "Insider watch", "Institusjon", "Annet")
ACTOR_ROLES = ("Bjellesau", "Insider watch", "Institusjon", "Styremedlem", "Ledelse", "Fond", "Holding", "Annet")
STRENGTH_LEVELS = ("Svak", "Normal", "Sterk")
TRUST_LEVELS = ("Bekreftet", "Manuelt lagt inn", "Importert", "Usikker")

DEFAULT_ACTOR_ROWS: list[dict[str, Any]] = [
    {
        "active": True,
        "name": "Norges Bank Investment Management",
        "aliases": "Norges Bank Investment Management; NBIM; Oljefondet; Statens pensjonsfond utland; Government Pension Fund Global; Norges Bank",
        "market": "Alle",
        "actor_type": "Institusjon",
        "actor_roles": "Institusjon",
        "strength": "Sterk",
        "trust_level": "Bekreftet",
        "relevant_tickers": "",
        "notes": "Offentlig institusjonell eier. Brukes som sterk institusjonell bjellesau naar NBIM-fil eller nyhetsspor matcher.",
        "links": "https://www.nbim.no/en/investments/all-investments/",
    },
    {
        "active": False,
        "name": "Eksempel Bjellesau",
        "aliases": "Eksempel Bjellesau; Eksempel Invest",
        "market": "Alle",
        "actor_type": "Bjellesau",
        "actor_roles": "Bjellesau",
        "strength": "Normal",
        "trust_level": "Usikker",
        "relevant_tickers": "",
        "notes": "Inaktiv eksempelrad. Legg inn egne navn, alias og marked.",
        "links": "",
    }
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_aliases(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_parts = [str(item or "") for item in value]
    else:
        raw_parts = re.split(r"[,;\n]+", _clean(value))
    out: list[str] = []
    for part in raw_parts:
        text = str(part or "").strip()
        if text and text.lower() not in {x.lower() for x in out}:
            out.append(text)
    return out


def _split_tickers(value: Any) -> list[str]:
    tickers = []
    for part in re.split(r"[,;\s\n]+", _clean(value).upper()):
        ticker = part.strip()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _normalize_role(value: Any) -> str:
    text = _clean(value)
    low = text.lower()
    if not text:
        return ""
    role_map = {
        "bjelle": "Bjellesau",
        "smart money": "Bjellesau",
        "insider": "Insider watch",
        "primar": "Insider watch",
        "primær": "Insider watch",
        "instit": "Institusjon",
        "nbim": "Institusjon",
        "styre": "Styremedlem",
        "board": "Styremedlem",
        "ledelse": "Ledelse",
        "ceo": "Ledelse",
        "cfo": "Ledelse",
        "fond": "Fond",
        "fund": "Fond",
        "holding": "Holding",
        "holdingselskap": "Holding",
    }
    for needle, role in role_map.items():
        if needle in low:
            return role
    if text in ACTOR_ROLES:
        return text
    return "Annet"


def _split_roles(value: Any, fallback: Any = None) -> list[str]:
    raw_value = value
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        raw_value = fallback
    if isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes, bytearray)):
        raw_parts = [str(item or "") for item in raw_value]
    else:
        raw_parts = re.split(r"[,;/\n+]+", _clean(raw_value))
    roles: list[str] = []
    for part in raw_parts:
        role = _normalize_role(part)
        if role and role not in roles:
            roles.append(role)
    return roles or ["Bjellesau"]


def actor_roles(row: Mapping[str, Any] | None) -> list[str]:
    raw = dict(row or {})
    return _split_roles(raw.get("actor_roles") or raw.get("roles") or raw.get("roller"), raw.get("actor_type") or raw.get("type") or raw.get("rolle"))


def _primary_actor_type(roles: Sequence[str]) -> str:
    for role in roles:
        if role in ACTOR_TYPES:
            return role
    return "Annet"


def _market_matches(actor_market: str, target_market: str | None = None, ticker: str | None = None) -> bool:
    actor = _clean(actor_market).lower()
    target = _clean(target_market).lower()
    ticker_text = _clean(ticker).upper()
    if actor in {"", "alle", "all", "global", "*"}:
        return True
    aliases = {
        "norge": (".OL", "oslo", "norge", "norway"),
        "oslo": (".OL", "oslo", "norge", "norway"),
        "sverige": (".ST", "stockholm", "sverige", "sweden"),
        "stockholm": (".ST", "stockholm", "sverige", "sweden"),
        "danmark": (".CO", "copenhagen", "danmark", "denmark"),
        "kobenhavn": (".CO", "copenhagen", "danmark", "denmark"),
        "finland": (".HE", "helsinki", "finland"),
        "norden": (".OL", ".ST", ".CO", ".HE", "norden", "nordic"),
        "usa": ("usa", "us", "nasdaq", "nyse"),
        "brasil": (".SA", "brasil", "brazil", "sao paulo"),
    }
    checks = aliases.get(actor, (actor,))
    return any(check in target or ticker_text.endswith(check) for check in checks)


def _ticker_matches(actor_tickers: str, ticker: str | None = None) -> bool:
    wanted = _split_tickers(actor_tickers)
    if not wanted:
        return True
    current = _clean(ticker).upper()
    return bool(current and current in wanted)


def normalize_actor_row(row: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(row or {})
    name = _clean(raw.get("name") or raw.get("navn") or raw.get("actor") or raw.get("aktor"))
    aliases = _split_aliases(raw.get("aliases") or raw.get("alias") or raw.get("aka"))
    if name and name.lower() not in {alias.lower() for alias in aliases}:
        aliases.insert(0, name)
    roles = _split_roles(raw.get("actor_roles") or raw.get("roles") or raw.get("roller"), raw.get("actor_type") or raw.get("type") or raw.get("rolle"))
    actor_type = _primary_actor_type(roles)
    strength = _clean(raw.get("strength") or raw.get("styrke")) or "Normal"
    if strength not in STRENGTH_LEVELS:
        strength = "Normal"
    trust_level = _clean(raw.get("trust_level") or raw.get("tillit") or raw.get("status")) or "Manuelt lagt inn"
    if trust_level not in TRUST_LEVELS:
        trust_level = "Bekreftet" if "bekreft" in trust_level.lower() else "Usikker" if "usikker" in trust_level.lower() else "Manuelt lagt inn"
    return {
        "active": bool(raw.get("active", raw.get("aktiv", True))),
        "name": name or (aliases[0] if aliases else ""),
        "aliases": "; ".join(aliases),
        "market": _clean(raw.get("market") or raw.get("marked")) or "Alle",
        "actor_type": actor_type,
        "actor_roles": "; ".join(roles),
        "strength": strength,
        "trust_level": trust_level,
        "relevant_tickers": "; ".join(_split_tickers(raw.get("relevant_tickers") or raw.get("tickers") or raw.get("ticker") or raw.get("selskaper"))),
        "notes": _clean(raw.get("notes") or raw.get("notater")),
        "links": _clean(raw.get("links") or raw.get("lenker") or raw.get("url")),
    }


def _rows_from_legacy_file(path: Path = LEGACY_BJELLESAU_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    names: list[str] = []
    if isinstance(raw, list):
        names = [_clean(x) for x in raw if _clean(x)]
    elif isinstance(raw, Mapping):
        names = [_clean(x) for x in raw.get("names", []) if _clean(x)]
    return [
        normalize_actor_row({
            "active": True,
            "name": name,
            "aliases": name,
            "market": "Alle",
            "actor_type": "Bjellesau",
            "strength": "Normal",
            "notes": "Migrert fra lokal bjellesau-watchlist.",
        })
        for name in names
    ]


def load_actor_registry() -> list[dict[str, Any]]:
    try:
        from settings_store import load_settings

        settings = load_settings() or {}
        raw = settings.get(ACTOR_REGISTRY_SETTINGS_KEY)
        if isinstance(raw, list):
            rows = [normalize_actor_row(item) for item in raw if isinstance(item, Mapping)]
            return [row for row in rows if row.get("name") or row.get("aliases")]
    except Exception:
        pass

    if ACTOR_REGISTRY_FILE.exists():
        try:
            raw_file = json.loads(ACTOR_REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(raw_file, list):
                rows = [normalize_actor_row(item) for item in raw_file if isinstance(item, Mapping)]
                return [row for row in rows if row.get("name") or row.get("aliases")]
        except Exception:
            pass

    legacy = _rows_from_legacy_file()
    return legacy or [dict(row) for row in DEFAULT_ACTOR_ROWS]


def save_actor_registry(rows: Sequence[Mapping[str, Any]]) -> int:
    clean_rows = [normalize_actor_row(row) for row in rows if isinstance(row, Mapping)]
    clean_rows = [row for row in clean_rows if row.get("name") or row.get("aliases")]
    from settings_store import load_settings, save_settings

    settings = load_settings() or {}
    settings[ACTOR_REGISTRY_SETTINGS_KEY] = clean_rows
    save_settings(settings)
    return len(clean_rows)


def actor_aliases_for_matching(
    *,
    market: str | None = None,
    ticker: str | None = None,
    actor_types: Sequence[str] | None = None,
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    wanted = {str(item) for item in actor_types or ("Bjellesau", "Institusjon", "Insider watch")}
    aliases: list[str] = []
    for row in rows or load_actor_registry():
        item = normalize_actor_row(row)
        if not item["active"] or not (set(actor_roles(item)) & wanted):
            continue
        if not _market_matches(item["market"], market, ticker):
            continue
        if not _ticker_matches(item.get("relevant_tickers", ""), ticker):
            continue
        for alias in _split_aliases(item["aliases"]):
            alias_l = alias.lower()
            if alias_l and alias_l not in aliases:
                aliases.append(alias_l)
    return aliases


def match_actor_text(
    text: str,
    *,
    market: str | None = None,
    ticker: str | None = None,
    actor_types: Sequence[str] | None = None,
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    haystack = f" {_clean(text).lower()} "
    if not haystack.strip():
        return []
    wanted = {str(item) for item in actor_types or ("Bjellesau", "Institusjon", "Insider watch")}
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows or load_actor_registry():
        row = normalize_actor_row(raw)
        if not row["active"] or not (set(actor_roles(row)) & wanted):
            continue
        if not _market_matches(row["market"], market, ticker):
            continue
        if not _ticker_matches(row.get("relevant_tickers", ""), ticker):
            continue
        for alias in _split_aliases(row["aliases"]):
            alias_l = alias.lower()
            if len(alias_l) < 3:
                continue
            if alias_l in haystack:
                marker = (row["name"].lower(), alias_l)
                if marker in seen:
                    continue
                seen.add(marker)
                match = dict(row)
                match["matched_alias"] = alias
                match["matched_roles"] = actor_roles(row)
                matches.append(match)
                break
    return matches


def actor_match_evidence(
    text: str,
    *,
    market: str | None = None,
    ticker: str | None = None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for match in match_actor_text(text, market=market, ticker=ticker):
        roles = actor_roles(match)
        evidence.append({
            "type": " + ".join(roles),
            "title": match.get("name") or match.get("matched_alias"),
            "source": "Lokalt aktorregister",
            "published": "",
            "url": match.get("links") or "",
            "detail": f"Matchet alias: {match.get('matched_alias')}. Roller: {', '.join(roles)}. Tillit: {match.get('trust_level')}. Styrke: {match.get('strength')}. {match.get('notes') or ''}".strip(),
            "actor": match.get("actor_type"),
            "actor_roles": roles,
            "trust_level": match.get("trust_level"),
        })
    return evidence


def actor_registry_to_json(rows: Sequence[Mapping[str, Any]]) -> bytes:
    clean = [normalize_actor_row(row) for row in rows if isinstance(row, Mapping)]
    return json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8")


def actor_registry_to_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    fields = ["active", "name", "aliases", "market", "actor_type", "actor_roles", "strength", "trust_level", "relevant_tickers", "notes", "links"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", delimiter=";")
    writer.writeheader()
    for row in rows:
        writer.writerow(normalize_actor_row(row))
    return buffer.getvalue().encode("utf-8-sig")


def parse_actor_registry_upload(data: bytes, filename: str = "") -> list[dict[str, Any]]:
    suffix = Path(filename or "").suffix.lower()
    text = data.decode("utf-8-sig", errors="replace")
    if suffix == ".json" or text.lstrip().startswith(("[", "{")):
        raw = json.loads(text)
        if isinstance(raw, Mapping):
            raw = raw.get("actors") or raw.get("rows") or []
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            return []
        return [normalize_actor_row(row) for row in raw if isinstance(row, Mapping)]
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ";"
    return [normalize_actor_row(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect) if isinstance(row, Mapping)]


def _actor_key(row: Mapping[str, Any] | None) -> str:
    clean = normalize_actor_row(row)
    return (clean.get("name") or clean.get("aliases") or "").strip().lower()


def load_actor_hit_log() -> dict[str, dict[str, Any]]:
    try:
        from settings_store import load_settings

        settings = load_settings() or {}
        raw = settings.get(ACTOR_HIT_LOG_SETTINGS_KEY)
        if isinstance(raw, Mapping):
            return {str(key): dict(value) for key, value in raw.items() if isinstance(value, Mapping)}
    except Exception:
        pass
    return {}


def actor_hit_stats(rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    log = load_actor_hit_log()
    stats: dict[str, dict[str, Any]] = {}
    for row in rows or load_actor_registry():
        key = _actor_key(row)
        if not key:
            continue
        item = dict(log.get(key) or {})
        stats[key] = {
            "hit_count": int(item.get("hit_count") or 0),
            "last_seen": _clean(item.get("last_seen")),
            "tickers": "; ".join(item.get("tickers") or []) if isinstance(item.get("tickers"), Sequence) and not isinstance(item.get("tickers"), (str, bytes, bytearray)) else _clean(item.get("tickers")),
            "markets": "; ".join(item.get("markets") or []) if isinstance(item.get("markets"), Sequence) and not isinstance(item.get("markets"), (str, bytes, bytearray)) else _clean(item.get("markets")),
            "sources": "; ".join(item.get("sources") or []) if isinstance(item.get("sources"), Sequence) and not isinstance(item.get("sources"), (str, bytes, bytearray)) else _clean(item.get("sources")),
        }
    return stats


def record_actor_hits(
    matches: Sequence[Mapping[str, Any]] | None,
    *,
    ticker: str | None = None,
    market: str | None = None,
    source: str | None = None,
    found_at: str | None = None,
) -> int:
    if not matches:
        return 0
    try:
        from datetime import datetime
        from settings_store import load_settings, save_settings

        settings = load_settings() or {}
        log = settings.get(ACTOR_HIT_LOG_SETTINGS_KEY)
        if not isinstance(log, Mapping):
            log = {}
        log = {str(key): dict(value) for key, value in log.items() if isinstance(value, Mapping)}
        now = found_at or datetime.now().strftime("%Y-%m-%d %H:%M")
        changed = 0
        for raw in matches:
            key = _actor_key(raw)
            if not key:
                continue
            item = dict(log.get(key) or {})
            item["hit_count"] = int(item.get("hit_count") or 0) + 1
            item["last_seen"] = now
            for field, value in (("tickers", _clean(ticker).upper()), ("markets", _clean(market)), ("sources", _clean(source))):
                values = list(item.get(field) or []) if isinstance(item.get(field), list) else []
                if value and value not in values:
                    values.append(value)
                item[field] = values[-20:]
            log[key] = item
            changed += 1
        if changed:
            settings[ACTOR_HIT_LOG_SETTINGS_KEY] = log
            save_settings(settings)
        return changed
    except Exception:
        return 0


__all__ = [
    "ACTOR_REGISTRY_SETTINGS_KEY",
    "ACTOR_HIT_LOG_SETTINGS_KEY",
    "ACTOR_ROLES",
    "ACTOR_TYPES",
    "STRENGTH_LEVELS",
    "TRUST_LEVELS",
    "actor_aliases_for_matching",
    "actor_hit_stats",
    "actor_match_evidence",
    "actor_registry_to_csv",
    "actor_registry_to_json",
    "actor_roles",
    "load_actor_registry",
    "load_actor_hit_log",
    "match_actor_text",
    "normalize_actor_row",
    "parse_actor_registry_upload",
    "record_actor_hits",
    "save_actor_registry",
]
