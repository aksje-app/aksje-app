APP_VERSION = "v18.6.39"
APP_VERSION_NAME = "Ryddet venstremeny og stoppet tekstklipping"
APP_BUILD_ID = "v18639-sidebar-polish"
# Kort label til UI. Fullt navn brukes kun i patch notes/admin.
APP_BUILD_LABEL = APP_VERSION

APP_PATCH_NOTES = [
    "v18.6.39: Venstremeny er gjort bredere og mer lesbar, med tydelige seksjoner for Navigasjon, Konto og Avansert.",
    "Tekstklipping som kunne vise Admin/Drift som korte fragmenter er fjernet med nye sidebar-regler.",
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
