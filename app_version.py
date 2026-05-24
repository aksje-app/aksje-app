APP_VERSION = "v18.6.3bf"
APP_VERSION_NAME = "NBIM Priority Views"
APP_BUILD_ID = "v1863bf-nbim-priority-views"
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
    "Datakilde-status viser naa API-nokler i aktivt miljo uten aa hevde at .env mangler, og lange kildefeil komprimeres i kandidatkortene.",
    "Aktørregister lar deg redigere bjellesauer/institusjoner/insider-watch med alias per marked, og radarene bruker dette til aa merke aktorspor.",
    "Norden/Brasil faar lokale kildediagnostikk-lenker for insider, flagging, borsmeldinger, OAM og katalysator-sok der globale API-er ikke dekker markedet.",
    "Early Warning bruker resultat-/vendepunkt-proxy naar earnings/revisions mangler, og rapportene viser tydeligere datadiagnostikk for tomme felt.",
    "Oljefond Radar kan importere NBIM CSV, finne nye/okte/reduserte/solgte posisjoner og sende NBIM-spor videre til Beslutningsgrunnlag.",
    "Beslutningsgrunnlag har tydeligere knapper: Vurder hele køen og Tøm kø.",
    "NBIM-parseren leser naa ekte eq_YYYYMMDD.csv fra Oljefondet i UTF-16/semikolon-format og matcher selskapsnavn/land mot tickerregisteret.",
    "Tickeruniversene er utvidet for USA, Norge, Sverige, Finland, Danmark og Brasil, og run-preview sier tydelig naar universkilden er mindre enn maks scan.",
    "Aktørregisteret har import/eksport for CSV/JSON, relevante tickere og NBIM/Oljefondet som aktiv institusjonell aktor.",
    "Radarene kan bruke finans-/offisiell sokelag ved Kjor, med aktornavn, alias, ticker, selskap og marked, uten tunge kall ved menyvalg.",
    "NBIM, finanssok, aktorregister og konkrete insider-/bjellesau-spor sendes videre til Alpha Radar, Early Warning, rapporter og Beslutningsgrunnlag.",
    "Oljefond Radar har prioriterte visninger for topp signaler, storste beholdninger, nye kjop, okninger, reduksjoner med restverdi, solgt ut, ticker-match og land/sektor.",
    "NBIM-tabeller viser markedsverdi med punkt som tusenskille og enhet, og previous/current value oversettes per metric til prosent, aksjer eller valuta.",
]

def get_app_version():
    return APP_VERSION

def get_app_build_label():
    return APP_BUILD_LABEL

def get_app_version_label():
    return APP_BUILD_LABEL

def get_app_patch_notes():
    return list(APP_PATCH_NOTES)
