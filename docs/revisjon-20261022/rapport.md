# Aksjeappen – feilretting og funksjonsrevisjon 22. oktober 2026

## Konklusjon og avgrensning

Arbeidet bygger på `main` ved `f0ef5b491219c2a1232bff30cc9b37eed58bc479`, etter PR #162–165. Endringene ligger på `fix/systemrevisjon-20261022`. Main, Render og produksjonsdata er ikke endret.

F1, F2 og F4–F10 er rettet innenfor de konkrete feiltilfellene beskrevet nedenfor. F3 er **delvis håndtert**: feilaktige sammenligninger og udokumenterte økonomiske påstander er begrenset, men Paper Trading og Autonomi har fortsatt et eldre regnskap uten fullstendig valutakonvertering og kostnadsføring. Superporteføljens prisforholdsmodell er heller ikke blitt et valutaregulert aksjeregnskap. Denne rapporten erklærer derfor ikke hele oppdraget eller systemet ferdig godkjent.

Det finnes heller ikke bevis for at hver knapp og hvert brukerforløp er testet. Den maskinelle kontrolloversikten skiller statiske deklarasjoner fra faktisk utførte nettleserhandlinger. Utestede funksjoner er IKKE VERIFISERT.

Bevisnivåer: **kode** viser implementert oppførsel, **test** viser observerte resultater med avgrensede testdata, **produksjon** viser bare de opplastede diagnosefilene, og **hypotese** er en mulig økonomisk forklaring uten bevist effekt.

## Funn og rettinger

| Funn | Håndtering | Kilde i arbeidsgrenen |
|---|---|---|
| F1: egen benchmarklagring ugyldiggjør SP-revisjonen | Planlagt syklus beregner benchmark uten mellomlagring og lagrer den sammen med øvrig syklusmetadata. CAS-kontrollen mot virkelige samtidige skrivere beholdes. Testen bruker faktisk benchmark- og oppgjørslagring, ikke en erstattet benchmarkfunksjon. | `super_portfolio.py:309`, `super_portfolio.py:3266` |
| F2: gammel positiv kandidatkurs kan utløse Autonomi-salg | Kjøp, tilleggskjøp og salg krever verifisert, ujustert intradagkurs med faktisk observasjonstid. Produksjonen kan hente en ny kurs; offline-replay må få kursbevis som input. Gamle, fremtidige eller mangelfulle bevis gir ingen handel. Risikosalg trenger ikke bestå kjøpsanalysens fundamentalporter. | `autonomous_portfolio.py:711`, `autonomous_portfolio.py:1949`, `autonomous_portfolio.py:2147` |
| F3: valuta, kostnader og økonomisk avkastning | **DELVIS RETTET.** Ny skrivebeskyttet kontroll kan beregne basisvalutaverdi når faktiske aksjeantall, tidsstemplede kurser, samsvarende FX og historikk er dokumentert. Ellers returneres IKKE VERIFISERT og ingen verifisert nettoavkastning. Gamle modellposisjoner omklassifiseres ikke til faktiske aksjer. Tydelig forbehold i Paper-/Autonomi-visninger og Paper-eksport. Uverifisert alpha fjernes; manglende benchmark blir ikke 0 %. | `services/economic_accounting_audit.py:27`, `autonomous_portfolio.py:2692`, `pages/paper_trading.py:20`, `super_portfolio.py:288` |
| F4: overlappende handler forrentes som full sekvensiell kapital | Optimaliseringen bruker nå handler uten kapitaloverlapp per aksje. Trenings-, validerings- og holdout-perioder beholdes. Metoden versjoneres; eldre resultater skjules fra den aktuelle forskningsoversikten og beregnes på nytt av vanlig forskningsjobb. Dette er fortsatt en enkeltaksjebaseline, ikke replay av hele porteføljen. | `strategy_history_worker.py:18`, `portfolio_history_optimizer.py:33`, `research_findings_dashboard.py:26` |
| F5: historisk stopptest hopper over inngangsdagen | Dagens LOW kontrolleres fra inngangsdagens OPEN. Senere gap under stoppen fylles fortsatt konservativt til åpningskurs. | `strategy_history_worker.py:18` |
| F6: nøytral score 50 blir «Historisk validering BESTÅTT» | Manglende historisk dokumentasjon gir IKKE VERIFISERT. En rå score alene er utilstrekkelig: eksplisitt verifisering, antall observasjoner, evidensreferanse og testperiode kreves i tillegg til målte komponenter. Scoringsvektene er ikke endret. Dette skaffer ikke manglende historikk automatisk. | `investment_pipeline.py:570` |
| F7: delsalg mangler i felles fillhistorikk | SELL_PARTIAL speiles som en SELL-fill med original handlingskode og versjonsinformasjon. Speilingen endrer ikke kontoens penger eller aksjeantall igjen. Gjenforsøk etter avbrudd mellom ordre- og fillskriving reparerer fra den opprinnelig lagrede hendelsen, ikke en ny kurs. Manglende kostnadsgrunnlag merkes eksplisitt. | `services/simulated_execution_service.py:232` |
| F8: vellykket læringslagring meldes mislykket | `write_json` returnerer None ved suksess. Koden bruker nå kontrakten riktig og rapporterer feil ved faktisk unntak. | `learning_experiments.py:48` |
| F9: salgsrapporter følger andre holdetider og score enn motoren | Rapporten bruker faktiske timer siden siste tillegg/inngang, samme basisscore for eide posisjoner, RSI-/stopphistorikk og aktive parametre. Forslaget er uttrykkelig rådgivende, ikke en utførelsesfullmakt. Benchmarkstart følger NAV-periodens faste start, ikke eldste gjenværende aksje. | `report_portfolio_intelligence.py:179`, `market_intelligence.py:6809`, `super_portfolio.py:309` |
| F10: versjonsavvik mellom konto og journal | Felles Autonomi-konto henter identitet fra samme binding som handelsjournalen. Hendelsens egen versjon beholdes ved speiling, selv om kontoens aktive versjon senere er endret. Samme trade-ID legges ikke inn på nytt i den eldre journalen. | `autonomous_portfolio.py:1668`, `autonomous_portfolio.py:2514`, `services/simulated_execution_service.py:232` |

