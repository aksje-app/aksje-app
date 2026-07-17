APP_VERSION = "v18.6.78a"
APP_VERSION_NAME = "Currency Alert Diagnostic & Repair"
APP_BUILD_LABEL = APP_VERSION

CHANGELOG = [
    "v18.6.78a: Currency Alert Diagnostic & Repair: valutakontrollen kjører før aksjescannerens markedstids- og cooldown-gate, full varselkjedetest er lagt til, og runtime-status/hendelseslogg gjør alle stoppårsaker synlige.",
    "v18.6.78: Paper Trading Professional: delvise salg, målpris, planlagt risikobeløp og R-multiple, kapitalbinding, exit-prioritet, posisjonskort og passiv exit-simulering. Ingen ekte handel eller autonom strategiendring er aktivert.",
    "v18.6.76: Performance & Explainability: global panelprofilering med render-tider, rerun-teller, cache/API-metrikk og eget Performance Dashboard. Paper Trading lagrer strukturert Explain AI-grunnlag for kjøp og salg i audit/replay uten å endre handelsregler.",
    "v18.6.75: AI Learning Foundation + Alert/Lifecycle Repair: valutavarsler kjører i bakgrunnsscanner uavhengig av børsåpning og gjentar brudd etter cooldown; Paper Trading beskytter nye posisjoner mot raske signal-flip SELL/AVOID med minimum holdetid, mens harde risikoutganger beholdes; AI Discovery får passiv Learning Queue, Trade Outcomes, Signal Scorecard, Confidence Calibration, Exit Analytics og Audit/Replay uten automatisk regelendring.",
    "v18.6.74e: Performance + Existing Position Repair: skjult save_portfolio ved vanlig Paper Trading-visning er stoppet, trailing stop-status/avstand beregnes kun i visningen, trading-regler/posisjonsrader gjenbrukes i samme render, Hypoteser/Test lazy-loader paper-flow først når fanen åpnes, URL-state skrives ikke ved no-op, og aksjekjøp kan nå øke eksisterende posisjon med vektet snittkurs.",
    "v18.6.74d: Paper Trading Risk + Trailing Stop Repair: trailing stop lagres som per-posisjon-regel ved kjøp, høyeste kurs etter kjøp oppdateres, trailing stop-nivå/avstand/status vises i Portefølje, Varsler får NÆR STOP/STOP UTLØST, REVIEW_ONLY review_queue kontrolleres videre, blokkårsaker vises mer kompakt, og browser-refresh state forsterkes på tvers av hovedpaneler.",
    "v18.6.74c: Global State + Review Queue: browser refresh/F5 gjenoppretter hovedområde, panel og intern fane via aa_nav/aa_group/aa_panel/aa_tab uten å slette remember_token. Paper Trading får review_queue under Hypoteser/Test; REVIEW_ONLY gjennomfører ikke kjøp, men lagrer kandidat som gult flagg med status ÅPEN/GODKJENT/AVVIST/KJØPT, notat, Avvis og Kjøp manuelt.",
    "v18.6.74a: Panel State + Manual Override Repair: AI Discovery Foundation blir liggende under Andre paneler, aktivt hovedområde/panel synkes før toppstatus rendres, Signal Discovery lazy-loades uten circular import, og Paper Trading får eksplisitt manuell overstyring med OFF som ufarlig standard, FORCE_BLOCK som eneste manuelle blokkering, FORCE_ALLOW for myke regler og tydelige blokkårsaker.",
    "v18.6.73: Signal Discovery: passiv mining av kandidatsignaler fra AI Discovery-observasjoner/resultater, kandidat-tabell, rapport og promotering til Signal Library som OBSERVE. Learning Loop er fortsatt AV og ingen motorlogikk endres.",
    "v18.6.72: AI Discovery Foundation: Signal Library, Signal Tracking, Resultatdatabase, Historikk og Rapportering. Learning Loop er AV; ingen motorlogikk eller tradingbeslutninger endres.",
    "v18.6.71: Paper Trading Architecture Rebuild: Paper Trading delt i fem arbeidsområder (Handel, Portefølje, Regler, Varsler, Hypoteser/Test); eksisterende funksjoner flyttet til riktige faner; blokkeringer viser mer konkret årsak uten motorlogikk-endring.",
    "v18.6.68: Paper Trading Layout Rebuild: aksjekjop og aksjesalg bygget om til kompakte arbeidskort; antall, confidence, systemvurdering og beholdning vises som badges; blokkering ved maks åpne posisjoner viser faktisk aktiv grense og opptelling.",
    "v18.6.70: Functional Fixes: Grafmodus Standard/Teknisk/Avansert styrer faktisk indikatorer/grafnøkler; Paper Trading får tydeligere blokkeringer, re-entry cooldown UI og aktiv lagring til trading_rules; Long Engine confidence/risiko beholdes kalibrert.",
    "v18.6.66: Professional UI Refactor: global tetthet for tallfelt, datofelt, selectbokser, KPI-kort, expandere og store containere. Ingen motorlogikk endret.",
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
