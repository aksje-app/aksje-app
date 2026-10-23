# Produksjonsavstemming og sikker overgangsprøve – F3

23. oktober 2026, norsk tid. Arbeidsgren `fix/systemrevisjon-20261022`, eksisterende
PR #167. Utgangspunkt: `19ed8781b5057fd3467b270f5c1e5cd4fa650a57`.

**Ingen produksjonsavstemming eller overgang på en produksjonskopi kan bekreftes
med de tilgjengelige kildene. Alle fire kontoer stoppes ved kildekontrollen.**
Programvaretestene nedenfor er ikke erstatning for denne prøven.

## 1. Hva som er kontrollert mot produksjonsdata

Det finnes ingen original diagnose-ZIP, produksjonsdump, konfigurert
produksjonsdatabaseforbindelse eller tilgjengelig Render-tilkobling i dette
kjøremiljøet. Ingen produksjons-SQL er derfor kjørt. Det er ikke brukt lokale
pytest-/nettleserdata som produksjonsdata.

Tilgjengelige kilder er tidligere revisjonsnotater og et tidligere aggregert
bevisutdrag i repositoryet. Notatene beskriver to Superportefølje-diagnoser og
et eldre skrivebeskyttet Render-uttrekk. De originale kildene er ikke
tilgjengelige for ny kontroll. Notatene bekrefter hva som tidligere ble
rapportert, men er ikke fullstendige beholdnings-, kontant- og handelsjournaler
for fire kontoer. Tall fra dem er ikke importert eller brukt til nye åpninger.
Ingen nye produksjonsverdier eller råuttrekk publiseres i denne oppfølgingen.

Det er spurt etter plassering av arkivene eller en skrivebeskyttet tilgang.
Manglende tilgang er ikke bevis for at en opplysning mangler i selve produksjonen.

## 2. Hvilke porteføljer kan avstemmes fullstendig

| Konto | Ny kontroll mot original produksjonskilde | Full avstemming | Overgangsprøve |
|---|---|---|---|
| Paper Trading | Ikke tilgjengelig | IKKE VERIFISERT | STOPPET før åpning |
| Autonomi | Ikke tilgjengelig | IKKE VERIFISERT | STOPPET før åpning |
| Superporteføljen | Kun tidligere sekundærnotater | IKKE VERIFISERT | STOPPET før åpning |
| Superfond | Ikke tilgjengelig | IKKE VERIFISERT | STOPPET ved kildekontroll |

Ingen konto erklæres feilavstemt uten data, og ingen erklæres fullstendig
avstemt ut fra beståtte syntetiske tester. Uforklarte beholdningsendringer,
fullstendig bevaring av alle produksjonstap og korrekt faktisk historisk NAV
kan ikke kontrolleres på nytt uten originalkildene.

## 3. Hvilke data må leveres og kontrolleres

For hver konto trengs et datert, sammenhengende modelluttrekk med beholdninger,
kontanter, startgrunnlag, hele tilgjengelige handelsjournalen, historisk
kostpris, kurs-/valutabevis, kostnadsforutsetninger og registrerte økonomiske
hendelser. Manglende perioder må oppgis. Åpnings- og sluttbeholdning må kunne
avstemmes uavhengig mot journalen.

Dette er modellporteføljer: **meglerbekreftelser kreves ikke**. Det er tilstrekkelig
med dokumenterte modellutførelser, sporbare markedskurser og de økonomiske
forutsetningene modellen faktisk brukte. `ACTUAL_SHARES` i den eksisterende
motoren betyr økonomisk aksjeantall, i motsetning til vekter/prisforholdsandeler;
det betyr ikke at aksjene må være kjøpt hos en megler.

En oppgitt modell-NAV og porteføljevekter er ikke alene dokumentasjon på historisk
NOK-kostpris eller aksjeantall. Gebyrer kan være dokumenterte modell-bps eller
dokumentert null. Ukjente historiske gebyrer og FX settes ikke til null eller
beregnes med dagens forutsetninger.

## 4. Resultatet av overgangsprøven

Ingen dokumentert produksjonskopi var tilgjengelig. Det er derfor ikke opprettet
åpningsbalanser for disse fire produksjonskontoene, og ingen av dem er kjørt
gjennom en produksjonsbasert handelstest. Ingen syntetiske beløp erstatter data.

