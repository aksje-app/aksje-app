"""Shared market universe definitions.

One small source of truth for UI market choices and market-scope expansion.
The data engine stays in ``universe_engine.py``; this module only describes
which markets exist and how aggregate scopes should expand.
"""

from __future__ import annotations

from typing import Iterable, List


BASE_MARKET_SCOPES: List[str] = ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]
CORE_MARKET_SCOPES: List[str] = ["Norge", "Sverige", "USA"]
EXTENDED_NORDIC_MARKET_SCOPES: List[str] = ["Danmark", "Finland"]
NORDIC_MARKET_SCOPES: List[str] = ["Norge", "Sverige", "Finland", "Danmark"]
FULL_MARKET_SCOPE_LABEL = "Alle markeder - full skanning"
AGGREGATE_MARKET_SCOPES: List[str] = ["Alle kjernemarkeder", "Alle", "Kjernemarkeder", "Utvidet Norden", "Norden", FULL_MARKET_SCOPE_LABEL]
MARKET_SCOPE_OPTIONS: List[str] = BASE_MARKET_SCOPES + AGGREGATE_MARKET_SCOPES
SOURCE_SCOPE_OPTIONS: List[str] = ["Top Picks", "Watchlist", "Paper trading", "Portefolje", "Portefølje", "Manuell liste", "Smart AI-utvalg"]
NO_MARKET_SELECTION_LABEL = "Velg marked"
NO_UNIVERSE_SELECTION_LABEL = "Velg univers"
SOURCE_SCOPE_OPTIONS = ["Analyseflyt input"] + [x for x in SOURCE_SCOPE_OPTIONS if x != "Analyseflyt input"]


def market_scope_options(include_aggregate: bool = True) -> List[str]:
    if include_aggregate:
        return list(MARKET_SCOPE_OPTIONS)
    return list(BASE_MARKET_SCOPES)


def picker_scope_options(include_sources: bool = True) -> List[str]:
    options = market_scope_options(include_aggregate=True)
    if include_sources:
        for source in SOURCE_SCOPE_OPTIONS:
            if source not in options:
                options.append(source)
    return options


def is_market_scope(scope: object) -> bool:
    return str(scope or "").strip() in MARKET_SCOPE_OPTIONS


def expand_market_scope(scope: object) -> List[str]:
    value = str(scope or "").strip()
    if value in {"Alle", "Kjernemarkeder", "Alle kjernemarkeder"}:
        return list(CORE_MARKET_SCOPES)
    if value == "Utvidet Norden":
        return list(EXTENDED_NORDIC_MARKET_SCOPES)
    if value == "Norden":
        return list(NORDIC_MARKET_SCOPES)
    if value == FULL_MARKET_SCOPE_LABEL:
        return list(BASE_MARKET_SCOPES)
    if value in BASE_MARKET_SCOPES:
        return [value]
    return []


def normalize_market_scopes(scopes: Iterable[object] | None) -> List[str]:
    out: List[str] = []
    for raw in scopes or []:
        scope = str(raw or "").strip()
        if not scope or scope in {NO_MARKET_SELECTION_LABEL, NO_UNIVERSE_SELECTION_LABEL}:
            continue
        if scope not in MARKET_SCOPE_OPTIONS and scope not in SOURCE_SCOPE_OPTIONS:
            continue
        if scope not in out:
            out.append(scope)
    return out

# Stable profile identifiers used by saved jobs, runtime telemetry and reports.
MARKET_PROFILE_CORE = "CORE"
MARKET_PROFILE_EXTENDED_NORDIC = "EXTENDED_NORDIC"
MARKET_PROFILE_BRAZIL = "BRAZIL"
MARKET_PROFILE_FULL = "FULL"
MARKET_PROFILE_CUSTOM = "CUSTOM"
MARKET_PROFILE_IDS = {
    MARKET_PROFILE_CORE,
    MARKET_PROFILE_EXTENDED_NORDIC,
    MARKET_PROFILE_BRAZIL,
    MARKET_PROFILE_FULL,
    MARKET_PROFILE_CUSTOM,
}
MARKET_PROFILE_LABELS = {
    MARKET_PROFILE_CORE: "Kjernemarkeder",
    MARKET_PROFILE_EXTENDED_NORDIC: "Utvidet Norden",
    MARKET_PROFILE_BRAZIL: "Brasil",
    MARKET_PROFILE_FULL: "Alle markeder - full skanning",
    MARKET_PROFILE_CUSTOM: "Egendefinert markedsutvalg",
}


