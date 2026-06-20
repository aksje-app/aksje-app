APP_VERSION = "v18.6.65"
APP_VERSION_NAME = "Global Compact UI"
APP_BUILD_LABEL = APP_VERSION

CHANGELOG = [
    "v18.6.65: Global Compact UI: reduserer overbrede tallfelt, tekstfelt, selectbokser, slidere, knapper og metric-kort globalt uten å endre motorlogikk.",
    "v18.6.63: Navigation Repair: menyklikk rydder gammel Long Engine-state før nytt panel åpnes; Dashboard/Analyse/Top Picks/Long/AI/System skal ikke låses til Long. Long Engine-søk får progressbar.",
    "v18.6.62: Long Engine får aktiv horisontvelger 1M/3M/6M med standard 3M, manuelle confidence-terskler, rangering etter valgt horisont og strammere grønn/gul/rød-kalibrering.",
    "v18.6.61: Navigation Session Lock Fix: URL-panel låser ikke lenger appen til Long Engine; venstremeny og Lukk oppgave skal fungere uten ny login, mens refresh/new login fortsatt huskes via fil-state.",
    "v18.6.60: Navigation Hotfix: menyknapper holder login/session, layout er komprimert, Long Engine confidence/risiko kalibrert og Paper Trading får stop-loss cooldown.",
    "v18.6.59: Navigation State Fix: venstremenyen bruker ekte URL-lenker slik at Dashboard, Analyse, Top Picks, AI og System reagerer igjen samtidig som Long Engine og persistent state beholdes.",
    "v18.6.58: Persistent UI State slik at refresh beholder aktiv side/motor og Long Engine kan lese siste resultater fra cache.",
    "v18.6.57: Long Engine Decision View med 1M/3M/6M-horisonter, kompakt/detaljvisning, tydelig land/børs/sektor, datakvalitet, exclusive-badge og forbedret kandidatforklaring.",
    "v18.6.56: Long Engine Professional Table med land/flagg, selskapsnavn, børs, sektor, kompakte kolonner, filtre for land/sektor/risiko/exclusive og bedre kandidatkort.",
    "v18.6.54: Long Engine flyttet til egen hovedgruppe, venstre/mobilknapp åpner direkte, kandidatkort, confidence/risiko/forklaring og CSV/Excel/Print-PDF/JSON eksport lagt til.",
    "v18.6.53: Long Engine Alpha gjort synlig i UI med egen Kontrollsenter-fane, kjør-knapp, Top Long USA Alpha-tabell og overlap-score mot Top Picks.",
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
