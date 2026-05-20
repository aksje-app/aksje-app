APP_VERSION = "v18.6.3ac"
APP_VERSION_NAME = "Paper Control Testing UX Polish"
APP_BUILD_ID = "v1863ac-paper-control-testing-ux-polish"
APP_BUILD_LABEL = f"{APP_VERSION} - {APP_VERSION_NAME}"

APP_PATCH_NOTES = [
    "Felles markedsvalg er videreført i AI Kontrollsenter, Top Picks, Smart Universe, banner og Fond/ETF.",
    "Finland, Danmark og Brasil er synlige valg der markedsmotoren brukes, mens Norden samler Norge, Sverige, Finland og Danmark.",
    "Smart Universe-tabeller viser selskap, land, børs, status, score, risiko og forklaring i stedet for bare ticker.",
    "Fond/ETF har marked/region, automatisk benchmark og tydelig melding når pris-/NAV-data mangler.",
    "Små tekster, statusrader og mørke tabeller er gjort mer lesbare på PC og mobil.",
    "Paper Trading viser aksjekjÃ¸p igjen, henter pris/NAV tydeligere og viser gjeldende trading-strategi.",
    "Mobil-login, Smart AI-statuskort og Analyseunivers-oppsett er forbedret for mindre friksjon.",
    "AI Kontrollsenter er gjort tydeligere som hovedarbeidsflate med større header og aktivt panel.",
    "Apne AI Kontrollsenter-linjen er gjort tydeligere og friskere, og importfeil i Kontrollsenter-header er rettet.",
    "AI Kontrollsenter-valgene er gjort lysere/storre, panelvalg synkroniseres med arbeidsomrade, og Paper Trading nullstiller gammel pris ved tickerbytte.",
    "Paper Trading bruker markedsmotoren til prisforslag/system-confidence og viser posisjonsgevinst/-tap i tydelige blaa/rode kort.",
    "Strategi-test Pro har tryggere kraftig smart-test, tydeligere tidlig stopp og hopper over enkeltkombinasjoner som feiler.",
]

def get_app_version():
    return APP_VERSION

def get_app_build_label():
    return APP_BUILD_LABEL

def get_app_version_label():
    return APP_BUILD_LABEL

def get_app_patch_notes():
    return list(APP_PATCH_NOTES)
