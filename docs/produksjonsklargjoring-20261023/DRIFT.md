# Operatørprosedyre for kontrollert NOK-start

Dette er en planlagt driftsoperasjon, **ikke** en aktivering ved merge/deploy.
Ingen kommando i denne prosedyren er kjørt mot produksjonen i Codex.
Bruk samme versjon av koden som er testet, Python 3.12, OpenSSL og PostgreSQL-
klienter kompatible med kildeserveren. Ingen `APP_ENVIRONMENT=test` i produksjon.

## Installasjon og private operatørfiler

Bruk en privat mappe utenfor Git og alle modell-/runtime-trær, med modus 0700.
Arkivmappen må også ha 0700. CMS-arkiver opprettes eksklusivt, forsegles og
kan ikke overskrives av programmet. Oppbevar en uavhengig kopi på lagring som
nye modellkjøringer ikke har skrivetilgang til. Kontrollsummer erstatter ikke
operatørens verifikasjon av at denne kopien finnes og kan leses.

Private operatørfiler, databasekopier, nøkkel, oppdrag og tørrkjøringsresultater
skal aldri legges i GitHub. Konfigurasjonen bruker **navn** på miljøvariabler for
forbindelser, ikke tilkoblingsstrenger. Aktiveringsprosessen trenger tilgang til
arkivnøkkelen; ordinære web-/schedulerprosesser trenger bare det offentlige
operatørsertifikatet. Fjern nøkkeltilgangen etter operatøroperasjonen.

Sett eksplisitt i den planlagte produksjonsinstallasjonen:

- `APP_ENVIRONMENT=production`.
- `NOK_DEPLOYMENT_ID`: ett operatørvalgt, stabilt installasjonsnavn, identisk for
  web, scheduler og arbeidere som skal bruke de samme kontoene.
- `NOK_APPROVAL_CERTIFICATE`: filsti til det pinnede offentlige signeringssertifikatet.
- `NOK_APPROVAL_CERT_SHA256`: SHA-256 av nøyaktig denne sertifikatfilen.
- `DATABASE_URL` og eventuelt separat `AUTH_DATABASE_URL`: de eksisterende,
  kontrollerte databaseforbindelsene. `ALLOW_LOCAL_STORAGE_FALLBACK=false`.
- Vanlige schedulerflagg beholdes; Paper krever også `PAPER_TRADING_ENABLED=true`
  når ordinær handel faktisk skal starte. Det flagget oppretter/velger ingen konto.

Disse verdiene er **ikke** aktivert eller lagt som automatiske aktiveringsverdier
inn i `render.yaml`. Det gamle `ECONOMIC_PRODUCTION_ACTIVATION_ENABLED=true`
er ingen godkjenning og åpner ikke kontoene.

I kommandoene nedenfor er `/secure/nok` en plassholder for operatørens private
mappe, `PERIODE` en ny eksplisitt periode-ID og `T0` en eksplisitt ISO-startdato
med tidssone. Alle outputfiler må være nye; verktøyet overskriver dem ikke.

## 1. Kartlegg kilder og eksisterende strategi før sikkerhetskopiering

```sh
python scripts/production_restart.py inventory --config /secure/nok/config.json --output /secure/nok/inventory.json
python scripts/production_restart.py account-config --config /secure/nok/config.json --output /secure/nok/account-settings.json
```

Første `config.json` kan inneholde `extra_roots` og ellers være tom.
Gå gjennom resultatet for **hver Render-tjeneste/arbeider og hvert diskvolum**.
Discovery omfatter APP_RUNTIME_ROOT med services, data, cache, logger, backups;
separate StorageService-/auth-trær; eldre data/cache/logs/storage/runtime/reports/
models/config/.streamlit/learning/exports-trær; løse JSON-/SQLite-/modell-/rapport-
filer og oppdagede konfigurerte filstier. DATABASE_URL, AUTH_DATABASE_URL og
konfigurerte eldre databasealiaser registreres som variabelnavn, uten verdier.

Data på andre containere, eksterne rapport-/objektlagre eller frakoblede gamle
volumer må hentes/stages og tas med i `extra_roots`. Discovery hevder ikke at
PostgreSQL alene inneholder historikken. Operatøren må avklare slike eksterne
kilder; uavklarte kilder betyr at arkivdekningen ikke kan godkjennes.