`services/production_reconciliation.py` stanser ved manglende kilde,
åpningsdokument, komplett journal eller datert avslutning. Der dokumentert
åpning og normaliserte historiske modellutførelser senere foreligger, kan
funksjonen spille dem gjennom samme motor i minnet og kontrollere kontanter,
antall, kostpris og dokumentert slutt-NAV. Den skriver ikke tilbake til kilden
og bruker ingen produksjonsaktivering. Superfond avstemmes med sitt native
regnskap; det opprettes ingen konkurrerende fondskonto.

`scripts/f3_readonly_inventory.py` kan senere hente de kjente kontodokumentene,
journalstrømmene og Paper-tabellene. PostgreSQL-uttrekket bruker en eksplisitt
REPEATABLE READ / READ ONLY-transaksjon, uten initialisering eller migrering.
Forbindelsen tas bare fra `F3_READONLY_DATABASE_URL`. Rådata må lagres utenfor
Git-checkout, med begrensede filrettigheter. Verktøyet avviser overskriving og
stanser ved rad-/bytebudsjett fremfor å presentere en avkortet journal som komplett.
ZIP-inventaret leser og hasher originalfiler uten å pakke ut vilkårlige stier.
Dette er et avgrenset uttrekksverktøy, ikke en full databasekopi eller en garanti
for at all rapporthistorikk er dekket.

## 5. Ordinær handelsmotor og autoritativ bokføring

Kodekontrollen gir følgende vurdering, som må skilles fra observerte
produksjonsfeil:

- Paper har aksjeantall, kurs og beløp, men dagens poster gir ikke automatisk
  hele den nye NOK-kontrakten. Daterte FX-kilder, eksplisitte kostnader og
  sammenheng mellom oppgjør og journal må kontrolleres i faktisk uttrekk.
- Autonomi har utførelses-ID, kurs, mengde og noe kursproveniens. Dagens ordinære
  modellbane er brutto for ubokførte gebyrer; portefølje og gammel journal
  lagres gjennom flere operasjoner. Den kan ikke uten videre speiles som et
  fullstendig NOK-regnskap.
- Superporteføljens eldre oppgjør bruker `MODEL_PRICE_RATIO_UNITS`, NAV og vekter.
  Disse er ikke økonomiske aksjeenheter. Dokumenterte aksjeutførelser må leveres
  særskilt; det gjøres ingen automatisk enhetskonvertering.
- Superfond har eget NOK-oppgjør og sine modellkostnader. Dette beholdes som
  operativ sannhet, med direkte avstemming og eksplisitte datamangler.

De tre nye aksjekontoene har hver ett autoritativt kontodokument. Eksplisitte
fill-adaptere, NAV-markeringer og nye regnskapshendelser skriver samme atomiske
journal gjennom `portfolio_accounting`. Gamle porteføljer er ikke ekstra
skrivere til den nye kontoen. Det er ikke lagt inn en automatisk omkobling.

**Direkte produksjonstilkobling er ikke klarert.** En senere overgang må
kontrollere stabile ID-er, økonomiske aksjeenheter, utført pris, valuta,
handels-/observasjonstid, FX-kilde og alle kostnadskomponenter fra den konkrete
utførelseskilden. Den kilden må være eneste operative bokføringsvei for den nye
kontoen. En vei som mangler et nødvendig felt skal stoppe.

## Øvrige økonomiske hendelser

Implementert for de tre separate, godkjente NOK-aksjekontoene:

- **Utbytte:** dokumentert rettighetsdato og berettiget antall, utbytte per aksje,
  valuta/FX ved betaling, eksplisitt kildeskatt og gebyrer. Retten utledes ikke
  av dagens beholdning; dokumentert utbytte kan komme etter et salg.
- **Splitt/reversert splitt:** dokumentert før-antall og forholdstall. Total
  kostpris beholdes; antall og kostpris per aksje justeres. Kurs etter splitt
  må leveres som kildebelagt markering. Modellen finner ikke på en ny markedskurs.
  Eventuelle splittgebyrer kostnadsføres i kontantregnskapet; historisk kostpris
  beholdes og kostnadskomponentene vises separat.
