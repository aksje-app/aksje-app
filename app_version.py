APP_VERSION = "v18.6.30"
APP_VERSION_NAME = "Clean kodebase og slanket app.py"
APP_BUILD_ID = "v18630-clean-codebase"
APP_BUILD_LABEL = f"{APP_VERSION} - {APP_VERSION_NAME}"

APP_PATCH_NOTES = [
    "Slanket app.py ved å fjerne eldre toppnivå-funksjoner som allerede ble overskrevet senere i samme fil.",
    "Fjernet genererte __pycache__-/pyc-filer fra prosjektpakken slik at zip-en blir renere og mindre.",
    "Ryddet versjonsmerking slik at appen ikke blander v18.6.28/v18.6.29 i toppfeltet.",
    "Beholdt funksjonsmoduler og analyser intakt for å redusere risiko for regresjon.",
    "Compile-test er kjørt på hele prosjektet etter opprydding.",
]


def get_app_version() -> str:
    return APP_VERSION


def get_app_build_label() -> str:
    return APP_BUILD_LABEL


def get_version_label() -> str:
    return APP_BUILD_LABEL


def get_patch_notes() -> list[str]:
    return list(APP_PATCH_NOTES)