Fyll den private konfigurasjonen med:

- `runtime_roots` og `database_environment_variables` fra gjennomgått inventar;
  alle oppdagede kilder må være inkludert, ingen stille utelatelser.
- `coverage`: hver kategori i inventory peker på inkluderte kildenavn.
- `inventory_ack_sha256`: inventory-resultatets `inventory_sha256`;
  `external_stores_reviewed=true` og `coverage_confirmed=true` først etter kontroll.
- `archive_root`, `certificate`, ny `restore_destination` og én egen
  `restore_database_environment_variables` per arkivert database.
- `accounts`: de tre uendrede strategikonfigurasjonene fra account-settings.json.
  Per konto angis en dokumentert modellkostnadspolicy:
  `cost_policy.components_per_fill` med `brokerage_nok`, `fx_cost_nok`, `other_nok`
  og `cost_policy.source_ref`. Dette er eksplisitte NOK-kostnader per modellhandel,
  ikke en påstand om faktiske meglerkostnader. Ingen kostnader antas av programmet.
- Eventuelle `pg_dump_program`/`pg_restore_program` dersom klientene ikke ligger i PATH.

Startkapital er fast i koden og kontrolleres ved godkjenning: Paper 100 000 NOK,
Autonomi 500 000 NOK, Superporteføljen 1 000 000 NOK. Alle åpner uten aksjer.
Strategiinnstillinger må samsvare med eksisterende konfigurasjon. Konto-/miljø-
godkjenningen dokumenterer startsnapshotet og tillater bare eksisterende kanonisk
konfigurasjon/governance videre. Hver jobb journalfører faktisk anvendte parametere.
Eksisterende kontrollerte parameter-/læringsoppdateringer fryses ikke av restart.
Denne leveransen endrer ingen aktive strategiparametere eller læringsmodeller.

## 2. Stopp alle skrivere og ta komplett, privat sikkerhetskopi

Stans cron/arbeidere, manuelle skanninger, rapportskrivere, læringsskrivere og
kontomutasjoner i web. Vent på pågående jobber og avbryt gamle ventende handelsjobber gjennom
de eksisterende jobbkontrollene. Første jobb etter start skal bruke nye innspill. Dette må kontrolleres på tvers
av tjenester; CLI-flagget er operatørens attestasjon, ikke en fjernstyrt Render-lås.
For senere sikkerhetskopier av aktive NOK-kontoer: stopp også hver konto med
STOP-prosedyren nedenfor før global quiescence.

```sh
python scripts/production_restart.py archive --config /secure/nok/config.json --sources-quiesced --output /secure/nok/archive-receipt.json
```

Full `pg_dump` kjøres mot eksporterbare read-only repeatable-read-snapshots.
Alle tabeller bevares, også ukjente navnerom. Filene kontrolleres før/under/etter
kopiering; hver fil får størrelse og SHA-256 i det krypterte manifestet.
Databasens modellrader får strømmende fingeravtrykk i samme snapshot.
Oppbevar den forseglede arkiv-ID-en og kontroller den uavhengige kopien.

## 3. Gjennomfør faktisk gjenoppretting uten å overskrive noe

Opprett på forhånd **nye, tomme** isolerte databaser med navn `nok_restore_*`.
Bruk miljøvariabler for tilkoblingene i restore_database_environment_variables.
De skal ikke være de aktive DATABASE_URL/AUTH_DATABASE_URL. Hvert arkivert
DB-navn må ha et eget mål. Sørg for nødvendige PostgreSQL-utvidelser/klientversjon.

```sh
python scripts/production_restart.py restore --config /secure/nok/config.json --archive-id ARKIV_ID --private-key-file /secure/offline/archive-key.pem --output /secure/nok/restore-result.json
```

Verktøyet dekrypterer, verifiserer alle filer og pakker ut bare til en **ny** privat
mappe. `pg_restore --exit-on-error --no-owner --no-privileges` bruker aldri
`--clean`, DROP eller overskriving av aktive databaser. Gjenopprettede database-
fingeravtrykk må stemme med snapshotet. En vellykket restore-review.json kreves
for godkjenning; en feil/incomplete restore gir ingen godkjent kvittering.

