from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


ACTOR_REGISTRY_SETTINGS_KEY = "alpha_radar_actor_registry_v1863bd"
ACTOR_REGISTRY_FILE = Path("data/alpha_radar_actor_registry.json")
LEGACY_BJELLESAU_FILE = Path("data/alpha_radar_bjellesauer.json")

ACTOR_TYPES = ("Bjellesau", "Insider watch", "Institusjon", "Annet")
STRENGTH_LEVELS = ("Svak", "Normal", "Sterk")

DEFAULT_ACTOR_ROWS: list[dict[str, Any]] = [
    {
        "active": False,
        "name": "Eksempel Bjellesau",
        "aliases": "Eksempel Bjellesau; Eksempel Invest",
        "market": "Alle",
        "actor_type": "Bjellesau",
        "strength": "Normal",
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
        "usa": ("usa", "us", "nasdaq", "nyse"),
        "brasil": (".SA", "brasil", "brazil", "sao paulo"),
    }
    checks = aliases.get(actor, (actor,))
    return any(check in target or ticker_text.endswith(check) for check in checks)


def normalize_actor_row(row: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(row or {})
    name = _clean(raw.get("name") or raw.get("navn") or raw.get("actor") or raw.get("aktor"))
    aliases = _split_aliases(raw.get("aliases") or raw.get("alias") or raw.get("aka"))
    if name and name.lower() not in {alias.lower() for alias in aliases}:
        aliases.insert(0, name)
    actor_type = _clean(raw.get("actor_type") or raw.get("type") or raw.get("rolle")) or "Bjellesau"
    if actor_type not in ACTOR_TYPES:
        actor_type = "Bjellesau" if "bjelle" in actor_type.lower() else "Annet"
    strength = _clean(raw.get("strength") or raw.get("styrke")) or "Normal"
    if strength not in STRENGTH_LEVELS:
        strength = "Normal"
    return {
        "active": bool(raw.get("active", raw.get("aktiv", True))),
        "name": name or (aliases[0] if aliases else ""),
        "aliases": "; ".join(aliases),
        "market": _clean(raw.get("market") or raw.get("marked")) or "Alle",
        "actor_type": actor_type,
        "strength": strength,
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
    wanted = {str(item) for item in actor_types or ("Bjellesau", "Institusjon")}
    aliases: list[str] = []
    for row in rows or load_actor_registry():
        item = normalize_actor_row(row)
        if not item["active"] or item["actor_type"] not in wanted:
            continue
        if not _market_matches(item["market"], market, ticker):
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
    wanted = {str(item) for item in actor_types or ("Bjellesau", "Institusjon")}
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows or load_actor_registry():
        row = normalize_actor_row(raw)
        if not row["active"] or row["actor_type"] not in wanted:
            continue
        if not _market_matches(row["market"], market, ticker):
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
        evidence.append({
            "type": "Bjellesau",
            "title": match.get("name") or match.get("matched_alias"),
            "source": "Lokalt aktorregister",
            "published": "",
            "url": match.get("links") or "",
            "detail": f"Matchet alias: {match.get('matched_alias')}. Styrke: {match.get('strength')}. {match.get('notes') or ''}".strip(),
            "actor": match.get("actor_type"),
        })
    return evidence


__all__ = [
    "ACTOR_REGISTRY_SETTINGS_KEY",
    "ACTOR_TYPES",
    "STRENGTH_LEVELS",
    "actor_aliases_for_matching",
    "actor_match_evidence",
    "load_actor_registry",
    "match_actor_text",
    "normalize_actor_row",
    "save_actor_registry",
]
