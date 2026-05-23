APP_VERSION = "v18.6.3bb"
APP_VERSION_NAME = "Radar Data Source Diagnostics"
APP_BUILD_ID = "v1863bb-radar-data-source-diagnostics"
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
    "AI Kontrollsenter-valgene er rendret som tydeligere blaa kontrollbokser, og den lille dupliserte toppstripen er fjernet.",
    "P/E vises i Top Picks/hurtigkort i tillegg til detaljanalysen, basert paa forward/trailing P/E fra felles aksjeanalyse.",
    "Learning history skjuler demo-/testtickere fra brukerlisten og viser tolkning av retning, prognosebaand og snittfeil.",
    "Topplinjen er ryddet for sesjonschips som Manuell, Bruker og Husk meg.",
    "Heatmap filtrerer bort gamle AAPL/STB.OL-seeddata og bruker samme filtrerte datasett for tall og visning.",
    "Tekniske kursnivaer viser valuta tydeligere, ORK/ORKLY tolkes som ORK.OL, og chart/legend-spacing er forbedret.",
    "Regime-panelet har markedvalg for USA, Norge, Sverige, Danmark, Finland, Brasil og Norden.",
    "Paper Trading-portefoljen kan brukes som testarena for portefoljeovervaking, kontrollpunkter og AI-forslag.",
    "AI Kontrollsenter har valutavarsler med faste ovre/nedre grenser og Pushover-stotte, for eksempel BRL/NOK.",
    "AI Kontrollsenter har hovedboks-rad, automatisk undermeny, favoritter, sist brukt, sok, arbeidsmodus og paneltellere.",
    "AI Kontrollsenter bruker ren hurtignavigasjon uten skjulte gamle dropdowns, med tydelig Til hovedvalg-knapp.",
    "AI Kontrollsenter er forenklet til hovedbokser og kompakt undermeny, uten automatisk aapnet startpanel.",
    "AI Kontrollsenter bruker stabil radio-basert hovedmeny og undermeny for mindre knekk ved menyvalg.",
    "AI Kontrollsenter-navigasjon unngaar ekstra rerun og hopper over ticker-banneret under aktiv menybruk.",
    "Gamle AAPL/MSFT/NVDA-defaults er fjernet fra Daily Report, Prognose og service-univers, og tester stopper skjult manuell fallback.",
    "Regresjonsvern er utvidet for kildeprioritet, panel-smoke, tung-jobb gating og visuelle statiske guardrails.",
    "Oppstart av Kontrollsenter nuller engangsflagget for tung jobb slik at ticker-banneret ikke forsinker Analyseunivers/preview.",
    "Analyseunivers forklarer tydelig forskjellen mellom tickerliste/univers, preview-cache og scorede Smart AI-kandidater.",
    "AI Kontrollsenter har Alpha Radar som eksplisitt kjoert hypotesemotor for 1-15 mulige aksjecaser paa 1, 3, 6 og 12 maaneder.",
    "Alpha Radar V2 bruker Contrarian / Hidden Potential Score med underdekkethet, vendepunkt, insider/bjellesauer, uvanlig volum, ravare/makro, why-now og crowding-straff.",
    "Alpha Radar har strengere parameterdisiplin med harde borsverdi-gates, presisjonsvalg, lav-data blokkering og tydelige ekskluderingsaarsaker.",
    "Alpha Radar viser scan-progresjon, skiller signal-lupe fra datakilder, markerer gamle resultater naar input endres og kan lagre/eksportere resultat.",
    "Alpha Radar viser manglende faktorgrunnlag som N/A, stopper univershenting ved vanlige menyvalg, har komplett print/Excel-eksport og Early Warning V1.",
    "Early Warning er skilt tydeligere fra Alpha Radar med ferske kildebevis, insider-/bjellesau-spor, nyhetskatalysatorer og Euronext/Norden-notat i rapportene.",
    "Alpha Radar/Early Warning-rapportene viser kildespor med titler, kilder, datoer og lenker der datakilden leverer dette.",
    "Mobilvisning for driftkontroll og Alpha Radar Signal-lupe er strammet inn uten aa flytte tunge jobber ut fra eksplisitte Kjor-knapper.",
    "Alpha Radar og Early Warning bruker felles regelmotor for Signal-lupe, datakilder, laasing, lav-data og overstyringsrekkefolge.",
    "Radar-panelet viser Kjoringsbudsjett / Run Preview med 0 tunge kall ved menyvalg og planlagt kostnad ved Kjor.",
    "Neste GO: hvis appen fortsatt dimmer ved menyvalg, profiler hele Kontrollsenter-renderen og flytt gjenvaerende cache-/statuskall ut bak eksplisitte knapper.",
    "Radar-menyene er strammet: Radar-modus laaser kjerne-signalene, ekstra Signal-lupe er separat, og datakilder folger samme regelmodell.",
    "Insider-modus i Alpha Radar starter naa med Insider/bjellesauer alene; nyheter/resultater blir kun stottevalg hvis bruker legger dem til.",
    "Kontrollsenter avslutter tung-jobb-gaten foer st.stop, slik at Global oppdatering ikke blir hengende igjen og gjor senere menyvalg tunge.",
    "Alpha Radar og Early Warning henter alltid ferskt run-univers ved Kjor, nuller gammel tickerliste og viser markedstelling for univers, skannet, scoret, ekskludert og funn.",
    "Alle/Norden bruker balansert sluttliste: beste funn per marked tas med foer resten fylles etter score, slik at USA ikke kan skjule alle andre markeder uten forklaring.",
    "Funn-grensen er utvidet til 60 for brede univers, og IPO/pre-IPO forklares som separat omraade, ikke som skjult tillegg i 177-universet.",
    "Radarene krever naa konkret nyhets-/makro-/resultatevidens foer faktorer merkes ekte, slik at tomme kildesok ikke gir lik 45.0-katalysator paa alle tickere.",
    "Borsverdi vises med punkt som tusenskille og lokal valuta, med ca. NOK-estimat der valuta ikke er NOK.",
    "Enkeltmarked bruker egen skannegrense i Alpha Radar/Early Warning, Brasil-listen er utvidet, og 177 behandles ikke som fast globalt tak.",
    "Alpha Radar og Early Warning skiller naa Insider fra Bjellesau i scoring, kildespor, CSV, Excel, HTML/PDF og resultatkort.",
    "AI Kontrollsenter har nytt Beslutningsgrunnlag-panel som tar radarfunn videre til manuell Kjop naa/Vent/Unnga-vurdering uten automatisk handel.",
    "Finnhub- og NewsAPI-nokler lastes naa robust fra work_d/.env eller work_d/.env/.env, og radarene viser trygg datakilde-status uten aa vise nokler.",
    "Alpha Radar/Early Warning lar 1, 3, 6 og 12 mnd styre datavinduet for insider, nyheter og earnings, og har egen markedstest for USA/Norden-datakilder.",
]

def get_app_version():
    return APP_VERSION

def get_app_build_label():
    return APP_BUILD_LABEL

def get_app_version_label():
    return APP_BUILD_LABEL

def get_app_patch_notes():
    return list(APP_PATCH_NOTES)
