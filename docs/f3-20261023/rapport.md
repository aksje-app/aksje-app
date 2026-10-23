# F3 – separat NOK-regnskap og sikker overgang

23. oktober 2026 · `aksje-app/aksje-app` · arbeidsgren
`fix/systemrevisjon-20261022` · eksisterende PR #167.

Regnskapsbanen for nye dokumenterte NOK-perioder er implementert og koblet til
eksplisitte utførelsesadaptere, skjermvisning og eksport. Dette betyr ikke at de
eksisterende produksjonsporteføljene er migrert eller at deres tidligere
avkastning er verifisert. Produksjonsovergangen er sperret og ikke gjennomført.
De ordinære strategimotorenes historiske utførelsesbaner er fortsatt i bruk.

## Fullført

- Separate kontodokumenter for Paper Trading, Autonomi og Superporteføljen,
  med samme eksisterende basisvalutamotor og ingen skriving til gamle regnskaper.
- Dokumentert startdato, NOK-kontanter, faktiske aksjer, historisk NOK-kostpris,
  åpningskurser og FX-kilder. Ingen standardverdier for ukjente beholdninger,
  kostnader eller historiske transaksjoner.
- Kjøp, tilleggskjøp, salg og delsalg med proporsjonal kostpris, NOK-valuta ved
  handel, fordelt kurtasje/valutakostnad/øvrige kostnader, realisert og
  urealisert resultat, kontanter og NAV.
- Separat visning av medbrakt urealisert resultat og nettoresultat siden ny
  periodestart. Historiske tap forsvinner ikke når en periode starter.
- Uforanderlig åpningsutkast, eksplisitt godkjenning med dokumentfingeravtrykk,
  miljøavgrensning og standard sperre mot produksjonsaktivering.
- Full hendelsesjournal for åpning, godkjenning, handler og markeringer.
  Kontanter, beholdning og journal lagres atomisk. Integriteten kontrolleres
  gjennom hashkjede og replay med samme regnskapsmotor.
- Idempotente gjenforsøk, avvisning av motstridende ID-er, avstemming etter
  gjenoppretting og fjerning av verifisert NAV ved feil eller foreldede bevis.
- Lesepaneler og JSON-/CSV-eksport på de tre aksjesidene. Paper- og
  Superportefølje-diagnose har separat NOK-regnskapsfil. Gamle modellestimater
  merkes tydelig og erstatter ikke verifisert nettoresultat.
- Kontroll av Superfonds eksisterende NOK-modell, uten en ny operativ fondskonto.
  Nye native poster dokumenterer antall, kostnader, kurs og faktisk brukt
  valutafixing. Eldre poster gjøres ikke om til dokumenterte handler i ettertid.
  Avstemmingsstatus følger skjerm, PDF, CSV, Excel og diagnoseeksport.
- Superfonds tidligere avkutting av handels- og verdihistorikk er fjernet.
  Eksisterende dokumentbudsjett gjelder fortsatt; det slettes ikke historikk
  dersom publisering blir for stor.
- Vern mot at gammel kontosynkronisering overskriver et eksplisitt nytt
  basisvalutaregnskap.

## Hvordan de fire porteføljene behandles

| Portefølje | Dokumentert regnskapsbane | Eksisterende data og produksjonsstatus |
|---|---|---|
| Paper Trading | Egen NOK-periode med faktiske aksjer og eksplisitte kostnader via `paper_store.record_documented_nok_fill` | Gamle lokale modellresultater og handler beholdes. Ingen ny produksjonskonto aktivert. |
| Autonomi | Egen NOK-periode via `autonomous_portfolio.record_documented_nok_fill` | Tidligere resultater, også tap, beholdes som uverifisert modellhistorikk. Ingen automatisk overgang. |
| Superporteføljen | Egen NOK-periode via `services.super_portfolio_store.record_documented_nok_fill` | Gamle vekter/modellandeler og prisforholds-NAV konverteres ikke til antatte aksjer. Egen historikk og diagnose beholdes. |
| Superfond | Eksisterende native NOK-regnskap, med direkte avstemming og bedre bilag | Ingen konkurrerende konto. Simulerte gebyr-bps, valutapåslag og halv ETF-spread beholdes. Løpende fondskostnader inngår i NAV og trekkes ikke på nytt. Eldre ufullstendig grunnlag merkes uverifisert. |

NOK-resultatet beregnes som kontanter pluss omregnet markedsverdi minus
åpnings-NAV. Kjøpskostnader inngår i kostpris; salgskostnader reduserer proveny.
Kostnader trekkes ikke fra dobbelt. Valutaendring påvirker NAV også når lokal
aksjekurs er uendret. Nettoavkastningen gjelder den dokumenterte perioden,
ikke hele den ufullstendige historikken.

