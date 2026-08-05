"""Shared market universe definitions.

One source of truth for market choices, stable profile identifiers and exact
country expansion.  User-facing aggregate labels always name the countries
that will actually run.  Legacy labels remain accepted for saved jobs and old
reports, but they are not offered as new UI choices.
"""

from __future__ import annotations

from typing import Iterable, List


BASE_MARKET_SCOPES: List[str] = ["USA", "Norge", "Sverige", "Finland", "Danmark", "Brasil"]
CORE_MARKET_SCOPES: List[str] = ["Norge", "Sverige", "USA"]
EXTENDED_NORDIC_MARKET_SCOPES: List[str] = ["Danmark", "Finland"]
NORDIC_MARKET_SCOPES: List[str] = ["Norge", "Sverige", "Finland", "Danmark"]

# RC9: labels are contracts, not marketing names.  The exact countries are
# visible anywhere a user selects a market profile.
CORE_MARKET_SCOPE_LABEL = "Norge + Sverige + USA"
EXTENDED_NORDIC_SCOPE_LABEL = "Danmark + Finland"
NORDIC_MARKET_SCOPE_LABEL = "Norge + Sverige + Danmark + Finland"
FULL_MARKET_SCOPE_LABEL = "Norge + Sverige + Danmark + Finland + USA + Brasil"

LEGACY_CORE_MARKET_SCOPE_LABELS = {"Alle", "Kjernemarkeder", "Alle kjernemarkeder"}
LEGACY_EXTENDED_NORDIC_LABELS = {"Utvidet Norden"}
LEGACY_NORDIC_LABELS = {"Norden"}
LEGACY_FULL_MARKET_SCOPE_LABELS = {"Alle markeder - full skanning"}
LEGACY_AGGREGATE_MARKET_SCOPES = (
    LEGACY_CORE_MARKET_SCOPE_LABELS
    | LEGACY_EXTENDED_NORDIC_LABELS
    | LEGACY_NORDIC_LABELS
    | LEGACY_FULL_MARKET_SCOPE_LABELS
)

AGGREGATE_MARKET_SCOPES: List[str] = [
    CORE_MARKET_SCOPE_LABEL,
    EXTENDED_NORDIC_SCOPE_LABEL,
    NORDIC_MARKET_SCOPE_LABEL,
    FULL_MARKET_SCOPE_LABEL,
]
MARKET_SCOPE_OPTIONS: List[str] = BASE_MARKET_SCOPES + AGGREGATE_MARKET_SCOPES
SOURCE_SCOPE_OPTIONS: List[str] = [
    "Analyseflyt input", "Top Picks", "Watchlist", "Paper trading", "Portefolje",
    "Portefølje", "Manuell liste", "Smart AI-utvalg",
]
NO_MARKET_SELECTION_LABEL = "Velg marked"
NO_UNIVERSE_SELECTION_LABEL = "Velg univers"


def market_scope_options(include_aggregate: bool = True) -> List[str]:
    return list(MARKET_SCOPE_OPTIONS if include_aggregate else BASE_MARKET_SCOPES)


def picker_scope_options(include_sources: bool = True) -> List[str]:
    options = market_scope_options(include_aggregate=True)
    if include_sources:
        for source in SOURCE_SCOPE_OPTIONS:
            if source not in options:
                options.append(source)
    return options


def is_market_scope(scope: object) -> bool:
    value = str(scope or "").strip()
    return value in MARKET_SCOPE_OPTIONS or value in LEGACY_AGGREGATE_MARKET_SCOPES


