# Teknisk produksjonsklargjøring – PR #167

Arbeidet viderefører commit `43c756095dcf9b72e3171c87ec798b10b173d837` på
`fix/systemrevisjon-20261022`. Ingen revisjon er startet på nytt. Den eksisterende
NOK-motoren, arkivet, ordinære strategier og rapportering gjenbrukes.

## Leveranse mot de ti punktene

1. **Produksjonsgodkjenning implementert.** Signerte operatørgrants binder konto,
   eksakt kapital, periode, åpningsfingeravtrykk, arkiv, fysisk gjenopprettingsprøve,
   installasjon/miljø, aktør, referanse, strategi og kostnadsforutsetninger.
   Et boolsk enable-flagg erstatter ikke signaturen. APP_ENVIRONMENT=production
   brukes i de isolerte produksjonsprøvene; testmiljø brukes ikke som omgåelse.
2. **Scheduler/motorer koblet.** Paper-scannerens AUTO og manuelle BUY/SELL,
   Autonomi-orchestratorens syklus og Superporteføljens scheduler/arbeider bruker
   eksplisitt valgt NOK-periode. Ingen rute finnes før godkjent operatørhandling.
   PAUSED, feil miljø, feil signatur eller korrupt rute gir ingen legacy-fallback.
   Samme bundle-transaksjon inneholder marks, handler, strategistatus og kvittering.
   Superporteføljens mellomliggende stoppovervåking bruker også NOK-journalen.
   Allerede kvitterte ordinære jobber kan gjenleveres uten nytt leverandørkall.
3. **Arkiv og fysisk gjenoppretting ferdigstilt.** Read-only discovery omfatter
   databasealiaser, runtime, separate lagre/auth, eldre kataloger og løse filer.
   Eksterne tjenester/volumer må erklæres og inkluderes. Alle DB-tabeller og
   deklarerte filer arkiveres kryptert; kildefingeravtrykk følger eksportert
   PostgreSQL-snapshot. Gjenoppretting skjer bare til nye filer og nye tomme
   nok_restore_*-databaser. Gjenopprettet DB må samsvare med snapshotfingeravtrykket.
   Faktiske Render-kilder er ikke tilgjengelige i denne økten og er ikke attestert.
4. **Operatørprosedyre implementert.** CLI inventory/account-config/archive/
   restore/prepare/request/sign/activate/status/stop/resume krever eksplisitte
   input og nye private outputfiler. Aktivering revaliderer originalt arkiv,
   gjenopprettede filer og at gamle modell-/lærings-/runtime-data ikke er endret
   etter arkivet. Bare den nye periodens egne utkast-/rutingrader kan avvike.
5. **Produksjonstørrkjøring implementert.** dry-run-live bruker ekte pris-/FX-
   adapter og eksisterende strategiinnstillinger på faktiske innspill. Den ekte
   motoren kjører i privat minne uten vedvarende godkjenning/handler/posisjonsendring.
   dry-run støtter allerede dokumenterte komplette jobbinnspill. Resultatet
   inneholder kursbevis, valuta, kostnader, beslutninger og prøveregnskap.
6. **Komplette handelsforløp verifisert isolert.** Produksjonsgodkjente testkontoer
   gjennomfører vanlige strategier, kjøp, Paper-tilleggskjøp/delsalg/fullt salg og
   Autonomi-/Superportefølje-risikosalg. Regnskapet avstemmer kontanter, aksjer,
   kostpris, kostnader, valuta, realisert resultat og netto-NAV. De eksisterende
   bredere testene dekker også urealisert resultat, utbytte, split og kapitalstrømmer.
   Dokumenterte økonomiske hendelser kan bokføres eksplisitt i samme produksjonsjournal.
7. **Historikk og læring bevart.** Ingen gamle kontoer nullstilles eller selges
   fiktivt. Nye kontoer åpner med null aksjer og 100 000/500 000/1 000 000 NOK.
   Kildetester bevarer gamle negative resultater, handler, modeller, observasjoner
   og parametere. Læringskonto og øvrige Autonomi-arbeidsflater beholdes separat. Eksisterende
   markedssnapshot, parallelle strategier og teknisk strategibidrag gjenbrukes
   før NOK-avgjørelsen. Etter bokføring oppdateres eksisterende læringsobservasjoner,
   læringskonto og eksperimentgrunnlag med egne gjenforsøkskvitteringer, uten
   hovedkonto-speiling til et konkurrerende regnskap. Stopp av finanskontoen
   stanser handler, mens den uavhengige læringen kan fortsette som før; global
   arkivering krever derfor fortsatt at alle skrivere stanses eksplisitt. Kanonisk parametergovernance
   videreføres; startsnapshotet fryser ikke senere godkjente læringsoppdateringer.
   Gamle posisjoner eller kontanter kan ikke bli autoritativ saldo i ny periode.