### Ytterligere feil funnet under faktisk testing

* Paper-diagnosepanelet kunne lukke seg ved omkjøring og skjule nedlastingen. Panelet har nå stabil widgetidentitet og tilstandsbevaring (`pages/paper_trading.py:27`). ZIP-filen er lastet ned og JSON-innholdet åpnet i nettlesertestene.
* En eksplisitt rapportdestinasjon kunne forsvinne bak Autonomis enkle oversikt. Destinasjonen etablerer nå riktig visningsnivå før widgeten opprettes (`autonomy_modes.py:127`, `pages/autonomy.py:84`). Dette er en UI-preferanse; det aktiverer ingen handelsmotor.
* Orkestreringssidens bakgrunnsfragment kunne krasje ved å tilordne eksisterende widgetverdier etter opprettelsen. Uendrede verdier skrives ikke tilbake (`navigation_state.py:637`). Siden er deretter åpnet på PC og mobil uten feilen.
* Autonomi kunne bokføre en flere timer gammel åpningskurs som en ny utførelse. Neste-sesjonsåpningen brukes fortsatt til å kvalifisere inngangen, men utførelsen bruker nå en fersk dokumentert kurs. Testen med sesjonsåpning 100 og observert kurs 101 bokfører 101. Dette retter utførelsesmodellen; gapgrense og kandidatregler beholdes.
* En innsidertest brukte en fast dato som hadde falt utenfor den eksisterende 90-dagersperioden. Testdataenes dato er gjort aktuell. Innsiderstrategien er ikke endret.

## Hva som ikke er endret som investeringsstrategi

Stopptapsgrenser, trailing stop, gevinstsikringens terskler, kandidatvalg, scorevekter, risikotak, sektorgrenser, reservekrav, fredagsrebalansering og godkjenningskrav er beholdt. Strengere bevis for utførelseskurs kan endre hvilke modellhandler som faktisk kan gjennomføres og hvilken kurs de får. Gamle backtestresultater skal derfor ikke brukes som dokumentasjon for den korrigerte utførelsesmodellen.

