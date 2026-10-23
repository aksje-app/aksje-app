# Kontrollert produksjonsovergang – prosedyre til separat godkjenning

Denne prosedyren er **ikke utført**. Ingen produksjonsarkivering, nullstilling,
kontoutkast, aktivering, merge eller deploy inngår i denne oppgaven.

## Forutsetninger og stoppunkt

Koden i denne PR-en tillater restart-handler bare med `APP_ENVIRONMENT=test`
og en konto med testgodkjenning. Produksjons-/utviklingsaktivering av
restartkontoer er fortsatt sperret av `AccountStorage`. Den eldre variabelen
`ECONOMIC_PRODUCTION_ACTIVATION_ENABLED` åpner ikke restartkontoene.

**Ikke sett testmiljø på produksjonsprosessen for å omgå sperren.** Før trinn 6–8
må en separat kontrollert endring levere produksjonsgodkjenning, kontovalg for
scheduler og tørrkjøring. Denne PR-en leverer den eksplisitte handelskontrakten,
atomiske transaksjonen og prøvingen; den starter ingen produksjonsjobber.

Driftsansvarlig må først registrere fullstendig kildeinventar, varig privat
arkivmål, krypteringssertifikat og separat oppbevart privat nøkkel. Ingen
produksjonstilgang eller komplett produksjonsinventar er bekreftet i dette
arbeidsmiljøet. Manglende kilde, mislykket kontrollsum eller ukjent aktiv
skriver er stoppgrunn. Ingen økonomiske historikkhull skal fylles med antakelser.

## 1. Pause alle skrivere og scheduler

- Inventer Render-tjenestene mot faktisk drift. Repositoryets `render.yaml`
  definerer `aksje-app` og cron-jobben `aksje-app-report-scheduler`
  (`python scheduled_runner.py`, hvert 15. minutt). Andre aktive workere,
  manuelle kjøringer, UI-handler og rapport-/læringsskrivere må også kartlegges.
- Suspender cron-jobben i Render. Blokker nye skanne-/handelsjobber og manuelle
  handler, og drainer pågående jobber til et avsluttet checkpoint. Sett
  `RUNTIME_BACKGROUND_ENABLED=false`, `REPORT_SCHEDULER_ENABLED=false` og
  `PAPER_TRADING_ENABLED=false` der de gjelder, men stol ikke på flaggene alene:
  kontroller at ingen aktive jobb-leaser eller prosesser kan skrive.
- Registrer commit, miljøidentitet, databaseidentitet, runtime-mapper og tidspunkt
  privat. Ikke slett køer, læringsobservasjoner, gamle posisjoner eller journaler.

## 2. Fullstendig kryptert arkivering

Bruk privat operatørkonfigurasjon som beskrevet i
[forrige kjøreveiledning](../kontrollert-restart-20261023/KJORING.md).
Konfigurasjonen inneholder navn på database-miljøvariabler, ikke passord.

```sh
python scripts/prepare_simulation_restart.py archive \
  --config <privat-konfigurasjon> --sources-quiesced
```

Bekreft alle åtte kategorier: porteføljer, handler, beslutninger/signaler,
rapporter, NAV/resultater, læringsmodeller/observasjoner, strategiparametere,
audit/diagnostikk. Ta med ekstra databaser og rapport-/modellmapper som ikke
ligger i standard runtime. Full dump omfatter alle tabeller i deklarerte databaser.

Arkivet skal ligge utenfor Git og modellagring, på varig privat lagring. Behold
arkiv-ID, kvittering og kontrollsummer privat. Etabler separat sikkerhetskopi,
retensjon og tilgangsstyring; lokale 0400/0500-rettigheter erstatter ikke dette.

## 3. Verifisert tilbakelesing

```sh
python scripts/prepare_simulation_restart.py review \
  --config <privat-konfigurasjon> --archive-id <arkiv-ID> \
  --private-key-file <privat-nøkkelfil>
```

Kontroller alle filhashene og manifestet. Gjenopprett en dekryptert databasekopi
**bare i en ny separat testdatabase**, og sammenlign kildeinventar, porteføljer,
handler, beslutninger, rapporter, tap og læringsmodeller. Kontroller også binære
modellfiler. Slett aldri eller gjenopprett over produksjonsdatabasen.

## 4. Opprett og kontroller tre inaktive utkast

Velg unik periode-ID og starttid med tidssone, **strengt etter arkiv og
verifisert arkivgjennomgang**. `prepare` kontrollerer dette.

