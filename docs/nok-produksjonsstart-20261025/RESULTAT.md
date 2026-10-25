# NOK-produksjonsstart: native kontroll og konkret kostnadsforslag

Dette fortsetter fra live PR #168 / `de2dc617`. Kontoene, perioden og arkivet
gjenbrukes. Denne endringen aktiverer ingen konto og endrer ingen lagrede
strategier, historikk, læring eller Superfond. Scheduleren skal være suspendert.

## Utført i kode

`simulation_archive.database_fingerprint` bruker nå den tidligere validerte
native UTF-8-algoritmen gjennom `services/native_archive_fingerprint.py`.
Store TEXT-kolonner sendes ikke gjennom PostgreSQL `row_to_json`. Klienten
leser én rad om gangen som UTF-8-bytes og hasher JSON-escaping i 16 KiB-blokker.
SHA-256, sortering, Decimal-behandling, radtelling og multiset-summering er
identiske med det opprinnelige arkivformatet. Eksisterende manifesthash og
restore-review endres ikke. Alle opprinnelige brukertabeller inngår fortsatt.

Kontrollen krever READ ONLY og UTF-8. Den eksisterende verifiserte grensen på
160 MiB per estimert native rad videreføres. Ukjente variable kolonnertyper
med verdier avvises før de hentes; de utelates ikke og går ikke tilbake til den
gamle minnebelastende banen. Dette er en bevisst sperre, ikke generell støtte
for vilkårlig store JSONB/array/numeric-kolonner. De 12 tidligere kontrollerte
produksjonstabellene hadde ingen slike ustøttede verdikolonner. Ved fremtidig
skjema-/størrelsesendring må kontrollen stoppes og adapteren vurderes.

Etter en fysisk testrestore foregår selve verifikasjonslesingen nå eksplisitt
i READ ONLY / REPEATABLE READ. Ingen ny fysisk produksjonsrestore utføres.
Aktiveringssperren sammenligner fremdeles hele databasefingeravtrykket og
runtime-filene med arkivet. Bare den eksakte nye perioden og ruter som peker
til den, kan unntas. Eldre perioder, andre ruter, læring og Superfond beholdes.

Klargjøring av account-config, aktiveringsforespørsel og live-preview krever
nå lagrede, gjenkjennelige strategiinnstillinger. Manglende konfigurasjon kan
ikke erstattes med en hel default-konfigurasjon eller lokale fallback-filer.
Ordinær trading beholder sin eksisterende innstillingslesing. For eksisterende
delvise konfigurasjoner beholdes samme kanoniske fletting/normalisering som
appen allerede bruker; ingen overstyringer lagres eller endres av klargjøringen.

## Faktiske produksjonsinnstillinger og input

| Konto | Autoritativ innstillingskilde | Faktiske input som må kontrolleres |
| --- | --- | --- |
| Paper | `trading_rules.rules WHERE id=1`, deretter eksisterende `settings/trading_rules.json` etter appens vanlige prioritet | Fullført faktisk scannerkjøring og kandidat-/beslutningsbevis; `paper_trading/scanner_status.json`, snapshot-ID og tilhørende faktiske snapshots. Et checkpoint i `SCANNING`/`FINALIZING` er ikke fullført input. |
| Autonomi | `autonomous_portfolio/parameters.json`, med eksisterende normalisering | Faktisk fullført markedskjøring og dens Autonomi-handoff fra `market_intelligence/runs/<run_id>.json` / `market_intelligence/latest_run.json`. Den faktiske governance-filtreringen i `autonomi_core/runtime/orchestrator.py` skal bevares. |
| Superporteføljen | `config` i `super_portfolio/state.json`, med eksisterende normalisering | Den faktisk brukte pipeline med `run_id`, `created_at`, kandidater og tilhørende integritets-/fullføringsbevis; `investment_pipeline/latest_run.json` og `super_portfolio/market_pipeline.json` må ikke forveksles uten å kontrollere faktisk kilde. |

En tidligere faktisk READ ONLY-kvittering bekrefter at de lagrede
innstillingsdokumentene finnes, og at Superporteføljens sats var 10 bp. Den
inneholder ikke komplette nåværende strategiinput eller kanoniske snapshots.
De skal derfor ikke rekonstrueres fra kode-defaults eller en tom kandidatliste.