F11 fra den brede revisjonen – mulig dårlig økonomi i kombinasjonen rask gevinstsikring og automatisk gjenfylling – er fortsatt en hypotese. Handelsreglene er ikke justert for å få et penere resultat.

## Testbevis

| Kjøring | Resultat |
|---|---|
| Sammenlignbar full pakke, uendret main | 2093 bestått, 100 feilet, 21 hoppet over |
| Sammenlignbar full pakke, rettet gren | 2113 bestått, 99 feilet, 47 hoppet over |
| Nye feilende testnavn mot main | 0 |
| Aktiv pakke, uten versjonsarkiv og ekstern live-OHLC | 628 bestått, 47 hoppet over |
| Release-workflowens kvalitetspakke | 497 bestått |
| Nye målrettede revisjonsregresjoner | 19 bestått |
| Hele-app-nettleserforløp | 24 bestått |
| Superfond-nettleserforløp | 9 bestått |
| Releasekontrakter | 24 skript bestått |
| JavaScript-deling | 5 forløp bestått |
| Python-syntaks | Bestått |

Den komplette pakken er fortsatt **FEILET**. De 99 feilende testnavnene forekommer også på uendret main; de er ikke bortforklart eller ommerket som bestått. Flere er gamle versjons-/kildeassertsjoner, men dette er ikke bevis for at samtlige er ufarlige. 47 hoppede tester er ikke 47 beståtte tester: blant annet er nettlesertestene kjørt separat med eksplisitt aktivering, mens lokale databasekrav ikke er oppfylt.

Endelige kjøringer, eksakte kommandoer og sammenligning mot uendret main finnes i `testresultater.json`, `testdifferanse.json` og vedlagte tekstlogger i denne mappen. Overlappende testpakker skal ikke summeres.

Det er kjørt faktisk Streamlit med Chromium og ufarlige, isolerte testdata. Hele-app-fixturen erstatter innlogging og eksterne leverandører og slår av bakgrunnsjobber. Autonomi aktiveres bare som fixtureinnstilling for å eksponere menyene; dette verifiserer ikke aktivering i produksjon. Testene har ikke brukt produksjonsdatabasen eller sendt eksterne varsler.

Bekreftede nettleserforløp:

* Paper Trading på 375 og 1280 piksler: åpning, generering, nedlasting og parsing av diagnose-ZIP; retur til Oversikt. ZIP inneholder manifest, portefølje, handler og regler.
* Rapporter på 375 og 1280 piksler: korrekt Rapportsenter fra eksplisitt destinasjon, og samme funksjon etter reload.
* Alle ti Autonomi-arbeidsflater på 375 og 1280 piksler: åpning og rendering uten Streamlit-unntak. Dette er ikke bevis for alle handlinger inne på flatene.
* Superfond på 375, 430 og 1280 piksler: menyer, kort, landgrupper og layout; mobilretur og gjenoppretting av valgt område.
* Superfond på 375 og 1280 piksler: faktisk nedlasting og åpning av PDF, CSV, Excel og diagnose-ZIP. PDF leses med pypdf, Excel med openpyxl, ZIP kontrolleres for integritet.

Regresjonene omfatter faktisk benchmarklagring, etterlagringsfeil og gjenforsøk, DNOs bevarte salgsdata, syntetiske BWE-/OMC-stoppscenarioer, flere samtidige handler, fullt salg, delsalg, tilleggskjøp, NAV/kontanter, holdetid over midnatt, kursbevis, metodeversjon og gammel forskningscache. BWE-/OMC-testkursene er testinput, ikke gjenfunnet produksjonsdokumentasjon.