## 4. Klargjør utkast og gjennomfør produksjonstørrkjøring

Velg T0 etter arkivkontroll, med nok tid til klargjøringen. Før godkjenning og
handelsprøve må T0 være nådd; godkjenning/handler kan ikke tilbakedateres før åpningen.

```sh
python scripts/production_restart.py prepare --config /secure/nok/config.json --archive-id ARKIV_ID --period PERIODE --start-at T0 --actor OPERATØR --private-key-file /secure/offline/archive-key.pem --output /secure/nok/prepared.json
```

Dette lager tre DRAFT-kontoer i ett separat bundle, uten ruting eller aktivering.
Ingen gamle posisjoner selges, og ingen historiske tall konstrueres.

For hver familie (`paper`, `autonomy`, `super_portfolio`) hentes faktiske,
ferdiglagrede skanne-/pipelineinnspill til en privat JSON-fil. Ikke lag oppdiktede
kandidater, priser, valutakurser, handler eller to-skanningsbevis.

- Paper: liste av vanlige signalinnspill (`ticker`, `operation=AUTO`, `signal`,
  `confidence`, `trade_context`, med faktisk entry_confirmation der det finnes).
- Autonomi: faktiske, ferdige beslutningskandidater med dokumentert teknisk
  strategibidrag fra samme snapshot; rå univers-/oppdagelsesrader er ikke det
  samme som ferdige beslutningsinnspill.
- Superporteføljen: den fullførte uavhengige markedspipelinen med opprinnelig run_id.

```sh
python scripts/production_restart.py dry-run-live --config /secure/nok/config.json --period PERIODE --family paper --input /secure/nok/paper-input.json --output /secure/nok/paper-dry-run.json
```

Gjenta for de to andre kontoene med deres innspill. Kommandoen bruker ekte
kurs-/valutaleverandør, eksisterende strategikonfigurasjon og eksplisitte kostnader.
Strategiene og NOK-motoren kjøres bare i minnet. Resultatet inneholder bevis,
beslutninger, blokkeringer og prøveregnskap; kildens konto/journal må være uendret.
Tom kandidatstrøm er ikke dokumentasjon på vellykket kandidat-/leverandørdekning.
Kontroller både kandidatgrunnlaget og eventuelle avvisninger i resultatene.
`dry-run` finnes også for allerede dokumenterte komplette private jobbinnspill.

Yahoo må kontrolleres fra den faktiske produksjonsinstallasjonen i relevant
markedstid: `provider-check` bruker en privat inputfil med `instruments`, f.eks.
`{"MYCR.ST":"SEK","MSFT":"USD"}`, og den dokumenterte `cost_policy`.
Tidspunkt tas fra faktisk klokke; aksjekurs og SEK/NOK eller USD/NOK må ha ferske,
sporbare observasjoner. Ikke endre proxy-/sikkerhetsregler for å få grønt resultat.

```sh
python scripts/production_restart.py provider-check --config /secure/nok/config.json --input /secure/nok/provider-input.json --output /secure/nok/provider-result.json
```

Hvert instrument får BESTÅTT/IKKE VERIFISERT. Manglende bevis gir exitkode 2 og en
privat resultatfil. En substituert leverandørtest erstatter ikke denne kontrollen.

## 5. Godkjenn eksplisitt og aktiver konto for konto i planlagt startvindu

Hold fortsatt skriverne stanset. Gjennomgå arkiv, gjenoppretting, åpning,
kostnader, miljø, strategi og tørrkjøringsresultater. Utfør for hver familie:

```sh
python scripts/production_restart.py request --config /secure/nok/config.json --period PERIODE --family paper --actor OPERATØR --approval-ref GODKJENNINGSREFERANSE --at GODKJENNINGSTID --output /secure/nok/paper-request.json
python scripts/production_restart.py sign --config /secure/nok/config.json --input /secure/nok/paper-request.json --confirmation REQUEST_SHA256 --private-key-file /secure/offline/operator-key.pem --output /secure/nok/paper-grant.json
python scripts/production_restart.py activate --config /secure/nok/config.json --input /secure/nok/paper-grant.json --confirmation REQUEST_SHA256 --private-key-file /secure/offline/archive-key.pem --output /secure/nok/paper-activation.json
```