## Faktisk testing

Sluttkjøringen bestod med **2 406 tester og fire deltester** på 362,97 sekunder,
uten feil eller hopp i den isolerte pakken. Dette omfatter **103 regnskapstester,
19 PostgreSQL-tester og 77 nettleserforløp**. Alle 99 tidligere feiltilfeller
består. De to separat kjørte live-testene feiler fortsatt med nettverksproxy 403.

Sluttall og kjøringstid står i [testresultater.json](testresultater.json) og
[sluttkjoring.txt](sluttkjoring.txt). [Kjøreveiledningen](KJORING.md) forklarer
isolasjonen, aktiverte testkrav og begrensningene.

Hele den isolerte testpakken er kjørt med aktive nettleser- og PostgreSQL-tester.
De to eksterne Yahoo Finance-akseptansetestene er kjørt separat og feiler fordi
CONNECT-proxyen returnerer HTTP 403. De regnes ikke som bestått.

Regnskapstestene dekker NOK, USD og EUR, kjøp, tilleggskjøp, delsalg, sluttoppgjør,
valutabevegelse, gebyrfordeling, NAV, historisk kostpris, medbrakte tap og ny
perioderesultat, separate kontosaldoer, dublettvern, samtidige utførelser,
ugyldige/manglende/foreldede/fremtidige data, manipulert journal, skrivefeil,
tapt commit-kvittering og omstart. PostgreSQL tester både transaksjonsrollback
og samtidige gjenforsøk mot reell lokal PostgreSQL 16 med isolerte skjemaer.

Nettleseren tester ordinære ruter og faner, innstillingslagring, mobilmenyer og
reelle PDF-/CSV-/Excel-/ZIP-nedlastinger. Nye forløp tester alle fire
regnskapsvisninger og nedlastinger på PC-/mobilbredde. Regnskapsutkast i UI er
syntetiske, inaktive og ligger bare i midlertidige testmapper. Det brede
kontrollinventaret dokumenterer ikke funksjonstest av hver mulig ordreknapp,
ekstern innlogging eller reell varslingslevering.

De opprinnelige 99 feilene er kontrollert mot sluttkjøringens JUnit-resultat;
ingen av de tilhørende testmetodene mangler eller feiler. Kontroller av låste
avhengigheter, runtime-importer/kompilering, alle 24 releasekontrakter og fem
rapportdelingsforløp er også kjørt.

## Bevaring av historikk

Det er ikke skrevet mot produksjonslagring. Ingen tidligere portefølje er
slettet, nullstilt, overskrevet eller økonomisk rekonstruert. De nye
aksjeregnskapene bruker separate nøkler. Eksisterende tall merkes som historiske
modellresultater, uten at tap skjules eller historiske aksjeantall gjettes.
Superfonds native fremtidige journal mister ikke eldre handler ved avkutting.

## Hva som mangler før produksjonsovergang

Se den fullstendige [overgangsplanen](OVERGANG.md). Det mangler et bekreftet
produksjonsgrunnlag per aksjeportefølje: datert NOK-kontantbeholdning, faktiske
aksjer, instrumentvaluta, gjenværende historisk NOK-kostpris med kostnader,
åpningskurser/FX og bilag for eventuelle historiske hull. Originalbevis må
kontrolleres; det er ikke tilstrekkelig å oppgi en kildehenvisning i JSON.

Den ordinære utførelseskilden må levere hele den dokumenterte fill-kontrakten
og kontrolleres i en isolert prøve før den kobles til som eneste skriver for
en ny konto. Tidligere modellvekter kan ikke føres direkte som aksjer. Det
utføres ingen automatisk utførelsesomkobling i denne endringen.

Utbytte, splitt og eksterne kapitalstrømmer er ikke nye støttede journaltyper.
Slike hendelser må avklares før overgang og skal ikke bokføres som skjulte
handelsgevinster. Live-leverandørtestene må dessuten bestå i et miljø med
fungerende tilgang. Uttrykkelig produksjonsgodkjenning må gis for det konkrete
åpningsdokumentet og den operative overgangen.

Løsningen er klar for kodegjennomgang og isolert overgangsprøve.
**Den er ikke klar for produksjonsaktivering med det tilgjengelige datagrunnlaget.**
Ingen merge, deploy, kontoaktivering eller overføring er utført.

## Oppdatering av PR

Endringene leveres på eksisterende arbeidsgren for PR #167; ingen ny PR opprettes.
GitHub GraphQL-API returnerer Forbidden ved oppdatering av PR-beskrivelsen.
Revidert PR-tekst er derfor lagret i [PR.md](PR.md). Kodeoppdateringen skjer
gjennom push til samme PR-gren.