**IKKE VERIFISERT:** lokal PostgreSQL-transaksjonskjøring, faktisk Render-oppsett etter endringen, ekte innlogging, eksterne leverandørers tilgjengelighet, faktisk Pushover-levering, fysisk mobiltelefon, Edge som eget produkt, utskriftsdialog og operativsystemets deling. Mobilbeviset er Chromium med mobilbredde. Live-OHLC-akseptansetesten er holdt utenfor den isolerte pakken fordi den krever ekstern markedsdatatilgang; den første brede kjøringen påviste leverandørfeil. Ingen slik test er ommerket til bestått.

## Funksjonsoversikt

`brukerfunksjoner.csv` angir kildefil, linje, kontrolltype, etikett, nøkkel, teststatus og bevis for hver funnet UI-deklarasjon. Deklarasjoner kan være legacy, betingede eller dynamiske; tallet er ikke et antall aktive brukerfunksjoner. Bare dokumenterte utførte kontrollhandlinger merkes BESTÅTT i listen.

| Funksjon/område | Faktisk verifisert | Status utover dette |
|---|---|---|
| Oversikt og retur fra Paper | Åpning og retur på PC/mobil | Dataaktualitet for produksjonskort: IKKE VERIFISERT |
| Enkel/avansert og hovednavigasjon | Målrettede navigasjons- og rutetester; rapportdestinasjon | Alle kombinasjoner av menyer/tilbakeknapp: IKKE VERIFISERT |
| Autonomi Oversikt | Åpning på PC/mobil | Kjøring av hele analyse-/handelskjeden fra knappen: IKKE VERIFISERT |
| Orkestrering og tidsplan | Åpning, ingen widgetkrasj | Start/avbryt/restart av faktisk schedulerjobb: IKKE VERIFISERT |
| Autonom portefølje | Åpning; modell- og kursregresjoner | Alle manuelle innstillinger/handlinger i nettleser: IKKE VERIFISERT |
| Læringsportefølje | Åpning; replay-/lagringstester | Økonomisk forbedring og alle UI-handlinger: IKKE VERIFISERT |
| Rapporter/historikk | Riktig side og reload | Alle rapporttyper med fullstendige produksjonsdata: IKKE VERIFISERT |
| Varsler og drift | Åpning; tekniske varslingstester | Levering til mottaker: IKKE VERIFISERT |
| Strategiversjoner | Åpning; metadataregresjoner | Full manuell promotering/rollback i nettleser: IKKE VERIFISERT |
| Strategy Lab | Åpning og eksisterende tester | Hele brukerløpet søk–evaluering–promotering: IKKE VERIFISERT |
| Motorresultater | Åpning | Reelle samtidige leverandørresultater: IKKE VERIFISERT |
| Ekspertkontroll | Åpning | Alle konfigurasjonsimporter/godkjenninger/tilbakerullinger: IKKE VERIFISERT |
| Paper Trading | Diagnose-ZIP og retur | Hele manuelle kjøps-/salgsflyten i nettleser: IKKE VERIFISERT |
| Superporteføljen | Oppgjør, jobbretry, stoppsalg og holdetid i regresjoner | Samtlige SP-knapper og komplette UI-forløp: IKKE VERIFISERT |
| Superfond portefølje/kandidater | Nettleser- og modelltester | Samtlige fondsbytter med produksjonsdata: IKKE VERIFISERT |
| Superfond rapporter/diagnoser | PDF/CSV/Excel/ZIP lest etter nedlasting | Alle eksterne lenker og delingsmottakere: IKKE VERIFISERT |
| Analyse, Top Picks, Long Engine og AI-verktøy | Kodekart og eksisterende tester | Komplette nettleserforløp og økonomisk verdi: IKKE VERIFISERT |
| Valuta og makro | Eksisterende tester og kildekode | Live-leveranse og alle UI-forløp: IKKE VERIFISERT |
| Kvalitet/prising og turnaround | Eksisterende regresjoner, shadow-/godkjenningsskille | Samlet nettleserflyt og historisk økonomisk effekt: IKKE VERIFISERT |
| Jobber, godkjenninger, system/admin | Kode-/regresjonsbevis for avgrensede deler | Alle brukerroller, skjemaer og handlinger: IKKE VERIFISERT |

