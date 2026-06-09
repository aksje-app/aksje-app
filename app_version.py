APP_VERSION = "v18.6.42"
APP_VERSION_NAME = "KPI, mobilmeny, Top Picks-sortering og lesbarhet"
APP_BUILD_LABEL = APP_VERSION
APP_PATCH_NOTES = [
    "v18.6.42: KPI beholder siste gyldige Top Picks-data og oppdateres fra synlige kandidater.",
    "v18.6.42: Mobilmeny er gjort om til bunnnavigasjon slik at hovedvinduet ikke blokkeres.",
    "v18.6.42: Top Picks sorteres primært etter total score; Kjøp nå har egen visning.",
    "v18.6.42: Høyresiden i kandidatkortene har større tekst og mindre overlapp.",
]

def get_app_version():
    return APP_VERSION

def get_app_version_badge():
    return APP_BUILD_LABEL
