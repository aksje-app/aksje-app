APP_VERSION = "v18.6.40"
APP_VERSION_NAME = "Mobilmeny gjort brukbar igjen"
APP_BUILD_ID = "v18640-mobile-sidebar-guard"
APP_BUILD_LABEL = APP_VERSION

APP_PATCH_NOTES = [
    "v18.6.40: Mobilvisning av venstremeny er endret til smal ikon-rail slik at hovedvinduet ikke blokkeres.",
    "Streamlit-sidepiler som kunne låse mobilvisningen er skjult på mobil.",
    "Desktop-menyen fra v18.6.39 beholdes.",
    "Ingen endringer i analysemotor eller datainnhenting.",
]


def get_app_version() -> str:
    return APP_VERSION


def get_app_build_label() -> str:
    return APP_BUILD_LABEL


def get_version_label() -> str:
    return APP_BUILD_LABEL


def get_patch_notes() -> list[str]:
    return list(APP_PATCH_NOTES)