```sh
python scripts/prepare_simulation_restart.py plan \
  --config <privat-konfigurasjon> --period-id <periode-ID> \
  --start-at <ISO-tid-med-tidssone> --actor <ansvarlig>
python scripts/prepare_simulation_restart.py prepare \
  --config <privat-konfigurasjon> --archive-id <arkiv-ID> \
  --private-key-file <privat-nøkkelfil> --period-id <periode-ID> \
  --start-at <samme-ISO-tid> --actor <samme-ansvarlig>
```

Kontroller NOK 100 000 / 500 000 / 1 000 000 for Paper / Autonomi /
Superporteføljen, tomme posisjoner, ingen handler og egne åpningsfingeravtrykk.
Behold de gamle kontoene uendret. Ikke lag fiktive salg. Ikke restart Superfond.

## 5. Godkjenning av eksakt periode, kapital og miljø

Legg frem følgende privat for uttrykkelig godkjenning: commit/build, produksjons-
miljøets identitet, periode-ID, alle tre familier, starttid, kapitalbeløp,
åpningshashene, arkivhashene, bekreftet gjenopprettingsprøve og ansvarlig.
Godkjenningen må ha datert referanse og kunne tilbakekalles for videre handel.
Ingen generell godkjenning av «nyeste konto» eller automatisk kontovalg er tillatt.

## 6. Kontrollert kobling – senere aktiveringsendring

Den nye handelskontrakten er `services/restart_trading.py`:

- Ta en eksplisitt `account_reference` med periode, familie, åpningshash,
  godkjenningshash og miljøscope ved opprettelse av jobben; lagre denne i jobben.
- Lever samme referanse, stabil `run_id`, eksplisitt tid, kandidatgrunnlag,
  uendrede strategiinnstillinger og daterte utførelses-/valutabevis med separate
  NOK-kostnadskomponenter. Null kostnad må også ha dokumentert modellforutsetning.
- Kall ordinær Paper/Autonomi/SP-inngang med eksplisitt `restart_context`, eller
  den tilhørende kontrollerte adapteren. Ingen miljøvariabel velger automatisk konto.
- Ny kontant-/posisjonsbeholdning skal bare leses gjennom den valgte periodens
  `AccountStorage`. Gamle synkroniseringer og speilføringer skal ikke kalles.
- Alle markeringer, handler, beslutninger, gjenopptakelsestilstand og jobbkvittering
  bokføres atomisk i én eksisterende NOK-journal. Ikke skriv en parallell saldo.

Produksjonsschedulerens eksplisitte kontobinding og godkjente enablement må
implementeres/gjennomgås separat. Ikke fjern testsperren under drift som snarvei.

## 7. Første prøvekjøring med handel deaktivert

Den senere driftskoblingen skal først levere en ren lese-/beslutningsprøve.
Kontroller aksjesøk/rangering, kandidater, tidssone, markedssesjon, kostnadsmodell,
valutakilder og kontobinding. Sammenlign journalhash før/etter: ingen handel,
godkjenning eller kontantendring skal være skrevet. Denne PR-en har ingen
produksjonskommando for slik scheduler-tørrkjøring.

## 8. Aktivering etter uttrykkelig godkjenning

Etter godkjent tørrkjøring kreves en ny uttrykkelig beslutning om å aktivere den
nøyaktige kontoperioden. Aktiver gjennom den separat kontrollerte driftskoblingen,
start én avgrenset jobb og kontroller resultatet før ordinær tidsplan gjenopptas.
Manglende råkurs, FX, kostnadsforutsetning eller journalavstemming skal stoppe jobben.

## 9. Overvåking og sikker stopp

Kontroller per jobb: forespurt kontoreferanse, beslutninger, antall nye handler,
unikhetsvern, NOK-kontanter, antall aksjer, kostpris, NAV, realisert/urealisert
resultat og nettoavkastning. Kontroller at journal og beholdning stemmer, og at
læringsdata ikke er slettet eller gammel kontosynkronisering har kjørt mot ny konto.

Ved avvik: suspender scheduler/skrivere og behold journalen. Ikke reparer med
direkte saldoendring. Isoler feilbevis og viderefør bare eksakt gjenforsøk av en
allerede identifisert jobb når årsaken er avklart. Konfliktende jobb-ID skal avvises.

## 10. Tilbakeføring uten historikktap

Stopp nye jobber og fjern/sperr den eksplisitte kontobindingen i den senere
schedulerkonfigurasjonen. Behold både gammel historikk, arkivet og hele den nye
periodens journal. Rull eventuelt tilbake programversjonen etter gjennomgang;
eldre kode uten eksplisitt restartstøtte skal ikke få skrive mot den nye perioden.
Ikke kopier gamle saldoer inn i ny konto, ikke slett nye handler, og ikke slett
kvitteringer for å forsøke samme jobb på nytt. Ny oppstart krever ny gjennomgang.