REQUEST_SHA256 er fingeravtrykket CLI skrev for nøyaktig request-filen, ikke
fingeravtrykket til den signerte grant-filen. Kontroller innholdet før signering.
Gjenta med Autonomi og Superporteføljen, hver med egen godkjenning og filnavn.
Konto, kapital, periode, installasjon, åpning og arkiv er bundet til signaturen.
Aktivering revaliderer også at runtime og databasen fortsatt samsvarer med
arkivet; bare denne nye periodens egne klargjørings-/rutingrader kan avvike.
Feil arkiv, endret historikk, feil miljø eller feil signatur blokkerer operasjonen.

Ved avbrudd mellom kontogodkjenning og rutepublisering kan samme grant leveres
på nytt. Åpning og journal nullstilles ikke. En annen periode/grant overskriver
aldri en eksisterende rute. Kontroller `status` for alle tre før skrivere startes.
Superfond har ingen ny rute og beholder sin native regnskaps-/handelsvei.

Start ordinære jobber kontrollert og kontroller første kvittering/NAV per konto.
Paper-scanneren, Autonomi-orchestratoren og Superporteføljens scheduler/arbeider
bruker de samme ordinære strategiene, men bokfører mot valgt NOK-journal.
Gjenforsøk bruker den lagrede jobbkvitteringen. Ingen posisjons-/kontantsaldo hentes
fra gamle kontoer. Kontroller offentlig rapportvisning og nedlasting på PC/mobil.

## 6. Stopp, gjenopptakelse og tilbakeføring

STOP og RESUME krever konto, periode, operatør, begrunnelse og SHA-256 av:
`{"period_id":PERIODE,"family":FAMILIE,"action":"STOP" eller "RESUME","deployment_id":NOK_DEPLOYMENT_ID}`,
beregnet med `services.economic_opening.digest` på nøyaktig dette objektet.

```sh
python scripts/production_restart.py stop --config /secure/nok/config.json --period PERIODE --family paper --actor OPERATØR --reason BEGRUNNELSE --confirmation HANDLINGS_SHA256 --output /secure/nok/paper-stop.json
python scripts/production_restart.py resume --config /secure/nok/config.json --period PERIODE --family paper --actor OPERATØR --reason BEGRUNNELSE --confirmation HANDLINGS_SHA256 --output /secure/nok/paper-resume.json
```

Begge endringer serialiseres på samme bundle-lås som handler. Etter at STOP er
bekreftet, kan ingen senere jobb passere med gammel RUNNING-status. Pågående
transaksjon fullfører eller rulles tilbake før STOP får låsen. Ruten beholdes;
PAUSED gir aldri automatisk retur til gamle kontoer. Journal, tap og læring slettes ikke.

Ved driftsgjenoppretting: STOP alle kontoer, stans alle skrivere, ta/velg en
kontrollert etter-start-sikkerhetskopi og kjør samme restore til nye tomme mål.
Behold original DB, opprinnelige runtime-trær og arkiv urørt. Kontroller journal,
NAV, rapporter og læring i de gjenopprettede målene. Ved planlagt overgang til
slike mål kopieres verifiserte runtime-trær til nye separate runtime-stier uten
overskriving, og operatøren setter eksplisitt de kontrollerte DB-/runtime-verdiene.
Installasjons-ID/sertifikat må være tilsiktet; et annet miljø får ikke handle med
produksjonsgranten. RESUME utføres først etter kontroll. Dette gjøres ikke av restore.

Tilbakeføring betyr stopp og bevaring av siste økonomiske sannhet, ikke gjenbruk
av gammel saldo eller fiktive motsalg. Ved kode-tilbakeføring holdes skrivere
stanset; en eldre binær uten NOK-rutestøtte skal ikke starte handel på de gamle
lagrene. Ingen automatisk kode-/data-rollback utføres av aktiveringsverktøyet.

Dokumenterte utbytter, splitter og kapitalstrømmer kan bokføres via `economic-event`
med eksplisitt konto/periode, kildebevis og bekreftelsesfingeravtrykk av hele
hendelsen, operatøren og installasjons-ID-en. De bruker samme autoritative journal.
Ukjente hendelser eller manglende dokumentasjon stoppes.
