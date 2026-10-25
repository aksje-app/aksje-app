# Eksisterende kostnadsmodell og status før godkjenning B

Dato: 25. oktober 2026. Ingen aktivering eller appendring er utført.

## Konklusjon og bevisnivå

Det finnes **ikke én felles dokumentert produksjonssats** som kan kopieres til
alle tre nye NOK-kontoer. Backtestingens 0,05 % kurtasje / 0,10 % slippage,
Autonomiens 0,20 % kostnadsfølsomhet og Superporteføljens 10 bp er ulike modeller.
De skal ikke legges sammen eller brukes om hverandre.

Render-API-et bekreftet 25. oktober kl. 02:46 norsk tid at siste deploy er `live`,
commit `2559bcfc1a1da11d3ce9406322410bd02bebaa62`. De 24 kostnads-/kontrollfilene
som denne revisjonen bygger på, er byte-identiske med den commiten i Git.
API-konfigurasjonen oppgir `APP_ENVIRONMENT=production`, `STORAGE_MODE=postgres`
og en konfigurert `DATABASE_URL`. Scheduleren er fortsatt `suspended`.
Dette er direkte API-observasjoner, ikke antakelser fra lokal kode.

**Lagrede produksjonsoverstyringer og nåværende DRAFT-status er ennå ikke lest
på nytt fra databasen i denne revisjonen.** Databaseverten er intern og kan ikke
navneoppløses fra Codex-arbeidsmiljøet. Ingen alternativ database er brukt.
Den medfølgende, avgrensede READ ONLY-kontrollen bruker eksisterende Render-SSH
fra Windows-PC-en. Resultatet må foreligge før kolonnen «lagret verdi» kan fylles
ut eller nåværende produksjonsstatus bekreftes uavhengig av sluttkvitteringen.

## Hvilken kode brukes til hva?

| Bane | Dokumentert kodeverdi | Virkning | Hva den ikke beviser |
| --- | --- | --- | --- |
| Historisk backtesting | Kurtasje 0,05 % av utført bruttoverdi, per handel | Trekkes i backtestregnskapet | Ikke Paper-/Autonomi-kurtasje i produksjon |
| Historisk backtesting | Slippage 0,10 % | Kjøpspris økes, salgspris reduseres | Ikke eget gebyr; skal ikke trekkes igjen som kontantkostnad |
| Ordinær eldre Paper Trading | Ingen egen kurtasje-/FX-/slippageberegning i oppgjøret | Kontanter endres med antall × utførelseskurs | Fravær av beregning er ikke dokumentert nullkostnad eller fullstendig NOK-nettoresultat |
| Ordinær eldre Autonomi | Ordinært oppgjør på observerte priser, brutto før gebyrer | Kjøp trekker handelsverdi; salg gir bruttoproveny | 0,20 % trekkes ikke automatisk fra denne kontantbeholdningen |
| Autonomi, historisk læringsreplay | 0,20 % av omsatt verdi | Kostnadsfølsomhet trekkes fra beregnet sluttresultat | Ikke en journal over faktiske modellgebyrer i hovedkontoen |
| Autonomi, erstatningsbeslutning | `transaction_cost_pct`, fallback 0,2 | Terskel for om forventet forbedring forsvarer erstatning | Ikke en belastning på kontanter |
| Superporteføljen, eldre oppgjør | `config.transaction_cost_bps`, kodefallback 10 bp = 0,10 % | Kostnad per kjøp/salg trekkes i modellens kontantoppgjør | Ikke bare rapportestimat; heller ikke dokumentert meglerpris eller full FX-kostnad |
| Superporteføljen, turnover-rapport | `turnover_cost_summary`, standard 10 bp | Estimat ut fra absolutte vektendringer og porteføljeverdi | Ikke en ekstra kostnad som skal trekkes i tillegg til oppgjøret |
| Ny NOK-ruting, alle tre | Eksplisitte `components_per_fill` i NOK | Kopieres fra signert policy og bokføres per utførelse | Ingen automatisk konvertering fra bps/prosent til handelsavhengig kostnad |

### Backtesting

