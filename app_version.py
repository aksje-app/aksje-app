APP_VERSION = "v18.6.50"
APP_VERSION_NAME = "Navigation rebuild"
APP_BUILD_LABEL = APP_VERSION

CHANGELOG = [
    "v18.6.50: Venstremeny bygget om til ekte Streamlit-knapper; HTML-kort som så klikkbare ut, men var døde, er fjernet fra sidebar-renderingen; Admin/Drift ligger fortsatt i toppmeny.",
    "v18.6.49: Admin/Drift fjernet helt fra venstremeny etter TRACE; Admin/Drift styres kun fra toppmenyen; sidebar trace fjernet.",
    "v18.6.47: Admin/Drift flyttet ut av sidebar til toppmeny; Auto/Paper Trading-status vises i toppstatus; sidebar holdes ren; runtime/cache ryddet uten å slette viktige tjenestedata.",
    "v18.6.46: Mobil bunnmeny bruker ekte lenker/query-param og setter Kontrollsenter-state; Admin/Drift-sidebar bredde/tekstklipping strammet opp; KPI debug skjult bak kpi_debug=1.",
    "v18.6.45: Midlertidig KPI DEBUG-panel viste råfelt, kilde, snapshot og klassifisering fra Top Picks/ranking.",
]

def get_app_version():
    return APP_VERSION


def get_app_version_label():
    return APP_VERSION


def get_app_build_label():
    return APP_BUILD_LABEL
