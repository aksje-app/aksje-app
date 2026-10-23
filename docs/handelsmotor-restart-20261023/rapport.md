# Restart og ordinære handelsmotorer – PR #167

23. oktober 2026. Arbeidsgren `fix/systemrevisjon-20261022`.
Utgangspunkt `7dd7afa73e75d466dbbb44f0ce0d8875c4d509c7`.

## Leveranse og avgrensning

Eksisterende NOK-motor og restartløsning er videreført. Alle tre ordinære
strategimotorer kan kjøres mot en eksplisitt, separat restartkonto i isolert
simulering. Koden velger ikke produksjonskonto, endrer ikke eksisterende
produksjonsdata og har ingen automatisk overgang. Produksjonsaktivering er
fortsatt sperret; verken `APP_ENVIRONMENT=production` eller development tillater
restart-handler. Testsperren skal aldri omgås ved å kalle produksjonen et testmiljø.

## Kodeendringer

- `services/restart_trading.py`: eksplisitt kontokontekst, ferske kurs-/FX-/kostnads-
  bevis, aksjeantall og NOK-budsjettering; én atomisk transaksjon for hele jobben.
  Handler, verdsetting, beslutninger, innstillinger, kandidater, bevis,
  strategitilstand og idempotent jobbkvittering ligger i samme autoritative journal.
- Ordinær `trading_engine.auto_trade` og kjøps-/salgsregler brukes av Paper-adapteren.
  Portfolio/rules/audit-lesing i den valgte konteksten er avgrenset fra gammelt lager.
  Samme-ticker-karantene leser siste kjøp først, slik det gamle Paper-formatet gjør.
- `run_autonomous_cycle(..., restart_context=...)` bruker eksisterende kjøps-,
  risiko-, gevinstsikrings- og salgsporter. Ventende neste-sesjonssignaler beholdes
  mellom jobber. Posisjons-/sektorgrenser, kontanter og sizing regnes i NOK;
  lokal aksjekurs brukes fortsatt til strategiens kursnivåer. Et delsalg kan ikke
  umiddelbart følges av tilleggskjøp i samme jobb.
- `super_portfolio.evaluate(..., restart_context=...)` bruker eksisterende søk,
  rangering, neste-sesjonsporter, målvekter, stop-loss og rebalansering. Oppgjøret
  bruker den nye aksje-/valutajournalen i stedet for gamle modellratio-enheter.
  Utførelseskursen merkes som dokumentert restart-utførelse; sesjonsåpningen er
  kvalifikasjonsgrunnlag, ikke en antatt utførelseskurs.
- Kjøp og tilleggskjøp inkluderer dokumenterte NOK-kostnader i budsjettet.
  Delsalg fordeler historisk NOK-kostpris gjennom eksisterende motor.
- `portfolio_accounting.verify` kontrollerer nye hashbundne `STRATEGY_RUN`-hendelser.
  En jobb bindes til eksakt periode, familie, åpning, godkjenning og miljøscope.
- `simulation_restart`: starttid må være strengt etter arkiv og verifisert
  arkivgjennomgang. Kontolagerets mutasjoner returnerer riktig kontodokument,
  samtidig som alle tre kontoer beholdes i den atomiske periodetransaksjonen.
- `restart_reporting.py` og lesepanelet viser startkapital/-tid, kontanter,
  beholdning, markedsverdi, NAV, realisert/urealisert resultat, kostnader og
  nettoavkastning. Ny NAV-graf og PDF/CSV/Excel/diagnose-ZIP gjelder bare valgt
  NOK-periode. Tidligere økonomisk historikk og læring merkes separat.

## Simulering, økonomiske hendelser og bevaring

Testforløpene arkiverer syntetisk gammel historikk med tap, rapporter og binære
modeller, verifiserer arkivet og oppretter tre tomme kontoer. Ny simuleringskapital
er Paper NOK 100 000, Autonomi NOK 500 000 og Superporteføljen NOK 1 000 000.
Kapitalen godkjennes bare i isolerte testkontoer. Dette er ikke meglersaldoer.

Ordinære strategier går fra kandidatgrunnlag til rangering/ventende signal,
kjøpsbeslutning, dokumentert utførelse og automatisk NOK-bokføring. Testene dekker
også tilleggskjøp, delsalg, full exit, stop-loss, gevinstsikring og SP-rebalansering
med økte og reduserte vekter. Markedsinput er eksplisitte syntetiske snapshots;
nytt aksjesøk mot en virkelig leverandør er ikke bekreftet.