Full funksjonsdekning er altså ikke oppnådd. En grønn renderingstest brukes ikke til å godkjenne underliggende handel, regnskap eller utsending.

## De fire porteføljene og beslutningskjeden

**Paper Trading:** tekniske signaler går via scanner, gjentatt inngangsbekreftelse og handelssikkerhet til den separate Paper-kontoen. Navigasjonsrettingene fra PR #163–165 er beholdt. Diagnoseeksporten er faktisk lastet ned. Kontoens eldre beregninger mangler fullstendig valuta og bokførte handelskostnader; tallene er ikke verifisert netto i NOK.

**Autonomi:** analyserte kandidater, godkjennings-/kvalitetsporter og teknisk bidrag kan påvirke modellinnganger. Utganger bruker basisscore og separat exitpolicy. Fersk kurs kreves ved utførelse, og risikosalg kan fortsatt skje innenfor minimumsholdetiden. Den separate lette stoppovervåkingen er fortsatt observasjonsfunksjon og bokfører ikke selv salg. Manglende kandidat i hovedsyklusen fører fortsatt til HOLD; dette er en vesentlig driftsbegrensning, ikke løst ved å finne på en kurs. Hele den eldre konto-/journal-/speilingskjeden er fortsatt ikke én atomisk databaseoperasjon.

**Superporteføljen:** selvstendig markedspipeline, risikosalg, ordinær rebalansering, begrenset gjenfylling og SPs atomiske oppgjør/journal/kvittering er beholdt. Ordinær rebalansering er normalt ukentlig; risikosalg har egen vei. Strategiske REDUSER/ØK kan utføres når motorens rebalanseringsporter åpner, mens rådgivende risikoforslag/staged-entry-preview ikke er ordre. De samme skjermordene er derfor ikke en felles automatisk fullmakt. Regnskapet er en deklarert modell med lokal prisavkastning, ikke full FX-eksponering.

**Superfond:** egen fondsmodell med datert NAV, senere kursobservasjon før utførelse, kostnads-/valutabehandling og eksplisitt godkjenning av læringsforslag. Modell- og eksporttestene er beholdt og utvidet. Dette er ikke en meglerbekreftet fondsordre. Live-katalogdekning og historisk nettoresultat i produksjon er ikke bekreftet her.

Læring er ikke én felles automatisk «selvforbedring»: godkjente adaptive vekter kan påvirke rangering, teknisk bidrag kan påvirke Autonomi-inngang, mens flere forsknings-, verdi-, forecast- og risikomoduler bare analyserer eller foreslår. Ingen av disse har gjennom denne revisjonen fått dokumentert positiv økonomisk effekt.

## Produksjonsbevis og økonomiske begrensninger

De to originale diagnose-ZIP-ene er lest på nytt. De er ikke publisert i repositoryet. `produksjonsbevis.json` har kildehashene og et begrenset, aggregert bevisutdrag uten tilgangsnøkler eller jobbtokens.

SP-diagnosen inneholder 20 snapshots fra 12. oktober 00:55:07 UTC til 21. oktober 13:25:28 UTC. Bevarte endringsrader: 16 BUY, 3 SELL og 2 ADD. Alle 16 kjøp er merket RISK_EXIT_REFILL. Det beviser gjenfyllingsaktivitet i utdraget, ikke at alle kjøp var økonomisk skadelige.

Bevarte salg er HALO, TREL-B.ST og DNO. DNO har inngang 20. oktober 13:10:38 UTC og salg 21. oktober 01:10:24 UTC, omtrent 12 timer senere. Registrerte kurser er 22,4200000763 og 22,2999992371. Dette er dokumentasjon av modellens logg, ikke en ekstern meglerutførelse eller bevis på en fersk nattkurs. BWE-/OMC-salg har fortsatt mangelfulle salgsrader og er ikke gjenopprettet med antatte priser.

Rapportert NAV i utdraget går fra 984 151,47 til 973 526,92, omtrent −1,08 %. Dette er et bevart modellresultat med kjente historiske regnskapshull, ikke en fullstendig kontrollert nettoavkastning. Materialet dekker ikke fire komplette uker eller alle fire porteføljene.