8. **Visning/eksport kontrollert.** Aktiv valgt konto viser NOK-rapport, avstemming,
   graf, beslutninger, historikkskille og CSV/XLSX/PDF/ZIP. Historiske modellresultater
   har egen skrivebeskyttet visning/nedlasting. PC/mobil og øvrig navigasjon dekkes
   av nettlesertestene. Superfond beholder native økonomi og endres ikke i denne fasen.
9. **Livssyklus og regresjon kontrollert.** Isolerte PostgreSQL-prøver dekker
   godkjenning, full handel, avbrudd, samtidige duplikater, gjenforsøk, stopp,
   gjenopptakelse, ny lagringsinstans og fysisk restore. Feil signatur/kapital/
   miljø/åpning/arkiv/bevis og endrede kilder blokkerer uten kontoendringer.
   Hele sluttpakken og kompatibiliteten med #166 rapporteres i testresultater.json.
10. **Tidligere blokkeringer avklart.** Test-only-produksjonssperren er erstattet
    av signert, eksplisitt operatørkontroll. Portisolasjonen og Autonomi-rettingen
    fra forrige økt er bevart. Live Yahoo-testene er fortsatt IKKE VERIFISERT:
    CONNECT-proxy HTTP 403 for MYCR.ST/MSFT. Ingen resultater fabrikeres.

## Testresultater

**2 563 tester og fire deltester besto på 521.76 sekunder**, uten feil,
errors eller skips, etter siste applikasjons- og testendring. Inkludert i pakken:
**97 nettleserforløp**, **77 PostgreSQL-baserte forløp** (seks er nettlesertester),
50 nye produksjonslivssyklus-/regresjonstilfeller og alle opprinnelige 99 feiltilfeller.

Tre ekstra operative prøver besto gjennom faktisk Paper AUTO-kjøp og risikosalg,
Autonomi-orchestratoren og Superporteføljens schedulerarbeider. De brukte lokal
PostgreSQL, eksplisitt godkjente testkontoer og APP_ENVIRONMENT=production.
Ingen testkonto peker på Render. Kombinasjonen med PR #166 besto **154 tester**
uten skips på 96.03 sekunder, med identiske siste applikasjonsfiler.
Superfonds tolv økonomiske kontrollpunkter i NOK/USD/EUR samsvarer med main.
Alle 24 releasekontrakter, fem Node-forløp, runtime- og avhengighetskontroll besto.
Tallene overlapper og skal ikke summeres. Detaljer i testresultater.json.

Live Yahoo-testene forsøkes separat: to feil på grunn av proxy HTTP 403.
Det er daglig OHLC, børsåpning og forrige sluttkurs som ikke kan bekreftes her.
Ny adapter for ferske 5-minutterskurser, valutapar og instrumentmetadata er testet
med kontrollerte kilder; faktisk live-leveranse er heller ikke bekreftet fra dette
miljøet. DRIFT.md beskriver både leverandørprøve og dry-run-live på produksjonens
faktiske nettverk. Kontrollen må gjennomføres med ferske data i relevant markedstid.

## Avgrensede endringer i eksisterende funksjoner

- Ordinære innganger får en rutingsjekk. Uten eksplisitt valgt konto beholdes
  eksisterende forløp; med valgt konto brukes eksisterende strategier i NOK-session.
- Paper/Autonomi/Superportefølje-loadere viser valgt ny bok. Legacy-balanse-/
  journalmutasjoner blokkeres for valgt konto; historikken kan fortsatt leses separat.
- Autonomi-orchestratoren kan utføre risikotilsyn selv med tom kandidatstrøm når
  en ny NOK-konto er valgt. Ingen kjøps-, salgs- eller rebalanseringsterskler endres.
- Autonomis eksisterende upstream-, læringsprobe- og læringssynkroniseringskode
  er flyttet til felles hjelpere. AST-kontrollen i strategibevaring.json bekrefter
  identiske upstream- og læringsprobegrener mot forrige commit. NOK-ruting kaller
  disse samme funksjonene; tidligere læring nullstilles ikke. Læringsfeil etter
  økonomisk commit kan gjenforsøkes uten ny finansiell handel.
- Superporteføljens eksisterende konfigurasjonsnormalisering er flyttet til en ren
  hjelpefunksjon så operatørens strategisnapshot kan leses uten legacy-migreringsskriving.
  Den samme normaliseringen brukes av den ordinære loaderen.
