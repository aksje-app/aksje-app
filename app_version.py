APP_VERSION = "v18.6.3x"
APP_VERSION_NAME = "Responsible UI Market Fund Cleanup"
APP_BUILD_ID = "v1863x-responsible-ui-market-fund-cleanup"
APP_BUILD_LABEL = f"{APP_VERSION} - {APP_VERSION_NAME}"

APP_PATCH_NOTES = [
    "Felles markedsvalg er videreført i AI Kontrollsenter, Top Picks, Smart Universe, banner og Fond/ETF.",
    "Finland, Danmark og Brasil er synlige valg der markedsmotoren brukes, mens Norden samler Norge, Sverige, Finland og Danmark.",
    "Smart Universe-tabeller viser selskap, land, børs, status, score, risiko og forklaring i stedet for bare ticker.",
    "Fond/ETF har marked/region, automatisk benchmark og tydelig melding når pris-/NAV-data mangler.",
    "Små tekster, statusrader og mørke tabeller er gjort mer lesbare på PC og mobil.",
]

def get_app_version():
    return APP_VERSION

def get_app_build_label():
    return APP_BUILD_LABEL

def get_app_version_label():
    return APP_BUILD_LABEL

def get_app_patch_notes():
    return list(APP_PATCH_NOTES)