For en forsvarlig lønnsomhetsanalyse mangler fortsatt fullstendige transaksjoner, åpningsbalanser, aksjeantall/enhetsgrunnlag, inn-/utbetalinger, tidspunkt for signal/beslutning/kurser/utførelse, kostnader og faktisk FX. Sammenligning med 5/10/20 børsdagers hold, tidligere svekkelsessalg og videre kurs etter salg krever punkt-i-tid-kurser, selskapsbegivenheter, handelskalendarer og samme kapital-/kostnadsgrunnlag. Ingen nye avkastningstall er konstruert for disse alternativene.

## Endrede filer og testvedlikehold

Produksjonskode: `super_portfolio.py`, `autonomous_portfolio.py`, `services/simulated_execution_service.py`, `services/economic_accounting_audit.py`, `investment_pipeline.py`, `learning_experiments.py`, `portfolio_history_optimizer.py`, `strategy_history_worker.py`, `research_findings_dashboard.py`, `report_portfolio_intelligence.py`, `market_intelligence.py`, `autonomy_modes.py`, `navigation_state.py`, `pages/autonomy.py`, `pages/paper_trading.py`, `pages/super_portfolio.py`. Formålet for hver fil fremgår av funntabellen og brukerflytfunnene.

Ny sikker testfixture: `scripts/system_revision_ui_fixture.py`. Nye regresjoner: `tests/test_system_revision_20261022.py` og `tests/test_system_revision_browser.py`. `tests/test_superfund_browser.py` støtter tilgjengelig system-Chromium og leser faktiske nedlastinger. Release-workflowen kjører de nye regresjonene og hele-app-nettleserflytene.

Eksisterende tester er oppdatert der gamle testinput manglet det nye eksplisitte kursbeviset, der benchmarkstubben måtte støtte persist-argumentet, der metodeversjon nå kreves, eller der stoppscenarioets inngangsdag ellers allerede traff stoppen. Kursbevisene er syntetiske og eksplisitte i testene, ikke en generell friskstempling av historikk. Endrede tester omfatter `test_autonomy_exit_quote_guard`, `test_autonomy_pending_restart_20261012`, `test_learning_runtime`, `test_program_audit_autonomy_accounting`, `test_rc16_32d_super_portfolio_completion`, `test_rc16_32e_super_portfolio_multimarket`, `test_rc16_32i_super_portfolio_decision_safety`, `test_research_findings_dashboard`, `test_research_method_audit`, `test_revision_trade_settlement`, `test_strategy_history_worker` og rotfilen `test_v1871_insider_intelligence.py`.

## Produksjonsovergang og gjenstående status

Rettelsene krever ingen ny SQL-tabell eller automatisk historisk handelsrekonstruksjon. Nye felter ligger i eksisterende JSON-/journalstrukturer. Forskningsmetodens nye versjon gjør eldre optimaliseringsresultater uaktuelle og medfører ny bakgrunnsberegning. Det er ikke gjennomført en prøveovergang på en full kopi av produksjonsdatabasen; tilgjengelig åpningsfixture representerer bare utvalgte dokumenterte SP-felter.

F3 krever fortsatt et dokumentert overgangsgrunnlag for faktisk basisvaluta, aksjeantall, kostnader og historikk. Eldre BWE-/OMC-salg kan ikke repareres uten originale bevis. Autonomis observasjonsbaserte stoppovervåking og ikke-atomiske eldre lagringskjede må tas med i risikovurderingen. Hele testpakken har fortsatt feil fra utgangspunktet, selv om målrettede og aktive pakker består.

**Vurdering:** de avgrensede rettingene har konkrete regresjons- og nettleserbevis og kan gjennomgås i en draft-PR. Hele systemet er ikke godkjent for merge/deploy eller fullverdig lønnsomhetskonklusjon på dette grunnlaget. Arbeid med datakvalitet og økonomisk grunnlag kan fortsette, men manglende regnskaps- og produksjonsbevis må ikke tolkes som dokumentert lønnsomhet. Ingen merge eller deploy er utført.
