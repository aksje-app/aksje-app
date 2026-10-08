# Trade Entry & Profit Protection — rc16.34g

## Problem og ny oppførsel

Paper kunne kjøpe etter én teknisk skanning og selge på en kurs fra analysegrunnlaget, mens nye kjøp brukte en separat intradagkurs. Det kunne blande justerte dagskurser med en annen utførelseskurs. PostgreSQL-innlesing rekonstruerte bare faste kolonner og skrev den reduserte porteføljen tilbake til dokumentlageret. Det fjernet blant annet decision_snapshot og øvrig revisjonsbevis. Dette er verifiserte kodefeil; at de forklarer hele NOHAL/OET-tapet er ikke bevist.

- Automatiske Paper-aksjekjøp og salg bruker kurs og tidspunkt fra samme **ujusterte 5-minutters bar**. Beviset må stemme med pris og markedsdatatidspunkt, være maksimalt 15 minutter gammelt og ikke gå bakover fra siste registrerte posisjonskurs. Manglende/gammelt/justert/ikke-endelig bevis stopper mutasjon. Manuelle handler beholder eksplisitt manuell pris; fonds-NAV følger eget løp.
- Nye automatiske aksjekjøp krever to kvalifiserte tekniske skanninger med forskjellige run-ID-er og kursbarer, minst 10 minutter mellom barene og innen 120 minutter. Samme bar teller ikke to ganger. HOLD, manglende analyse, for lav score/confidence eller ugyldig kurs nullstiller bekreftelsen. Status er permanent og begrenset til 500 kandidater; databasefeil gir ikke lokal omgåelse. Bekreftelse er **ikke** fundamentalanalyse eller kalibrert sannsynlighet for gevinst.
- Bekreftelse og kandidatautorisering skjer før salg for utskifting. Mislykket salg stopper det nye kjøpet. Ordrevalidering håndhever plassgrensen for nye posisjoner, og utilgjengelig validator blokkerer kjøp.
- Eksisterende Paper-posisjoner kan fortsatt få en hard risikoexit på verifisert fersk kurs selv om aksjeanalysen feiler. Manglende analyse blir ikke score 0.
- Faktisk inn-/utgangsscore, kjøpssnapshot, bekreftelser, kursbevis og salgsdetaljer bevares i additive PostgreSQL-metadatafelt. Faste SQL-kolonner er autoritative for beholdning og kontanter. Innlesing skriver ikke dokumentkopien tilbake. Historiske manglende bevis rekonstrueres ikke som oppdiktede verdier.
- Varsler skiller ukjent score fra 0, viser minutter/timer i tillegg til børsdager og viser stopgrense, kursavvik og kurstidspunkt. Et gap registreres til observert pris; stopgrensen er ingen garanti for maksimal tapsprosent.

## Gevinstsikring

Felles trinnfunksjon for Paper, Super Portfolio og ordinær Autonomi-produksjon:

| Toppgevinst | Andel av toppgevinst som beskyttes |
|---|---:|
| under 2 % | Ingen aktiv gevinstsikring |
| 2–3 % | 40 % |
| 3–5 % | 55 % |
| 5–6 % | 65 % |
| fra 6 % | 70 % |

Effektiv trailing stop er maksimalt 3 %, også når Autonomi har eldre lagrede 7 %-parametre. Strammere innstilling gjelder. Autonomi bruker nå gevinstgulvet og kan også selge ved bekreftet tilbakefall innen 0,5 % over gulvet, når avstanden har falt mer enn 0,25 prosentpoeng fra forrige vurdering. Superporteføljens eksisterende øvrige tidlige stopregler beholdes. Læringskontoer og observasjoner har fortsatt egne eksplisitte regler. Gamle Super Portfolio-parameternavn med 8 i navnet beholdes for kompatibilitet; høyeste trinn gjelder nå fra 6 %.

VEI-eksemplet (inngang 202, topp omtrent 219) gir gulv 213,90. NOHAL (29,80 → 28,20) og OET (854 → 831, topp 861) hadde ikke nådd 2 % registrert toppgevinst; 8→6-endringen alene ville ikke hindret disse tapene.

## Lagringsfunn og begrensninger

Lesetilgang 8. oktober viste pg_database_size omtrent 2378 MiB, ca. 46,4 % av 5 GiB, mot Render-skjermbildets 56,48 % av disken. Siste opprydding kl. 08:11 UTC var COMPLETED / apply_enabled=true og målte 46,27 %. app_kv_store var omtrent 1972 MiB og app_jsonl_store 396 MiB. Ukomprimerte payloadsummer må ikke forveksles med fysisk komprimert tabellplass.

Historikk utgjør mest: repositories, autonomi_core og market_intelligence. Eldre samlefiler (market_snapshots, strategy_runs, strategy_decisions) finnes sammen med nye individuelle poster. Dette er også en kompatibilitetsmekanisme; de er ikke bevist fullt dupliserte og slettes ikke blindt.

Denne versjonen reduserer omskrivinger: porteføljeinnlesing gjør ingen dokument-write, og identisk write_json-payload gir ingen ny PostgreSQL-radversjon eller oppdatert updated_at. updated_at betyr siste innholdsendring. Kapasitetsrapporten oppgir at den måler selve databasen, ikke Render-diskens totale bruk. Dette begrenser unødvendig WAL/radversjoner; det garanterer ikke mindre disk umiddelbart og stopper ikke all ny historikkvekst.

**Årsaken til hele diskhoppet er fortsatt åpen.** SQL-brukeren fikk ikke tilgang til pg_ls_waldir. Ingen størrelse på WAL eller øvrige systemfiler er målt. Ingen produksjonsdata er slettet, ingen VACUUM FULL utført og ingen betalt lagringsoppgradering bestilt.

## Validering

Testene kjører uten produksjonsskriving og varsling. Den nye scenariofilen tester tre motorers trinngrenser, VEI-gevinstgulv, bekreftet tidlig exit, NOHAL-gap med faktisk utførelsespris, gammel/fremtidig/justert kurs, kursrekkefølge, tidsone, bekreftelser på tvers av skanninger, ugyldig/utløpt bekreftelse og utskifting før/etter vellykket salg.

Release gate inkluderer en isolert PostgreSQL 16-tjeneste med to reelle round-trip-tester: inngangs-/utgangsbevis over load/save og identisk dokument-write uten ny radversjon. Lokalt kjøres disse bare når TEST_POSTGRES_URL er satt; CI er den faktiske databasekontrollen.

Endringen er klargjort på separat gren. Merge og deploy inngår ikke i denne gjennomføringen.
