# Oppfølging av PR #167 – 23. oktober 2026

Arbeidsgren: `fix/systemrevisjon-20261022`. Startpunkt
`0803e414fb5421858b8bdc2386cebc750d5c569f` er kontrollert mot PR #167.
Arbeidet fortsetter den eksisterende PR-en. Ingen ny PR, merge eller deploy.

## Resultat og avgrensning

Alle de 99 tidligere rapporterte feilende testene består. Hele den isolerte
pakken, med nettleser- og databasetestene aktivert, består: **2325 bestått,
0 feilet, 0 hoppet over og 4 beståtte deltester**, på 335,03 sekunder. De to
separate live-OHLC-testene er eksplisitt utenfor denne kjøringen.

F3 er **fortsatt delvis fullført for eksisterende porteføljer**. En ny eksplisitt
basisvalutabane er implementert og testet gjennom felles simuleringsmotor,
men de eldre Paper-/Autonomi-banene og SP-modellen byttes ikke automatisk over.
Manglende historikk og åpningsbalanser kan ikke erstattes av antatte tall.
Valg av overgang er spurt om i samtalen. Se [F3.md](F3.md).

Det er heller ikke dokumentert at hver mulig knapp, innstilling, brukerrolle
og nedlasting i hele programmet er funksjonstestet. **69 nettlesertester består**,
men et observert kontrollelement er ikke et bestått brukerforløp. Full
handlingsdekning skal fortsatt stå som uverifisert.

## De 99 testfeilene

`opprinnelige-99.json` kobler hvert tidligere feilende testnavn til en bestått
test i den samlede sluttkjøringen. Ingen av de 99 er hoppet over, xfail-merket
eller fjernet fra innsamlingen. To testenavn er presisert fra tre til fire
valutadesimaler for å følge den eksisterende presisjonskontrakten.

Arbeidet omfatter både produktrettinger og testvedlikehold:

* Historiske versjonslåser er erstattet med kontroll av gjeldende kanoniske
  versjon, serialisering, build-label og gjeldende release-notater.
  Funksjonsassertsjoner i blandede tester er bevart.
* Innsider-fixturer bruker aktuelle datoer. Kjøp og salg testes innenfor de
  eksisterende tidsvinduene; selve vinduene er ikke utvidet.
* Exit-tester bruker prisbaner som faktisk treffer regelen som testes, i stedet
  for først å treffe en høyere prioritert gevinstsikring. Handelsreglene er ikke
  senket eller deaktivert.
* Rapporter, navigasjon, scannerminne, læringshorisonter, FX-presisjon,
  vedlikehold og universinnhenting kontrolleres mot gjeldende kontrakter.
* En eldre kvalitetstest kunne starte ekte fullmarkedsinnhenting. Den bruker
  nå isolert prescreen-fixture og tester fortsatt lagring og PDF-publisering.
* Rapportreparasjon er skilt ut som en begrenset funksjon. Feilen injiseres og
  kontrolleres uten å starte hele schedulerens eksterne vedlikeholdsarbeid.

En grønn pakke betyr dermed ikke at det er funnet og rettet 99 separate
produksjonsfeil. Flere var foreldede tester. De aktive beskyttelsene og de
konkrete regresjonene er beholdt.

## Produktrettinger

Sidepanelets to varianter skrev til felles `data/ui_state_v18658.json`.
De bruker nå brukerspesifikk runtime-lagring, i samsvar med appens hovedrute.
Den genererte gamle filen ble bevart utenfor checkouten, ikke slettet som
brukerdata.

Rapportdeling bruker Streamlits støttede HTML-/JavaScript-grensesnitt.
Komplett rapportpakke viser byggestatus under komprimeringen.
Kvalitets-PDF skiller eksplisitt markedsgrunnlag, dekning og valgt dybdeanalyse.
Distribusjonsfilteret velger gjeldende release-dokumenter og bevarer historiske
release-dokumenter i repositoryet. Manglende gjeldende akseptanse- og
driftsforutsetninger er dokumentert uten å erklære produksjon godkjent.