- **Innskudd/uttak i NOK:** egen kapitalstrøm, atskilt fra gevinst. Komplett,
  fersk verdsetting kreves før strømmen. Andeler for avkastningsmåling utstedes
  eller innløses ved denne NAV-en, slik at avkastningen er tidsvektet. Gebyrer
  er utgifter, ikke innskudd eller gevinst.
- Hendelsene bruker stabile ID-er, samme atomiske kontojournal, replay,
  duplikatvern og samme produksjonssperre som handler. Ingen automatisk
  hendelsesinnhenting er aktivert.

Periodens resultat i kroner er NAV minus åpnings-NAV minus netto ekstern
kapitaltilførsel. Prosentavkastning etter kapitalstrømmer bruker avkastningsandeler,
ikke NAV delt på opprinnelig kapital. Avkastningsandeler er ikke aksjebeholdning.
Netto utbytte, kildeskatt, kapitalbevegelser og kostnader vises separat i rapporten.

Fusjon, fisjon, tegningsretter, tilbakebetaling av kapital, valutaomlegging,
kontantoppgjør for brøkdeler og full innløsning av siste kapitalandel er ikke
støttet som generelle hendelser. De avvises fremfor å bokføres ved antakelser.
Slik støtte krever konkret dokumentert hendelsesgrunnlag. Superfonds native
regnskap har ikke fått en parallell hendelsesmotor; eventuelle slike hendelser
der må avklares før produksjonsovergang.

## 6. Tester og gjenværende feil

Sluttkjøring: **2440 beståtte tester og 4 deltester**, ingen feil eller hopp
i den isolerte pakken, på 368.54 sekunder. Dette omfatter **120 regnskapstester,
15 kilde-/avstemmingskontrakter, 22 PostgreSQL-tester og 79 nettleserforløp**.
Alle tidligere 99 feiltilfeller består fortsatt.

Se [testresultater.json](testresultater.json) og [KJORING.md](KJORING.md) for
sluttall og reproduserbare kommandoer. Syntetiske enhets-/integrasjonstester er
programvarebevis, ikke en gjennomført overgang på produksjonsdata.

Nye tester dekker kapitalflyt uten oppdiktet gevinst, tidsvektet avkastning,
modellkostnader, utbytte etter solgt posisjon, kildeskatt, splitt og etterfølgende
delsalg, ugyldige/manglende data, journalavvik, gjenforsøk etter tapt kvittering,
samtidighet og reell PostgreSQL. Uttrekksverktøyet testes mot skrivebeskyttet
PostgreSQL, avgrensning mot autentiseringsdata og avvisning av avkortet uttrekk.
Nye nettleserforløp leser utbytte-/kapitalrapporten på PC- og mobilbredde.

Begge live-OHLC-testene ble forsøkt på nytt og feilet med CONNECT-proxy HTTP 403.
Direkte forbindelse uten proxy ga heller ingen HTTP-respons innen tidsgrensen.
Leverandørtilgang og leverandørakseptanse er **IKKE VERIFISERT**. Ingen annen
tilgjengelig maskin med fungerende leverandørtilgang er knyttet til oppdraget.

## 7. Merge og produksjonsaktivering

PR #167 kan gjennomgås for de avgrensede kodeendringene, men **anbefales ikke
godkjent som ferdig F3**. Produksjonsavstemming og produksjonsbasert overgangsprøve
er ikke gjennomført, ordinær utførelseskilde er ikke ende-til-ende-verifisert,
og live-leverandørakseptansen er fortsatt uavklart.

Produksjonsaktivering krever de manglende kildene, fullført avstemming per konto,
vellykket isolert prøve, dokumentert åpning og uttrykkelig godkjenning av den
konkrete overgangen. Det er ikke foretatt merge, deploy, produksjonsaktivering,
nullstilling, historisk rekonstruksjon eller overføring av posisjoner.

PR-koden leveres gjennom samme arbeidsgren for #167. GitHub-API returnerte
Forbidden ved oppdatering av selve PR-beskrivelsen. Revidert tekst ligger i
[PR.md](PR.md); ingen ny PR er opprettet.
