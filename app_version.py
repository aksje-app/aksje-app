APP_VERSION = "v18.6.46"
APP_VERSION_NAME = "Mobile nav and sidebar text fix"
APP_BUILD_LABEL = APP_VERSION

CHANGELOG = [
    "v18.6.46: Mobil bunnmeny bruker ekte lenker/query-param og setter Kontrollsenter-state; Admin/Drift-sidebar bredde/tekstklipping strammet opp; KPI debug skjult bak kpi_debug=1.",
    "v18.6.45: Midlertidig KPI DEBUG-panel viste råfelt, kilde, snapshot og klassifisering fra Top Picks/ranking.",
    "v18.6.44: Mobilnavigasjon renderes i hoved-DOM som fast bunnmeny, uavhengig av Streamlit-sidebar.",
    "v18.6.43: Gjenopprettet get_app_build_label() som brukes av app.py og workspace_layout.py.",
]

def get_app_version():
    return APP_VERSION


def get_app_version_label():
    return APP_VERSION


def get_app_build_label():
    return APP_BUILD_LABEL