Direkte databaseadgang mangler fra arbeidsmiljøet. Det tidligere avgrensede
Render-leseoppdraget `job-dbev9kjncjis73fis710` feilet; autentisert loggtilgang
gir fortsatt HTTP 403. Ingen nytt leseoppdrag er startet uten en diagnose av
det første. **Nåværende innstillinger/input er derfor ikke hentet eller
produksjonsverifisert av denne endringen.** Dette er en teknisk tilgangshindring,
ikke en ny kontroll brukeren bes om å kjøre.

## Kostnadsforslag

Alle tre komplette, maskinlesbare **forslag** ligger i
[cost-policy-proposals.json](cost-policy-proposals.json). De lastes ikke av appen,
installeres ikke i databasen og er ikke signerte produksjonsgodkjenninger.

| Konto | Modellens grunnsats per kjøp/salg | Simulert slippage | Ny foreslått FX-komponent |
| --- | --- | --- | --- |
| Paper | 0,05 % fra backtesting | 0,10 % ugunstig utførelseskurs | 0,25 % i tillegg ved valutaveksling |
| Autonomi | 0,20 % samlet modellkostnad fra læringssensitiviteten | Intet ekstra slippagetrekk foreslås oppå samlet sats | 0,25 % i tillegg ved valutaveksling |
| Superporteføljen | Viderefør dokumenterte 0,10 % | Intet nytt slippagetrekk foreslås oppå samlet sats | 0,25 % i tillegg ved valutaveksling |

**FX-forslaget er 25 bp av faktisk konvertert brutto NOK per kjøp og salg.**
Appens NOK-regnskap gjør opp hver handel i NOK og fører ikke en separat
utenlandsk kontantkonto. Utenlandsk kjøp og salg innebærer derfor hver sin
modellkonvertering. NOK-noterte instrumenter har ingen valutakonvertering.
V2-policyen beskriver dette som `NO_CURRENCY_CONVERSION`, ikke gratis veksling.

