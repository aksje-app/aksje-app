APP_VERSION = "v18.6.35"
APP_VERSION_NAME = "Dashboard 2026 Phase 4 Mobile + KPI"
APP_BUILD_ID = "v18635-dashboard-2026-phase4-mobile-kpi"
# Kort label til UI. Fullt navn brukes kun i patch notes/admin.
APP_BUILD_LABEL = APP_VERSION

APP_PATCH_NOTES = [
    "Dashboard 2026 Phase 4: mobilvisningen er strammet opp med egne regler for KPI-kort, bannere, AI Kontrollsenter og tabeller.",
    "KPI-kortene leser nå flere reelle Top Picks/ranking-kilder, inkludert siste renderede ranking og rank_cache, før de viser Ingen data.",
    "Top Picks-run lagrer eksplisitt en dashboard-snapshot slik at øverste kort ikke blir stående tomme etter kjøring.",
    "Ticker-bannerkort er komprimert på mobil for å gjøre startsiden brukbar igjen.",
    "Analysemotor og datainnhenting er ikke endret i denne runden.",
]


def get_app_version() -> str:
    return APP_VERSION


def get_app_build_label() -> str:
    return APP_BUILD_LABEL


def get_version_label() -> str:
    return APP_BUILD_LABEL


def get_patch_notes() -> list[str]:
    return list(APP_PATCH_NOTES)
