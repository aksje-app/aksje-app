# Siste regresjonskontroll før merge – PR #167

23. oktober 2026. Gren `fix/systemrevisjon-20261022`.
Kontrollert utgangspunkt: `88e414a6688ab2396599330e18223d2939ed9c16`.
Hentet main: `f0ef5b491219c2a1232bff30cc9b37eed58bc479`.
Hentet PR #166: `8c1fd952732c5ff560797f8fb8597a02d9b1d7d7`.

## Funn og avgrenset retting

Autonomis ordinære løp hoppet over eide tickere som ikke fantes i kandidatlisten.
Det skjedde før forsøk på å skaffe dokumentert utførelseskurs. Dermed kunne
kandidat-/oppdagelsesfiltre hindre risikosalg selv når en fersk kurs var tilgjengelig.
Dette er rettet i `run_autonomous_cycle` og `_execution_candidate`.

Alle eide tickere vurderes nå uavhengig av kjøpslisten. En gyldig, allerede mottatt
`execution_quote` kan brukes fra kandidaten eller den eide posisjonen. Dette er et
faktisk datert kursbevis, ikke posisjonens numeriske `last_price`/`average_price`.
Beviset må være ferskt, ikke ligge i fremtiden og ikke være eldre enn siste
posisjonsobservasjon. Uten gyldig bevis forsøker det ordinære løpet kursleverandøren.
Et leverandørunntak stopper ikke resten av porteføljekontrollen.

Ved totalt bortfall av gyldig kursbevis utføres ingen handel. Beslutningen merkes
`risk_execution_blocked` med begrunnelse. Ingen antatt kurs, skannetidspunkt eller
gammel numerisk mark brukes som erstatning. Det er derfor ikke mulig å love
utført stop-loss under et slikt databortfall; dette er et nødvendig beviskrav.

Ingen kjøps-, salgs-, stop-loss-, gevinstsikrings- eller rebalanseringsterskler
endres i denne siste kontrollen. Produksjonskontoer og læringslagre er ikke rørt.

## Ordinære motorer, restart_context=None

Seks felles funksjonelle prober ble kjørt uendret mot både main og arbeidsgrenen.
Importroten ble kontrollert, slik at main-prøven faktisk brukte main-koden.
Dette dekker Paper-kjøp, delsalg, automatisk take-profit og lokal lagring;
Autonomi-stop-loss, delvis gevinstsikring og gevinstvern med lagring/journal/
ytelsesrapport; Superporteføljens vanlige måloppgjør, lagring og PDF; og schedulerens
forfalte tidsslot i Europe/Oslo. Alle seks har samme forventede økonomiske resultat.

Ytterligere 13 målrettede tester kontrollerer den korrigerte risikoveien:
uten kandidat, med avvist kjøpskandidat, med leverandørsvikt og gyldig mottatt
kursbevis, og med manglende/foreldet/fremtidig/ufullstendig kursbevis.
Stop-loss, delvis gevinstsikring og gevinstvern prøves uten kjøpsautorisasjon.
Lagring og rapporter kontrolleres i isolerte faktiske lokale lagre.
Eksterne tjenester/varslinger substitueres; strategibeslutningene er de ordinære.

## Oppstart og aktiveringssperrer

Tre nye kontroller omfatter AST-/Render-oppsett og egne subprocesser med
`APP_ENVIRONMENT=production` og development. Import av scheduler-/worker-
oppstartsmodulene endrer ikke klargjorte testutkast. Aktiveringsforsøk avvises,
selv med den eldre `ECONOMIC_PRODUCTION_ACTIVATION_ENABLED=true`.
Alle tre utkast og journaler er uendret etter kontrollen.

Ingen oppstartsmodul eller Render-konfigurasjon velger restartperiode, setter
`restart_context` eller importerer en restartaktiveringsvei. UI-panelene leser
bare eksplisitt angitt periode. Merge og deploy åpner dermed ikke en restartkonto.
Det er ikke kjørt en faktisk Render-deploy; vurderingen gjelder kode og oppsett.

## Superfond og PR #166

PR #166 endrer bare grafnøkkelen i `superfund_presentation.py`, slik at
`chart_scope` inngår. Filen overlapper ikke #167. Endringen ble lagt på en separat,
detached testkopi av #167 med denne kontrollens Autonomi-retting; ingen gren ble
merget og ingen PR #166-kode ble lagt i #167.

