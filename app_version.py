APP_VERSION = "v18.6.31"
APP_VERSION_NAME = "Dashboard 2026"
APP_BUILD_ID = "v18631-dashboard-2026"
APP_BUILD_LABEL = f"{APP_VERSION} - {APP_VERSION_NAME}"

APP_PATCH_NOTES = [
    "Dashboard 2026: lagt inn fire KPI-kort øverst for BUY, SELL, varsler og beste kandidat.",
    "Komprimert ticker-bannerområdet og redusert visuell høyde på bannerkortene.",
    "AI Kontrollsenter er flyttet visuelt frem som hovedarbeidsflate, uten gammel expander-innramming.",
    "Modernisert kontrollsenter-valg med større kortpreg, tydeligere hierarki og færre blå rammer.",
    "Analysemotor og datamoduler er ikke endret i denne designrunden.",
]


def get_app_version() -> str:
    return APP_VERSION


def get_app_build_label() -> str:
    return APP_BUILD_LABEL


def get_version_label() -> str:
    return APP_BUILD_LABEL


def get_patch_notes() -> list[str]:
    return list(APP_PATCH_NOTES)
