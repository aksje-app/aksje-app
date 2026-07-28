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