Utbytte, innskudd, uttak og aksjesplitt bruker eksisterende `record_event` og samme
journal. Innskudd/uttak telles ikke som gevinst. Splitt bevarer NOK-kostpris og
justerer lagrede kursbaserte strategiankre slik at splitt ikke gir en falsk stop.
Ingen strategiterskler endres. Andre selskapsbegivenheter uten støttet, dokumentert
hendelsestype avvises fortsatt; de kan ikke konstrueres som tilfeldige handler.

Læring, parametere, gamle kontanter, gamle posisjoner og tidligere tap endres ikke.
Ingen fiktive salg opprettes. Ny kontekst skriver ikke gamle kontosynkroniseringer
eller læringslagre. Autonomis eksisterende rene simuleringsløp har ingen eksterne
lærings-/varslingsskriver; denne oppgaven nullstiller eller omkonfigurerer ikke
det separate operative læringsløpet. Superfond har ingen restartkonto.

Et konkret syntetisk Paper-forløp starter på NOK 100 000, kjøper 10 og deretter
5 USD-aksjer à USD 100 ved NOK/USD 10, og betaler NOK 10 per handel. Det selger
3 aksjer à USD 110 ved NOK/USD 11, mottar netto innskudd NOK 5 000 og netto
utbytte NOK 122, gjennomfører 2:1-splitt og selger resten til USD 55 ved NOK/USD 11.
Sluttkontanter/NAV blir NOK 108 232. Etter fratrekk for ny kapital er nettoresultatet
NOK 3 232, fordelt på realisert aksjeresultat NOK 3 110 og netto utbytte NOK 122.
Handelskostnadene er NOK 40 og er allerede trukket fra. Dette er testdata og
beskriver ikke produksjonsporteføljenes avkastning.

## Feilsikkerhet

Identiske jobber og tapte svar returnerer samme journalførte resultat uten ekstra
kjøp. En konfliktende jobb-ID avvises. Avbrudd før commit og databasefeil etter
beregning ruller tilbake hele jobben. Samtidige leveranser testes på lokalt lager
og PostgreSQL. Ingen gammel regnskapsmotor overtar ved feil.

Manglende/foreldet kurs, manglende FX/kostnadsbevis, utkastkonto, feil periode,
feil familie/godkjenning/miljø og avvik mellom beholdning og journal avviser handel.

## Testresultater

Etter siste kodeendring besto **2 485 tester og fire deltester**, uten feil,
errors eller skips, på **412,45 sekunder**. Dette omfatter **91 nettleserforløp**,
**24 PostgreSQL-integrasjonstester** og alle de **opprinnelige 99 regresjonstilfellene**.
I forkant besto 33 restart-/handelstester, 135 økonomiske regresjoner og seks nye
nettleserforløp; disse overlapper sluttpakken og skal ikke summeres med den.
Alle 24 releasekontrakter, fem Node-forløp for rapportdeling, kontroll av 70 låste
avhengigheter og runtimekontroll (970 Python-filer) besto også.
Sluttall og avgrensninger finnes i `testresultater.json` og `sluttkjoring.txt`.
Leverandørtester føres separat: Yahoo for MYCR.ST og MSFT feilet igjen med
CONNECT-proxy HTTP 403. **IKKE VERIFISERT**; ingen alternativ godkjent kjørevert
med verifisert leverandørtilgang var tilgjengelig.

Nettlesertester kontrollerer de tre nye kontoenes tall, graf og faktisk innhold i
PDF/CSV/Excel/ZIP ved 1280 og 375 piksler. Innlogging og eksterne tjenester er
substituert i nettleserfixturen; produksjonsinnlogging er ikke testet her.

## Klarhet for merge og produksjon

Endringen leveres til kodegjennomgang som en sperret, testet simuleringskobling.
Sluttkjøringen besto. Jeg vurderer endringen som klar for ordinær PR-review og
merge som sperret simuleringskobling, forutsatt vanlig CI-/reviewgodkjenning.
Dette er ikke en produksjonsklar aktiveringsleveranse.

Følgende gjenstår operativt: faktisk kildeinventar og tilgang, varig privat arkiv,
nøkkelforvaltning, produksjonsarkivering og tilbakelesing, og eksplisitt godkjenning
av kontoer og miljø. Teknisk gjenstår en separat kontrollert produksjonskobling
for scheduler, godkjennings-/aktiveringsvei og tørrkjøring. Ingen ny produksjons-
periode er opprettet eller aktivert i denne oppgaven.

[Produksjonsprosedyren](PRODUKSJONSPROSEDYRE.md) beskriver pause, arkivering,
gjenopprettingskontroll, kontoutkast, eksakt godkjenning, kontrollert kobling,
tørrkjøring, aktivering etter separat godkjenning, overvåking og tilbakeføring.

Ingen merge, deploy, produksjonsarkivering, nullstilling eller produksjonsaktivering
er utført. Ingen råproduksjonsdata, databasekopier eller nøkler følger PR-en.
