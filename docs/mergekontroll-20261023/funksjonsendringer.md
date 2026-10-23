# Endringer i eksisterende funksjoner mot main

Dette er hele settet på 33 endrede eksisterende Python-filer i runtime/verktøy,
ikke bare ny restartkode. Tabellen beskriver funksjonell virkning uten restart
og skiller denne fra kontekstavhengig ny bokføring. Endringene er i hovedsak fra
tidligere faser av PR #167; denne siste kontrollen retter bare Autonomis kursvei
for eide tickere og legger til regresjonstester/dokumentasjon.

Det er derfor **ikke korrekt å si at PR-en bare legger til sperret restartkode**.
Selv med `restart_context=None` gjelder flere rettinger av økonomisk dokumentasjon,
rapportering, forskning, synkronisering og brukerflyt. Operative strategi-
terskler er ikke endret, men forskningssimuleringens stoppmodell er korrigert.

| Eksisterende fil | Endring og virkning |
|---|---|
| `autonomous_portfolio.py` | Ferske dokumenterte utførelseskurser for ordinære kjøp/salg; deduplisering ved handelsspeiling; strategiversjon-import; læringssnapshot tas etter kursvalidering. Reset er sperret og rapporter merker gammelt bruttoresultat. Denne kontrollen retter risikotilsyn for eide tickere uten kandidat, med gyldig datert kursbevis fra posisjon eller separat leverandør. Restartens NOK-sizing er kontekstavhengig. |
| `autonomy_modes.py` | Eksplisitt valgt arbeidsflate åpner ekspertvisning; endrer bare UI-preferanse, ingen handelsregel. |
| `investment_pipeline.py` | Historisk validering merkes IKKE VERIFISERT uten dokumentert evidens/testperiode/utvalg; scoreformelen er ikke endret. |
| `learning_experiments.py` | Snapshot bevarer execution_quote/market_data_at; vellykket write_json med returverdi None tolkes korrekt, og feil registreres. |
| `market_intelligence.py` | Rapportpakke får spinner; porteføljesnapshot etter Autonomi inkluderer anvendte parametere for etterprøvbar rapport. |
| `navigation_state.py` | Unngår identisk skriving til allerede opprettet Streamlit-widget under checkpoint-gjenoppretting. |
| `pages/autonomy.py` | Eksplisitte navigasjonsmål etablerer riktig arbeidsflate før moduswidgeten bygges. |
| `pages/paper_trading.py` | Diagnose-ZIP inkluderer separat NOK-status og merking av gammel historikk. Reset og direkte ujournalført kapitaloverskriving fjernes; vanlig handel og beholdningslagring består. |
| `pages/super_portfolio.py` | Benchmark uten datagrunnlag vises som utilgjengelig; gyldig nullavkastning beholdes. Kostnadsresultat merkes modellestimat. Lesepanel for separat NOK-periode. |
| `pages/superfund.py` | Lesepanel for revisjon av Superfonds eksisterende modell. Ingen restartkonto eller parallelt fondslager. |
| `paper_store.py` | Destruktiv reset sperres før skriving. Eksplisitt NOK-fill-adapter legges til; vanlig load/save/add_trade endres ikke. |
| `paper_trading_guard.py` | Restart-session bruker separat handlingskontekst. Uten session brukes eksisterende sentrale sperrer og ordinært register. |
| `paper_trading_professional.py` | holding_days tar valgfritt now; uten dette er vanlig klokke og holderegel uendret. |
| `portfolio_history_optimizer.py` | Historisk forskning bruker ikke-overlappende kapital, ny metodeversjon og ny beregningsprogresjon. Gamle resultater slettes ikke, men brukes ikke som om de var beregnet med rettet metode. |
| `public_report_ui.py` | Delingskontroller rendres i appens HTML-kontekst fremfor iframe for fungerende nettleser-/mobilhandlinger. |
| `quality_valuation_ui.py` | PDF skiller markedsdekning fra antall selskaper med dybdeanalyse; endrer ikke verdsettelsesmodellen. |
| `report_portfolio_intelligence.py` | Råd om salg bruker samme basisscore, holdetimer, RSI og exitpolicy som motoren; merkes rådgivende og krever fersk utførelseskurs. Økonomisk revisjonsstatus vedlegges. |
| `research_findings_dashboard.py` | Skjuler forskningsresultater med gammel metodeversjon og teller dem som ugyldig metode; læring og råhistorikk slettes ikke. |
| `scheduled_runner.py` | Rapportreparasjon trekkes ut til egen avgrenset feilfangende vedlikeholdsfunksjon; feil kan ikke blokkere kontroll av forfalte jobber. Ingen restartkontovalg. |
| `services/simulated_execution_service.py` | Eksplisitt økonomisk skjema bruker basisvalutamotor. Ordinær legacy-speiling støtter SELL_PARTIAL, reparerer avbrutt ordre/fill-speiling fra opprinnelig hendelse og bevarer strategi-/kostnadsproveniens; bokfører ikke kontanter på nytt. |
| `services/strategy_account_service.py` | Legacy-synkronisering avviser allerede opprettet basisvalutakonto. Vanlige legacy-kontoer beholder sync/verdsetting; økonomiske kontoer får verifisert NAV og nettoavkastning. |
| `services/super_portfolio_store.py` | Eksport inkluderer separat NOK-regnskapsstatus; eksplisitt ny fill-adapter. Vanlig commit og transaksjonslagring er uendret. |
| `strategy_history_worker.py` | Historiske stopp kan treffe allerede i kjøpsdagens LOW; valgfritt ikke-overlappende kapitalforløp. Bare forskningssimulering, ikke operative stop-loss-regler. |
| `super_portfolio.py` | Benchmark har fast startdato og ukjent sammenlignbarhet merkes; scheduler oppfrisker benchmark i minnet uten konkurrerende commit. Restartens posisjoner/oppgjør velges bare med eksplisitt kontekst. |
| `superfund_data.py` | nok_quote bevarer dokumentert ECB-kildedato som allerede brukes av eksisterende nok_rate; kursberegningen endres ikke. |
| `superfund_diagnostics.py` | Diagnosepakke inkluderer revisjonsresultat fra eksisterende fondsmodell. |
| `superfund_engine.py` | Native journal utvides med antall, brutto, kostnadskomponenter, kurs/FX-bevis og åpningsproveniens. Fjerner trunkering av eldre handler/tap og NAV. Handels-/risikoregler og NOK-oppgjør beholdes. |
| `superfund_reports.py` | CSV og PDF viser regnskapsstatus og kostnadsgrunnlag, med eksplisitt merking av uverifisert eldre historikk. |
| `superfund_runtime.py` | Registrerer FX-bevis sammen med eksisterende nok_rate på katalog-/cacheoppdatering. Ingen kobling til nye aksjekontoer. |
| `tools/build_safe_distribution.py` | Distribusjonspakken inkluderer dokumenter for gjeldende release, fremfor historiske release-/acceptance-/deploy-filer. |
| `tools/ui_sidebar_stable.py` | Navigasjon lagres per sanert brukernavn i runtime, fremfor delt datafil i repositoryet. |
| `trading_engine.py` | Eksplisitt restartkontekst får isolert portefølje/rules/audit og NOK-bokføring. Klokkehjelper og valgfri now muliggjør simulering; uten kontekst brukes ordinær klokke og gamle kjøp/salg/lagring. |
| `ui_sidebar_stable.py` | Samme retting av per-bruker navigasjon/runtime-lagring som verktøykopien. |

`funksjonsendringer.json` lister alle endrede, nye og fjernede funksjons-/klassesymboler per fil, beregnet fra AST mot hentet main. Nye regnskapsmoduler og tester/dokumentasjon er ikke skjult som endringer i gamle funksjoner.