def expand_market_scope(scope: object) -> List[str]:
    value = str(scope or "").strip()
    if value == CORE_MARKET_SCOPE_LABEL or value in LEGACY_CORE_MARKET_SCOPE_LABELS:
        return list(CORE_MARKET_SCOPES)
    if value == EXTENDED_NORDIC_SCOPE_LABEL or value in LEGACY_EXTENDED_NORDIC_LABELS:
        return list(EXTENDED_NORDIC_MARKET_SCOPES)
    if value == NORDIC_MARKET_SCOPE_LABEL or value in LEGACY_NORDIC_LABELS:
        return list(NORDIC_MARKET_SCOPES)
    if value == FULL_MARKET_SCOPE_LABEL or value in LEGACY_FULL_MARKET_SCOPE_LABELS:
        return list(BASE_MARKET_SCOPES)
    if value in BASE_MARKET_SCOPES:
        return [value]
    return []


def canonical_market_scope_label(scope: object) -> str:
    """Return the unambiguous RC9 label for a legacy or current scope."""
    value = str(scope or "").strip()
    expanded = expand_market_scope(value)
    if expanded == CORE_MARKET_SCOPES:
        return CORE_MARKET_SCOPE_LABEL
    if expanded == EXTENDED_NORDIC_MARKET_SCOPES:
        return EXTENDED_NORDIC_SCOPE_LABEL
    if set(expanded) == set(NORDIC_MARKET_SCOPES) and len(expanded) == len(NORDIC_MARKET_SCOPES):
        return NORDIC_MARKET_SCOPE_LABEL
    if expanded == BASE_MARKET_SCOPES:
        return FULL_MARKET_SCOPE_LABEL
    return value


def market_scope_description(scope: object) -> str:
    markets = expand_market_scope(scope)
    return ", ".join(markets) if markets else "Ingen gyldige markeder"


def normalize_market_scopes(scopes: Iterable[object] | None) -> List[str]:
    out: List[str] = []
    for raw in scopes or []:
        scope = str(raw or "").strip()
        if not scope or scope in {NO_MARKET_SELECTION_LABEL, NO_UNIVERSE_SELECTION_LABEL}:
            continue
        if not is_market_scope(scope) and scope not in SOURCE_SCOPE_OPTIONS:
            continue
        canonical = canonical_market_scope_label(scope) if is_market_scope(scope) else scope
        if canonical not in out:
            out.append(canonical)
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
    MARKET_PROFILE_CORE: CORE_MARKET_SCOPE_LABEL,
    MARKET_PROFILE_EXTENDED_NORDIC: EXTENDED_NORDIC_SCOPE_LABEL,
    MARKET_PROFILE_BRAZIL: "Brasil",
    MARKET_PROFILE_FULL: FULL_MARKET_SCOPE_LABEL,
    MARKET_PROFILE_CUSTOM: "Egendefinert markedsutvalg",
}


def _profile_from_name(name: object) -> str | None:
    text = str(name or "").strip().casefold().replace("–", "-")
    if not text:
        return None
    if "alle markeder" in text or "full skanning" in text or all(country.casefold() in text for country in ("norge", "sverige", "danmark", "finland", "usa", "brasil")):
        return MARKET_PROFILE_FULL
    if "utvidet norden" in text or ("danmark" in text and "finland" in text and "norge" not in text and "sverige" not in text):
        return MARKET_PROFILE_EXTENDED_NORDIC
    if "kjernemarked" in text or ("norge" in text and "sverige" in text and "usa" in text and "danmark" not in text and "finland" not in text):
        return MARKET_PROFILE_CORE
    if text == "brasil" or text.endswith("- brasil") or "rapport - brasil" in text:
        return MARKET_PROFILE_BRAZIL
    return None


def infer_market_profile(
    markets: Iterable[object] | None,
    *,
    name: object = "",
    explicit_profile: object = "",
) -> str:
    """Resolve one stable market profile while accepting legacy saved values."""
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
        return [CORE_MARKET_SCOPE_LABEL]
    if profile == MARKET_PROFILE_EXTENDED_NORDIC:
        return [EXTENDED_NORDIC_SCOPE_LABEL]
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
    return expanded or [CORE_MARKET_SCOPE_LABEL]


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
        "country_text": ", ".join(expanded),
    }
