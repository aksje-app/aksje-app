APP_VERSION = "v18.6.37"
APP_VERSION_NAME = "Sidebar guard og mobilmeny"
APP_BUILD_ID = "v18635-dashboard-2026-phase4-mobile-kpi"
# Kort label til UI. Fullt navn brukes kun i patch notes/admin.
APP_BUILD_LABEL = APP_VERSION

APP_PATCH_NOTES = [
    "Dashboard 2026 Phase 5: KPI-kort oppdateres etter aktivt panel, venstremeny er ryddet og dobbelt versjonsnummer er fjernet.",
    "KPI-kortene leser aktive Top Picks/ranking-data og refreshes etter Kontrollsenter-rendering slik at toppkortene ikke blir liggende tomme når panelet har data.",
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