Kilder: [standardforutsetninger](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/backtesting_engine.py#L32),
[kurtasje og fill-pris](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/backtesting_engine.py#L113),
[justerbare UI-verdier](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/backtesting_engine.py#L390).
Dette er standarder som brukeren kan overstyre for en historisk kjøring.
Det er ikke grunnlag for å kalle dem lagret produksjonskurtasje.
Den separate månedlige strategitesten har dessuten en annen modell:
[0,002 × beregnet turnover](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/backtest_strategy.py#L22).

### Paper Trading

Ordinære kall forsøker først den eksplisitt valgte nye NOK-ruten. Når ingen rute
er valgt, brukes den eldre oppgjørsbanen. Kilder:
[rutevalg](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/trading_engine.py#L616),
[kjøp](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/trading_engine.py#L797),
[salg](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/trading_engine.py#L861).
Regelsettet inneholder ikke en standard kurtasje-/FX-policy
([DEFAULT_RULES](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/trading_settings.py#L8)).

Det finnes også en generell `SimulatedExecutionService` med standardargumentene
`fee_pct=0.0`, `slippage_bps=0.0`. Dette er en annen utførelsesbane, brukt blant
annet av læringskontoer; den må ikke forveksles med bevis for ordinær Paper Trading
eller de tre nye NOK-kontoenes policy.
[Generell utførelse](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/simulated_execution_service.py#L98).

### Autonomi

Motoren beskriver selv den ordinære historiske banen som «gross of fees»:
[produksjonsreplay-kontrakt](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/autonomous_portfolio.py#L183).
Uten NOK-session gir [salg](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/autonomous_portfolio.py#L1779)
`quantity * price`; [kjøp](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/autonomous_portfolio.py#L2454)
trekker handelsverdi. I NOK-session kommer gebyr og FX fra den særskilte fill-kontrakten.

0,20 % har to andre konkrete bruksområder:

- [Læringsreplay](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/learning_runtime.py#L177):
  `turnover * .002`, merket `0.2_PERCENT_TURNOVER_SENSITIVITY` og
  `PRODUCTION_MARKS_GROSS_OF_FEES`. Kommentaren sier uttrykkelig at dette er en
  sensitivitet, ikke oppdiktede produksjonsutførelser.
- [Erstatningsbeslutning](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/autonomous_portfolio.py#L2287):
  lagret `transaction_cost_pct` eller fallback 0,2 sendes til
  [exit_policy](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/exit_policy.py#L158)
  som terskel for forventet erstatningsgevinst.

`trigger_slippage_pct` i læringsjournalen er dessuten observert forskjell mellom
resultat og stopputløser, ikke en fast 0,10 %-slippagesats eller et kontantgebyr.
[Kilde](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/autonomous_portfolio.py#L1520).

### Superporteføljen

[Konfigurasjonen](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/super_portfolio.py#L381)
har standard 10 bp. Ved ordinært oppgjør sender motoren denne satsen til
[settle](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/super_portfolio.py#L2683).
[Oppgjørsfunksjonen](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/super_portfolio_accounting.py#L39)
beregner `fee = gross * cost_bps / 10000`, trekker beløpet ved kjøp og salg,
lagrer `transaction_cost`/`cost_bps` og lar kostnaden redusere modell-NAV.
Dette er en **bokført simulert modellkostnad**, ikke et eksternt meglerbilag.

[Turnover-rapporten](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/super_portfolio.py#L217)
har en separat estimatfunksjon. I den ordinære oppgjørsbanen erstattes resultatet
av oppgjørets `turnover_costs`. Man skal ikke belaste begge.
Historiske enheter kan være `MODEL_PRICE_RATIO_UNITS`; et felt kalt «NOK» eller
`base_currency` gjør ikke gamle vektbaserte enheter til dokumenterte aksjer eller
bevis for at FX tidligere var riktig bokført.

**Lagret konfigurasjon og faktiske journalrater går foran kodefallback.** Den nye
kontrollen leser `super_portfolio/state.json` og hele den tilgjengelige native
`super_portfolio/transactions.jsonl` med avgrenset minnebruk. Den rapporterer
lagrede satser, kostnadssummer per dokumentert enhet og manglende kostnadsfelt.
En manglende sats blir ikke automatisk «10 bp brukt i alle historiske handler».

## Valuta og Superfond

Eldre Paper-/Autonomi-oppgjør har ingen generell separat, dokumentert beregning
av FX-påslag i banene over. Superporteføljens eldre generelle oppgjør skiller heller
ikke 10 bp i kurtasje, FX og øvrige komponenter. **Dette er et dokumentasjonshull,
ikke dokumentert null valutakostnad.**

Den nye NOK-hovedboken krever faktisk instrumentvaluta og en datert, kildebelagt
NOK-kurs. Kursomregning og valutapåslag er to forskjellige forhold.
[NOK/NOK = 1](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/economic_ledger.py#L41)
er en matematisk identitet; utenlandsk valuta trenger et ferskt FX-bevis.
Dette setter ikke et automatisk prosentpåslag.
[Markeds-/FX-bevis og kostnader](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/production_routing.py#L23).

Superfond har en **egen** dokumentert modell: standard `fee_bps=10.0`,
`fx_bps=25.0`, FX-påslag bare for annen valuta enn NOK, og halv dokumentert
ETF-spread. Løpende fondskostnader inngår i NAV og trekkes ikke på nytt.
[Parametre](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/superfund_engine.py#L14),
[kostnadsfordeling](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/superfund_engine.py#L242),
[native avstemming](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/superfund_accounting.py#L54).
Dette er Superfonds kodeforutsetninger, ikke en bekreftelse av lagrede overstyringer
eller en tillatelse til å kopiere 25 bp til de tre aksjekontoene.
**Superfond migreres eller endres ikke.**

## Forslag til særskilt NOK-policy

| Konto | Videreførbart grunnlag | Korrekt forslag nå | Mangler før en full policy kan signeres |
| --- | --- | --- | --- |
| Paper, 100 000 NOK | Historisk oppgjør uten særskilt gebyrmodell; 5 bp/10 bp finnes bare i backtesting | Ingen numerisk kurtasje-/FX-policy fastsettes fra backteststandardene. Dersom en slik ny modell ønskes, er det et konkret nytt modellvalg | Dokumentert regnskapskostnad og FX-behandling, eventuelt uttrykkelig valgt ny simulering; databasekontrollen først |
| Autonomi, 500 000 NOK | Ordinær kontantbane brutto; 20 bp læringssensitivitet og beslutningsterskel | Behold 20 bp som dokumentert lærings-/beslutningsforutsetning, ikke omdøp til bokført kurtasje | Dokumentert kostnad per utførelse og FX; ny bruk av 20 bp i kontantregnskap er et modellvalg, ikke uendret videreføring |
| Superporteføljen, 1 000 000 NOK | Lagret `transaction_cost_bps`, kodefallback 10 bp, samt faktiske journalrater | Viderefør den faktisk gjeldende satsen som **samlet simulert transaksjonskostnad på handelsverdien i NOK**. Hvis lagret sats er 10, betyr det 0,001 × brutto NOK per kjøp/salg | Bekreft lagret sats; dokumenter eventuell kostnadsdeling/FX. Ikke legg til 25 bp fra Superfond eller dobbelt trekk fra turnover-rapporten |

Eksempel bare på enheten i Superporteføljens kodefallback: en dokumentert
handel på NOK 10 000 gir NOK 10 ved 10 bp; NOK 20 000 gir NOK 20. Dette er en
forklaring av formelen, ikke testbeløp som skal importeres eller en godkjent policy.

Ingen manglende kurtasje, valutakostnad eller øvrig kostnad fylles med 0.
Slippage hører hjemme i en dokumentert fill-pris. Backtestslippage skal ikke
kopieres inn og deretter trekkes en gang til som gebyr.

### Påvist begrensning i den deployede NOK-policyen

[Godkjenningskontrakten](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/production_restart.py#L95)
krever `components_per_fill = {brokerage_nok, fx_cost_nok, other_nok}` og kilde.
[Rutingen](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/production_routing.py#L45)
kopierer faste beløp til instrumentbeviset; [Session.fee/fill](https://github.com/aksje-app/aksje-app/blob/2559bcfc1a1da11d3ce9406322410bd02bebaa62/services/restart_trading.py#L66)
summerer dem og bruker beløpet uavhengig av faktisk antall og handelsverdi.
Det finnes ingen prosent-/bps-beregning i denne ruten.

Man kan derfor **ikke korrekt konfigurere 10 bp som ett fast NOK-beløp** for
alle fremtidige handler. Å merke den samlede historiske kostnaden som kurtasje
og sette FX/annet til 0 ville også være en udokumentert oppdeling.
Før B må enten en dokumentert virkelig fastpris-modell finnes, eller en konkret
endring for handelsavhengige, kildebelagte kostnader gjennomgås og testes.
Denne revisjonen endrer ikke den deployede regnskaps-/strategikoden og foreslår
ikke ny deploy eller aktivering på skjult grunnlag.

## Faktiske kvitteringer som foreligger

Opplastet `final-result.json` har fil-SHA256
`6dfef9978f34681d840e0e26c204bdaacf343b973b35225b6c47a2fdcd7d141b`.
Det er en faktisk operatørkvittering fra brukerens kjøring, ikke en testfixture.
Den rapporterer:

- Status `ARCHIVE_RESTORED_ON_WINDOWS_AND_THREE_INACTIVE_DRAFTS_PREPARED`.
- Arkiv `20261024T232608Z-4df389aad81c4186949d7133e32c0649`.
- Fysisk restorevert `WINDOWS_LOCAL_POSTGRESQL_18`.
- Restore-review SHA256 `3118134d55f84c0935ab4d22704117db160bd730f46636ab5488547290f1e90a`.
- Periode `nok-20261025T012118Z`.
- Paper DRAFT/kontanter/åpnings-NAV 100 000 NOK; Autonomi 500 000 NOK;
  Superportefølje 1 000 000 NOK. Alle har null posisjoner og null realisert/urealisert resultat.
- `independent_windows_copy_verified=true`, `accounts_activated=false`,
  `approval_B_ready=false`, `old_positions_transferred=false`,
  `learning_reset=false`, `strategies_changed=false`.

Dette bekrefter **hva sluttkjøringen kvitterte for**. Filen alene inneholder ikke
alle rå arkiv-/restorebilag, signatur over miljøidentitet eller en fersk
produksjonsforespørsel. Jeg hevder derfor ikke at filen alene er uavhengig bevis
for at alle kontoer fortsatt står uendret nå.

Den medfølgende kontrollen vil avstemme det eksisterende forseglede arkivets
SHA256 på både PC og Render, opprinnelig arkivkvittering, Windows-kopi-/dekrypteringsbevis,
selve restore-reviewens kanoniske hash, alle bevarte restore-filers hashverdier,
manifestets hash og samtlige lagrede database-/tabellfingeravtrykk mot det manifestet,
arkivreferansene i det faktiske lagrede
kontobundlet og Render-sluttkvitteringen. Den uendrede core-rutinen
`verify_bundle` spiller regnskapsgrunnlaget og journalen mot hverandre. Deretter
kreves DRAFT, ingen godkjenning, ingen handler/posisjoner, eksakte startbeløp,
ingen production-controls og ingen valgt route for hver av de tre familiene.
Feil miljø, kildehash, bilag eller status gir stopp, ikke opprettelse av en ny konto.
Dette er en kontroll av den allerede utførte restoren, ikke en ny restore.

## Én skrivebeskyttet kontroll fra eksisterende Windows-vindu

Åpne [KONTROLLER-KOSTNADER-OG-DRAFT.txt](KONTROLLER-KOSTNADER-OG-DRAFT.txt), kopier
hele innholdet til det eksisterende PowerShell-vinduet og trykk Enter.
Ingen opplysninger om modellverdier eller filer må finnes frem manuelt.
Eksisterende SSH-identitet og vertsverifikasjon beholdes; ingen nøkler registreres.

Kontrollen leser faktiske Paper-regler/handelsmetadata, Autonomi-parametre og
kostnadsfelt/handelsjournal, Superporteføljens konfigurasjon/native journal,
arkivbilag og akkurat den nye kontoperioden. Ingen vanlig app-loader, migrering,
scanner, provider-handel eller initialisering kjøres. Den SQL-koblingen er
READ ONLY / REPEATABLE READ med tidsgrenser. Store JSON-er leses som begrensede
native UTF8-byteverdier, aldri `row_to_json`, JSONB-casting eller hele Python-
objekter for modellhistorikken. Små valgte felt deserialiseres, og handelsrader
aggregeres med eksplisitt skille mellom manglende og dokumentert null kostnad.

Kun en ny privat bevismappe på PC-en opprettes. Ingen filer skrives på Render,
og ingen arkivering, restore, prepare, aktivering eller opprydding startes.
Resultatfilen heter `cost-and-draft-evidence.json`; terminalen viser nøyaktig sti.
Del bare den filen. Originalarkiv, DB, nøkler og historikk bevares.

## Verifikasjon av den nye kontrollen

Isolert PostgreSQL16-fixture bekreftet ekte READ ONLY, native UTF8, lesing av
lagret sats 17 bp fremfor kodefallback 10, journalaggregering per dokumentert
enhet, forskjell på manglende kostnad og eksplisitt 0, og at ingen kildedata
endres. En stor Unicode-historikk ble hoppet over uten full JSON-deserialisering;
et ukjent konfigurasjonsfelt med en sensitiv kanariverdi ble ikke eksportert.
Uendrede core-rutiner verifiserte tre ekte fixture-DRAFT-dokumenter og avviste
endret kontantsaldo. Bilags-/cipher-hashkontroll avviste ugyldig Windows-kopibevis.
Windows-/arkivmarkører var syntetiske i akkurat denne testen, og er ikke
påstått som en ny faktisk produksjonsrestore.

En separat minneprøve hoppet over 155 MiB UTF8-historikk med astraltegn innen
768 MiB adressegrense og fant riktig top-level konfigurasjon. Offisiell
PowerShell-parser, faktisk innebygd kildehash og eksakt .NET GZip → shell-
dekoding bestod (kommandoen er under 24 000 tegn). Minneprøvens topp-RSS
var 329 016 KiB; dette er målt i isolert test, ikke produksjon. Tidligere verifisert konservativ SSH-
transport gjenbrukes; den gjentar bare dokumenterte feil før innlogging.

Ferskt faktisk database-/bilagsresultat fra den nye kontrollen gjenstår. Det
føres inn i rapporten når resultatfilen foreligger. Ingen personlig godkjenning
bes om før de gjenstående modellvalgene kan presenteres konkret.
