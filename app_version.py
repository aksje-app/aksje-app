APP_VERSION = "v18.6.41"
APP_VERSION_NAME = "Stabiliseringspakke: audit, modulert sidebar og KPI-cache"
APP_BUILD_ID = "v18641-stabilization-package"
APP_BUILD_LABEL = APP_VERSION

APP_PATCH_NOTES = [
    "v18.6.41: Stabiliseringspakke etter flere UI-regresjoner.",
    "Sidebar-rendering er flyttet ut av app.py til ui_sidebar_stable.py.",
    "KPI-kort beholder siste gyldige data og overskriver ikke med tomme rerun-verdier.",
    "Audit- og verifikasjonsnotater lagt ved for videre arbeid.",
]


def get_app_version() -> str:
    return APP_VERSION


def get_app_build_label() -> str:
    return APP_BUILD_LABEL


def get_version_label() -> str:
    return APP_BUILD_LABEL


def get_patch_notes() -> list[str]:
    return list(APP_PATCH_NOTES)