Samme fond ble rendret i to grafkontekster i en faktisk Streamlit AppTest uten
widgetkollisjon. Hele Superfond-suiten på den kombinerte kopien ble til slutt
kjørt med nettleser og PostgreSQL aktivert: **154 tester besto**, ingen feil eller
skips, på **100,53 sekunder**. Dette inkluderer den ekstra grafkollisjonsprøven.
En innledende kjøring hadde fire PostgreSQL-skips; de er dekket av sluttkjøringen.

En egen differensiell prøve sammenlignet Superfonds økonomiske tilstand med main:
NOK, USD og EUR, med fire sykluser per valuta – opprettelse, kjøp, delsalg og
fullstendig salg. Kontanter, antall, kostpris, markedsverdi, realisert resultat og
NAV-historikk var identiske i alle tolv kontrollpunkter.

Superfond-koden er likevel **ikke uendret fra main** i #167: native journal får
flere bevisfelter, eldre handler/NAV trunkeres ikke, og rapporter viser revisjons-
status. Disse tidligere endringene er dokumentert; økonomiske/strategiske
regresjoner er ikke påvist i de prøvde forløpene. Ingen restartkonto opprettes for fond.

## Endringer utenfor restart

[Funksjonsoversikten](funksjonsendringer.md) dokumenterer alle 33 endrede eksisterende
Python-filer i runtime/verktøy mot main. Tilhørende JSON lister symbolene fra AST.
PR #167 er altså ikke bare en isolert tilføyelse av sperret restartkode.

Tidligere rettinger omfatter blant annet kursbevis, delsalgs-/gjenforsøksspeiling,
benchmark-startdato, merking av uverifisert avkastning, native fondsrevisjon,
forskningssimuleringens kjøpsdagsstopp/kapitaloverlapp, læringssnapshotets
lagringsstatus, rapportreparasjon og navigasjon/deling. De beholdes; de gjøres ikke
usynlige ved å hevde at alt ordinært er byte-identisk med main.

## Isolasjon av nettlesertester

Parallell kontroll av arbeidsgrenen og #166-kopien avdekket at Superfonds
nettleserfixture brukte fast port 8599. Første fulle kjøring fikk åtte
nettleserfeil (forbindelsen forsvant da den andre testkopien stoppet serveren).
Det var 2 499 beståtte tester og fire beståtte deltester i denne kjøringen.
Fixturen velger nå egen ledig localhost-port. Dette er eneste øvrige retting i
denne kontrollen, og påvirker ikke applikasjonskode. Alle ni Superfond-
nettlesertester besto deretter separat; hele pakken er deretter kjørt ferdig
og bestått to ganger, også etter at økten ble gjenopptatt.

## Sluttkontroller og konklusjon

De lokale rettingene, testene og rapporten var bevart. Ingen revisjon ble startet
på nytt eller rekonstruert. Den tidligere sluttkjøringen var også ferdig og bestått
(2 507 tester + fire deltester på 433,11 sekunder).

Etter gjenopptakelse ble hele pakken kjørt på nytt etter siste kildekode-/testendring:
**2 507 tester og fire deltester besto på 417.19 sekunder**, uten feil, errors
eller skips. Dette inkluderer **91 nettleserforløp**, **24 PostgreSQL-integrasjonstester**
og alle de **opprinnelige 99 regresjonstilfellene**. Alle 24 releasekontrakter,
fem Node-forløp, 70 låste avhengigheter og runtimekontroll besto igjen.
Sluttall står i `testresultater.json` og `sluttkjoring.txt`.
Live Yahoo for MYCR.ST/MSFT er forsøkt separat og feiler fortsatt med
CONNECT-proxy HTTP 403: **IKKE VERIFISERT**. Kontroller med substituerte leverandører
beviser feilbehandlingen, ikke faktisk produksjonsnettverk eller leverandørtilgjengelighet.

Konklusjon etter bestått sluttkjøring: **klar for merge som sperret
funksjonalitet**, etter vanlig CI/review. Ingen påvist gjenstående regresjon i
ordinær handel eller konflikt med #166. Dette er ikke godkjenning for produksjons-
aktivering; tidligere dokumenterte krav til arkiv, data, kontogodkjenning og
schedulerens separate produksjonskobling gjelder fortsatt.

Ingen merge, deploy, produksjonsarkivering, nullstilling eller produksjonsaktivering
er utført. Alle arkiv-/kontodata i prøvene er isolerte og syntetiske.

Oppdatering av PR-beskrivelsen med `gh pr edit` ble avvist av GitHub-API-et
(`Forbidden`). Den ferdige teksten ligger i `PR.md`. Kode og rapport leveres
via push til eksisterende PR-gren; API-avvisningen gjelder beskrivelsesfeltet.
