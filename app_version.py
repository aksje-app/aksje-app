APP_VERSION = "v18.6.48"
APP_VERSION_NAME = "UI cleanup and runtime data hygiene"
APP_BUILD_LABEL = APP_VERSION

CHANGELOG = [
    "v18.6.48: Midlertidig sidebar trace/debug viser nøyaktig hvilke sidebar/admin/drift-komponenter som renderer Admin/Drift i venstremenyen.",
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