- Superporteføljens stoppovervåking bruker identiske stoppsignaler, men sessionens
  dokumenterte kurser og autoritative bokføring når ny konto er valgt.
- De ordinære Paper-/Autonomi-resultatoversiktene bruker også verifiserte,
  kapitalstrømjusterte NOK-tall og ny periodes beslutninger. Historisk drawdown
  gjenbrukes ikke, og innskudd telles ikke som gevinst.
- Nye NOK-kontoer har en egen økonomisk PC-/mobilvisning som ikke gjenbruker gamle
  beregninger i lokal valuta. Autonomis kontrollsenter og læringsnavigasjon beholdes.
- Release-workflowen kjører den nye produksjonslivssyklusen og nettleserprøvene
  mot disponibel CI-PostgreSQL, uten produksjonshemmeligheter.

En innledende bred kjøring ble avbrutt etter ett gammelt testkrav til
feilmeldingstekst (1 feil, 1 437 beståtte). Aktiveringen var korrekt blokkert;
feilmeldingen ble gjort kompatibel. Det ble også rettet at eksplisitt angitt
lagring skal brukes ved lesing av strategisnapshot, uten annen backend som reserve.
En tidligere komplett kjøring hadde også ett kildekodekontrakt-avvik:
2 554 besto, mens en test krevde nøyaktig gammelt innrykk på læringsbroens kall.
Denne testen verifiserer nå reelt AST-funksjonskall og konto-/porteføljeargumenter.
Ingen økonomisk atferd ble endret for å tilpasse testen. Den nye komplette
sluttkjøringen over erstatter alle del-/feilkjøringer.

De siste integritetsrettingene krever streng PostgreSQL-lagring også ved stopp,
økonomiske hendelser og produksjonsmutasjoner. En valgt NOK-installasjon kan ikke
falle tilbake til en lokal filjournal ved databasesvikt. Manglende kanonisk
strategikonfigurasjon bruker det signerte startsnapshotet fremfor en annen
prosess' runtime-fil. Eksisterende journal kan ikke forkortes eller erstattes,
og et eldre kursbevis kan ikke overskrive en nyere dokumentert posisjonskurs.

En mellomliggende nettleserkjøring fikk 94 feil etter et foreldet
nedlastingsmål og manglende opprydding. Kontospesifikke widgetvelgere og
finally-close rettet dette. En senere fullkjøring fikk 7 feil og 6 fixture-feil
fordi Autonomi-testen arvet andre testers runtime-parametere. Produksjonsvernet
avviste korrekt ulik konfigurasjon. Fixture setter nå dokumenterte kanoniske
PostgreSQL-parametere før arkivering; godkjenningskravene er beholdt.

## Gjenstående drift – ingen produksjonsoperasjon utført

Kode for produksjonsaktivering er implementert, men **ikke kjørt mot produksjon**.
Ingen merge, deploy, nullstilling, arkivering eller kontoaktivering i produksjon.
Ingen produksjonsdata, nøkler, DSN-er eller databasekopier publiseres i GitHub.

Det mangler tilgang til den faktiske Render-installasjonens database-/diskinventar,
arkiv og gjenopprettingsmål; derfor er disse ikke kontrollert eller godkjent her.
Gjenstående arbeid er operatøroperasjoner i [DRIFT.md](DRIFT.md): godkjent utrulling
av denne koden, kildeinventar og uendrede strategisnapshots, stans av alle skrivere,
komplett arkiv med uavhengig kopi, faktisk restore, tre utkast, live leverandørkontroll/
tørrkjøring, tre signerte godkjenninger og eksplisitt oppstart. Deretter kontrolleres
første jobbkvittering, NAV og rapporter. Yahoo-aksept må bestå fra produksjonsnettet
før handelsoppstart. Ingen automatisk ruting/aktivering skjer ved merge/deploy.

GitHub GraphQL avviste både PR-lesing og oppdatering av beskrivelsen med Forbidden.
PR-beskrivelsen er derfor lagt i PR.md. Kodeoppdateringen gjøres via vanlig Git-push
til eksisterende gren; gren og refs/pull/167/head kontrolleres direkte mot GitHub.
Dette er en API-tilgangsbegrensning, ikke en automatisk godkjenningsavvisning.

Den nye leverandør-CLI-en er også kjørt uten ordre her: alle fire forespurte
5-minuttersserier (MYCR.ST, MSFT, SEKNOK=X og USDNOK=X) feilet med proxy 403.
CLI-en returnerte exitkode 2 og IKKE VERIFISERT for hver. Live instrumentvaluta-
metadata ble ikke nådd etter kursfeilen. Produksjonens faktiske markedskurser,
valutakurser og metadata må derfor kontrolleres i planlagt driftsvindu.