Kilden for 25 bp er den eksisterende, dokumenterte simuleringsforutsetningen i
[superfund_engine.py:14](https://github.com/aksje-app/aksje-app/blob/de2dc61716726647013e341c9bcac1024c894aaf/superfund_engine.py#L14)
og dens faktiske modellberegning i
[superfund_engine.py:243](https://github.com/aksje-app/aksje-app/blob/de2dc61716726647013e341c9bcac1024c894aaf/superfund_engine.py#L243).
Dette er et konkret gjenbruksforslag for friksjon ved NOK/utenlandsk valuta,
**ikke en dokumentert gammel FX-policy for aksjekontoene eller en bekreftet
meglerprisliste**. Offentlig ekstern meglerdokumentasjon var ikke tilgjengelig
gjennom nettverkstilgangen. En faktisk megleravtale kan ha andre vilkår.
Superfonds modell, data og kapital endres ikke ved dette forslaget.

I den nye foreslåtte policyen holdes FX uttrykkelig **utenfor** grunnsatsene
5/20/10 bp. Det er en ny modellbeslutning som krever særskilt godkjenning,
ikke en påstand om hvordan de gamle ufordelte satsene behandlet FX. Dermed er
foreslått bokført gebyr for en utenlandsk handel henholdsvis 30/45/35 bp.
Paper har i tillegg slippage i prisen, aldri et nytt slippagegebyr. Ingen
ekstra turnover-kostnad eller valutaspread legges inn i kursen på toppen av FX.
En nøytral, dokumentert FX-kurs brukes til omregning, og modellgebyret bokføres
én gang separat. Fremtidige kilder som allerede inkluderer valutagebyret i
utførelseskursen må avstemmes før bruk, slik at samme friksjon ikke gjentas.

På 10 000 NOK faktisk brutto utenlandsk handelsverdi blir gebyrene derfor
30 NOK / 45 NOK / 35 NOK. NOK-handel gir 5 NOK / 20 NOK / 10 NOK i grunnkostnad.
Dette er forklarende modellregning, ikke en utført handel eller et kursbevis.

Alle forslag bruker motorens eksisterende samlede modellkostnadskomponent
pluss FX. For Paper er grunnsatsens kilde den modellerte kurtasjen. Dermed
bevares 5 bp uten å fylle ukjente øvrige gebyrarter med null. Rapporteringen
merker fordelingen som ufullstendig; dette er ikke en full meglerkostnadsoppgave.
Eventuelle fremtidige faktiske gebyrer krever dokumentasjon og en ny eksplisitt
policyavstemming. Paper/Autonomi blir ikke automatisk satt til disse satsene.

Andre kilder:
[Paper 5/10 bp](https://github.com/aksje-app/aksje-app/blob/de2dc61716726647013e341c9bcac1024c894aaf/backtesting_engine.py#L32),
[Autonomi 20 bp sensitivitet](https://github.com/aksje-app/aksje-app/blob/de2dc61716726647013e341c9bcac1024c894aaf/learning_runtime.py#L178),
[Superporteføljen 10 bp](https://github.com/aksje-app/aksje-app/blob/de2dc61716726647013e341c9bcac1024c894aaf/super_portfolio.py#L381).

## Bevis, signering og gjenstående arbeid

Eksisterende periode er `nok-20261025T012118Z`, med 100 000 / 500 000 /
1 000 000 NOK og de eksisterende DRAFT-åpningene. Arkiv-ID er
`20261024T232608Z-4df389aad81c4186949d7133e32c0649`. Restore-review SHA-256 er
`3118134d55f84c0935ab4d22704117db160bd730f46636ab5488547290f1e90a`.
Den tidligere produksjonskvitteringen har kanonisk SHA-256
`b853945a5ff7f90f160cee29bdef1df36e610b3cc4224fddee4c6251aed4dac3`.
Disse henvisningene er bevarte faktiske bevis, ikke en ny arkivering/restore.

Faktiske signérbare forespørsler krever nåværende kanoniske innstillinger,
komplett original restore-review, godkjent kostnadspolicy og operatørens
identitets-/godkjenningsfelter. De opprettes gjennom den eksisterende
`production_restart.request`, slik at konto, kapital, starttidspunkt, periode,
arkiv og åpning bindes eksakt. Ingen manglende bevis eller kontrollsum er
konstruert, og ingen signatur er laget. Den private nøkkelen skal forbli
utenfor Git og samsvare med det pinnede offentlige sertifikatet. Tidligere delt
privat nøkkel skal erstattes før faktisk signering.

Søndag gir ingen ferske åpningsbevis for de aktuelle aksjemarkedene. Når
relevante markeder åpner og faktiske input er tilgjengelige, skal den eksisterende
ordrefrie `live_preview` bruke daterte pris-/valutabevis. Gamle kurser stemples
ikke om. Verken ferske markedskontroller eller produksjonstørrkjøring hevdes
utført her.

Scheduleren forblir suspendert på eldre kode; web er sist bekreftet live på
`de2dc617`, Auto-Deploy OFF. Denne nye kodeendringen er ikke deployet. Ingen
kostnadsgodkjenning tillater scheduler-gjenopptak eller kontoaktivering.

## Målrettet verifikasjon

- Native-kontroll, eksisterende syntetisk arkivlivsløp og produksjonsmodus i
  isolert lokal PostgreSQL: 79 bestått. Dette gjentok ikke produksjonsarkivet.
- Etter innstramming av innstillingsbevis: 71 bestått i native-, innstillings-
  og produksjonskontrolltestene, inkludert eksisterende signatur-/rutesperrer.
- Siste innstillings- og kostnadsforslag: 15 bestått. Dette dekker også feilaktige
  konfigurasjoner uten gjenkjennelige felter, de eksakte modellbeløpene,
  NOK/NOK og at slippage bare påvirker prisen.
- Ekstra faktisk PostgreSQL-kontroll for alle tre familier: 3 bestått;
  manglende lagrede innstillinger stopper både request og preview før
  markedsoppslag, med DRAFT-bundle uendret.
- `compileall` for endrede Python-filer og `git diff --check` bestått.

Testgruppene overlapper og skal ikke summeres. Dette er isolerte tester,
ikke nye produksjonskvitteringer eller ferske markedsdata. Ingen full
systemrevisjon eller full nettlesersuite er kjørt på nytt.

## Beslutning som kreves fra brukeren

Godkjenn eller avvis **én samlet ny simuleringspolicy**: Paper 5 bp + 10 bp
slippage, Autonomi 20 bp og Superporteføljen 10 bp, med **25 bp FX i tillegg**
kun ved valutakonvertering. Konsekvensen er 30/45/35 bp bokførte modellgebyrer
for utenlandske handler; Paper-slippage ligger bare i prisen. Dette omfatter
valg av en avgrenset simulert kostnadsmodell, ikke aksept av ukjente faktiske
meglergebyrer som null. Det er en kostnadsgodkjenning, **ikke personlig B**.

Tilgangshindringen og markedstiming er tekniske forhold; brukeren bes ikke
lete etter lagrede innstillinger eller gjenta tidligere kontroller.