Den nye økonomiske banen bokfører basisvalutakontanter, FX, kostpris,
handelskostnader, realisert resultat og netto-NAV. Den avstemmer journalen og
avviser manglende/fremtidige/foreldede kursbevis, inkonsistente beløp og endret
input på samme ordre-ID. Kontanter, beholdning og autoritativ journal lagres
atomisk. Fill-/ordrevisninger kan repareres etter avbrudd uten dobbelt oppgjør.
Dette er ikke automatisk migrering av de eldre modellkontoene.

## Verifiserte brukerforløp

* 16 navigasjonsruter på både 375 og 1280 piksler er åpnet med fullført
  app-rendering. Blant dem er analyse, marked, Top Picks, Long Engine,
  valuta, system, Superporteføljen, Superfond, kvalitet og driftsruter.
* Alle ti Autonomi-arbeidsflater er åpnet på PC- og mobilbredde.
* Paper Trading-diagnose: generering, nedlasting, ZIP-/JSON-kontroll og retur.
* Rapportsenter: eksplisitt destinasjon og gjenoppretting etter reload.
* Superfond: menybytte, kandidat-/landvisninger, mobilretur og nedlasting av
  PDF, CSV, Excel og diagnose-ZIP. Filene åpnes og innholdet kontrolleres.
* Valutainnstillinger: grenseverdier med fire desimaler og varslingsvalg
  lagres og består reload på begge bredder.
* Systeminnstillinger: cron-intervall og avskrudd bakgrunnssøk lagres;
  full stopp vedvarer over reload og blokkerer auto-kjøpsknappen; oppheving
  av full stopp er også kjørt på begge bredder.
* Ekte lokal autentisering er i tillegg testet med AppTest: opprettelse av
  første administrator, utlogging og ny innlogging med passord. Det er ikke
  en verifikasjon av produksjonsinnlogging eller gjenoppretting av nettlesercookies.

`ui-dekning.json` viser rendering og observert kontrollantall per rute/bredde.
Antall DOM-kontroller inkluderer gjentakelser mellom sider og bredder og skal
ikke oppgis som antall unike funksjonstestede knapper.

## Regresjoner og øvrige kontroller

Den samlede kjøringen omfatter tidligere F1–F10-regresjoner, ferske utførelses-
kurser, stoppsalg, holdetid, benchmarklagring, delsalg, læring, rapportretur,
versjonsbinding og forskningsmetode. 49 målrettede tester dekker den nye
økonomiske banen sammen med de tidligere revisjonsregresjonene.

14 eksisterende PostgreSQL-integrasjoner og to nye økonomiske samtidighets-
tilfeller er kjørt mot en lokal PostgreSQL 16-instans. Databasetestene bruker
isolerte skjemaer. De erstatter ikke en produksjonsmigreringstest.

Alle 24 releasekontraktskripter og fem JavaScript-delingsforløp består.
Python-syntaks, 70 eksakte produksjonspins, PDF-rundtest og `git diff --check`
består. Pakker som overlapper skal ikke summeres som uavhengige testantall.

## Fortsatt uverifisert og nødvendig neste avklaring

F3 krever valg mellom bevaring av eldre modellkontoer som historikk med nye,
separate NOK-kontoer for videre simulering, eller videreføring med dokumenterte
åpningsbalanser og originalhistorikk. Nåværende produksjonskontoer er ikke
nullstilt eller omklassifisert.

Alle aktive knappers kombinasjoner og hele analyseløp med representative
produksjonsdata er ikke fullstendig testet. Live-OHLC, reell Pushover-levering,
Render-oppsett, fysisk mobiltelefon, operativsystemets utskrift/deling og
produksjonens autentisering er heller ikke verifisert her.

GitHub-API-oppslag returnerte 403 Forbidden. Git-tilgang er brukt for å kontrollere
PR-ref og oppdatere samme arbeidsgren; ingen ny GitHub-token er konstruert eller
etterspurt i chat. Oppdatert PR-beskrivelse må skilles fra oppdatert kodegren.
