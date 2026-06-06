APP_VERSION = "v18.6.34"
APP_VERSION_NAME = "Dashboard 2026 Phase 3"
APP_BUILD_ID = "v18634-dashboard-2026-phase3"
# Kort label til UI. Fullt navn brukes kun i patch notes/admin.
APP_BUILD_LABEL = APP_VERSION

APP_PATCH_NOTES = [
    "Dashboard 2026 Phase 3: fjernet støy i topplinjen og beholdt kun diskret versjonsbadge.",
    "KPI-kort viser Ingen data når cache mangler, og bruker flere eksisterende session/cache-kilder før den faller tilbake.",
    "AI Kontrollsenter er visuelt løftet med tydeligere fliser/kort og mindre innstillingspreg.",
    "Bannerområdet og venstremargen er ytterligere komprimert for mer arbeidsflate.",
    "Visuell opprydding: færre blå rammer, mindre topptekst og mer moderne dashboard-hierarki.",
    "Analysemotor og datainnhenting er ikke endret i denne designrunden.",
]


def get_app_version() -> str:
    return APP_VERSION


def get_app_build_label() -> str:
    return APP_BUILD_LABEL


def get_version_label() -> str:
    return APP_BUILD_LABEL


def get_patch_notes() -> list[str]:
    return list(APP_PATCH_NOTES)