def _profile_from_name(name: object) -> str | None:
    text = str(name or "").strip().casefold().replace("–", "-")
    if not text:
        return None
    if "kjernemarked" in text:
        return MARKET_PROFILE_CORE
    if "utvidet norden" in text:
        return MARKET_PROFILE_EXTENDED_NORDIC
    if "alle markeder" in text or "full skanning" in text:
        return MARKET_PROFILE_FULL
    if text == "brasil" or text.endswith("- brasil") or "rapport - brasil" in text:
        return MARKET_PROFILE_BRAZIL
    return None


def infer_market_profile(
    markets: Iterable[object] | None,
    *,
    name: object = "",
    explicit_profile: object = "",
) -> str:
    """Resolve one stable market profile.

    Explicit profile metadata is authoritative. For legacy rows without profile
    metadata, a clearly named profile (for example ``Kjernemarkeder``) takes
    precedence over stale saved market lists. This repairs the historic case
    where a job called "Kjernemarkeder" still carried all six markets.
    """
    explicit = str(explicit_profile or "").strip().upper()
    if explicit in MARKET_PROFILE_IDS:
        return explicit
    named = _profile_from_name(name)
    if named:
        return named
    expanded: list[str] = []
    for scope in markets or []:
        for market in expand_market_scope(scope):
            if market not in expanded:
                expanded.append(market)
    values = set(expanded)
    if values == set(CORE_MARKET_SCOPES):
        return MARKET_PROFILE_CORE
    if values == set(EXTENDED_NORDIC_MARKET_SCOPES):
        return MARKET_PROFILE_EXTENDED_NORDIC
    if values == {"Brasil"}:
        return MARKET_PROFILE_BRAZIL
    if values == set(BASE_MARKET_SCOPES):
        return MARKET_PROFILE_FULL
    return MARKET_PROFILE_CUSTOM


def profile_market_selections(profile_id: object, markets: Iterable[object] | None = None) -> List[str]:
    profile = str(profile_id or "").strip().upper()
    if profile == MARKET_PROFILE_CORE:
        return ["Alle kjernemarkeder"]
    if profile == MARKET_PROFILE_EXTENDED_NORDIC:
        return ["Utvidet Norden"]
    if profile == MARKET_PROFILE_BRAZIL:
        return ["Brasil"]
    if profile == MARKET_PROFILE_FULL:
        return [FULL_MARKET_SCOPE_LABEL]
    normalized = normalize_market_scopes(markets)
    # Custom profiles must be explicit individual markets. Aggregate aliases
    # are expanded so the persisted profile cannot silently change meaning.
    expanded: list[str] = []
    for scope in normalized:
        for market in expand_market_scope(scope):
            if market not in expanded:
                expanded.append(market)
    return expanded or ["Alle kjernemarkeder"]


def market_profile_contract(
    profile_id: object,
    markets: Iterable[object] | None = None,
    *,
    name: object = "",
) -> dict[str, object]:
    resolved = infer_market_profile(markets, name=name, explicit_profile=profile_id)
    selections = profile_market_selections(resolved, markets)
    expanded: list[str] = []
    for selection in selections:
        for market in expand_market_scope(selection):
            if market not in expanded:
                expanded.append(market)
    return {
        "profile_id": resolved,
        "label": MARKET_PROFILE_LABELS[resolved],
        "selections": selections,
        "expanded_markets": expanded,
    }
