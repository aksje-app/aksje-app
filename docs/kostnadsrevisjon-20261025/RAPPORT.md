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

**Faktisk READ ONLY-produksjonskontroll er nå fullført.** Brukeren kjørte den
publiserte kontrollen fra sin eksisterende Windows-/Render-tilgang. Den opplastede
`cost-and-draft-evidence.json` viser kontrolltid **25. oktober 2026 kl. 02:57:57
norsk tid (01:57:57 UTC)**, miljø `production`, backend `postgres`, tjeneste
`srv-d7obt5e47okc739susgg`, installasjon `aksje-app-production-nok-v1`, database
`aksje_paper_db`, PostgreSQL 18.4 og `transaction_read_only=on`.
Alle 24 deployede kildefilhashene stemte med den gjennomgåtte produksjonsversjonen.

Filens kanoniske `evidence_sha256` er kontrollert på nytt etter opplasting:
`b853945a5ff7f90f160cee29bdef1df36e610b3cc4224fddee4c6251aed4dac3`.
Den opplastede filens byte-SHA256 er
`3366dad5ee893a906c76d18fd3d390a6b02bf02bb7a4728d3655f9d64714d331`.
Hashene viser konsistens med den returnerte kvitteringen; dette er ikke en ekstern
meglerattest eller en digitalt signert tillatelse til aktivering.

## Faktiske lagrede produksjonsverdier og journalbevis

| Konto | Lagrede kostnadsinnstillinger | Faktisk undersøkt journal | Konklusjon |
| --- | --- | --- | --- |
| Paper | Verken `trading_rules:id=1` eller `settings/trading_rules.json` inneholder de undersøkte kostnadsfeltene. Ingen legacy-regelfil ble funnet | 247 handler: 239 uten `evidence_metadata`, 8 med metadata men uten eksplisitt gebyr/kostnadsbeløp | Ingen dokumentert kurtasje-/FX-sats i disse kildene; ikke dokumentert nullkostnad |
| Autonomi | Parametere og portefølje finnes i PostgreSQL; ingen av de undersøkte kostnadsfeltene er lagret | 77 handler; alle mangler eksplisitt gebyr/kostnadsbeløp | 0,20 % er ikke påvist som kontanttrekk; kodefallbacken for erstatningsbeslutning står, og læringsreplayets 20 bp er en separat sensitivitet |
| Superporteføljen | **`config.transaction_cost_bps=10.0`** | Én tilgjengelig native journalrad: **10 bp**, kostnad **144,146144**, enhet merket **NOK** | Satsen er faktisk lagret og brukt i den tilgjengelige oppgjørsjournalen; kostnaden er ikke bare et rapportestimat |

Superporteføljens siste `turnover_costs` viser 0 omsatt verdi / 0 estimert kostnad,
og `last_portfolio_transaction_cost=0`. Dette er et annet tids-/hendelsesgrunnlag
enn den bevarte historiske journalraden på 144,146144. Null i siste oppdatering
opphever ikke den historiske kostnaden. Den ene journalraden må heller ikke
presenteres som full rekonstruert livstidshistorikk eller bevis for ekte aksje-
eller valutaregnskap i eldre `MODEL_PRICE_RATIO_UNITS`.

Ingen av de undersøkte journalene har en eksplisitt separat `fx_cost_nok` eller
slippage-verdi. Superporteføljens kostnad er ikke fordelt mellom
`brokerage_nok`, `fx_cost_nok` og `other_nok`; disse feltene er **null/mangler**
i beviset, ikke dokumenterte 0. Full parameter-/modellhistorikk er ikke
omskrevet eller deserialisert for å produsere disse opplysningene.

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

**Lagret konfigurasjon og faktiske journalrater går foran kodefallback.** Den utførte
kontrollen leste `super_portfolio/state.json` og hele den tilgjengelige native
`super_portfolio/transactions.jsonl` med avgrenset minnebruk. Den rapporterte
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
| Paper, 100 000 NOK | Faktisk gjennomgåtte innstillinger/journal har ingen kostnadspolicy. Backtesting dokumenterer 5 bp kurtasje og 10 bp slippage | Et konkret alternativ er **5 bp kurtasje og 10 bp simulert slippage**, eksplisitt merket som innføring av eksisterende backtestforutsetninger i en ny Paper-modell. Dette er ikke eksisterende produksjonskostnader | Krever særskilt godkjenning av modellendringen og korrekt fill-implementasjon; FX er fortsatt udokumentert, ikke 0 |
| Autonomi, 500 000 NOK | 77 handler uten gebyrbeløp; kode dokumenterer 20 bp læringssensitivitet og beslutningsterskel | Behold disse forutsetningene der de allerede brukes. Et konkret alternativ for ny kostnadsført simulering er **20 bp samlet modellkostnad av omsatt brutto NOK**, med kilde til læringsmodellen, ikke kalt faktisk kurtasje | Nytt kontanttrekk krever særskilt godkjenning. Fordeling på kurtasje/FX og om 20 bp skal dekke FX er ikke dokumentert; ingen dobbelt belastning eller antatt null |
| Superporteføljen, 1 000 000 NOK | Bekreftet lagret og journalført **10 bp** | Viderefør **10 bp = 0,001 × brutto NOK per kjøp/salg**, merket samlet simulert transaksjonskostnad | Prosentberegning må støttes riktig i NOK-rutingen. Kostnadsdeling/FX er fortsatt udokumentert; ikke legg til Superfonds 25 bp eller et ekstra turnover-trekk |

Eksempel på enheten i Superporteføljens bekreftede lagrede sats: en dokumentert
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

Den senere, faktiske READ ONLY-kvitteringen er nå avstemt mot denne sluttfilen:
`final_receipt_sha256` er nøyaktig samme filhash. Periode, arkiv-ID og
restore-reviewhash er også identiske mellom begge opplastede kvitteringer.

**Arkiv og restore, bekreftet av den utførte produksjonskontrollen:**

- Eksisterende forseglet arkiv fikk SHA256 kontrollert på nytt:
  `5e98f9c9d7f43ed477099f17f459ea7680ec61fb04d49f9f504191694b4ce158`.
  Windows-kontrollen sammenlignet samtidig PC-kopiens hash med dette resultatet
  før den viste vellykket fullføring. Det separate lokale Windows-kvitteringsvedlegget
  er ikke lastet opp; sammenligningen følger av den publiserte runnerens sjekk og
  brukerens viste vellykkede kjøring.
- Manifest-SHA256:
  `7295361bf2743bdf6f61e9c742d0932489d6b18dadfba15ee28f45637cf0e28c`.
- `retained_restore_files_sha256_rechecked=true`: bevarte materialiserte filer
  stemte med den opprinnelige restore-reviewen.
- `restore_review_digest_rechecked=true`, `physical_restore_status=RESTORED_AND_VERIFIED`,
  `restore_execution_host=WINDOWS_LOCAL_POSTGRESQL_18`.
- Én databasekilde `db_database_url`, **12 tabeller**, modellfingeravtrykk
  `5b235eb8a1cc31ff1d0157407bd7b8111748b25f6446e7b580460e681c2fdb94`.
  Restore-reviewens tabelltellinger og fingerprintdigest stemte med manifestet.
- Windows-kopi-/dekrypteringskvitteringer forelå og bestod kontrollen.

Dette bekrefter den tidligere fullførte fysiske restoren og de bevarte bilagene;
kontrollen kjørte **ikke** en ny fysisk restore eller en ny full dataskanning av
Windows-restore-databasen. Eksisterende bevis ble kontrollert, ikke erstattet.

**Kontoer, direkte fra produksjonsdatabasen ved 02:57:57 norsk tid:**

| Familie | Status | Kontanter / åpnings-NAV | Posisjoner / handler | Godkjenning | Valgt route |
| --- | --- | --- | --- | --- | --- |
| Paper | DRAFT | 100 000 NOK / 100 000 NOK | 0 / 0 | Ingen (`null`) | Ingen |
| Autonomi | DRAFT | 500 000 NOK / 500 000 NOK | 0 / 0 | Ingen (`null`) | Ingen |
| Superportefølje | DRAFT | 1 000 000 NOK / 1 000 000 NOK | 0 / 0 | Ingen (`null`) | Ingen |

Alle har `fees_paid_nok=0` fordi de nye kontoene ennå har **null handler**.
Dette er en avstemt startsaldo, ikke et valg om fremtidige nullkostnader.
`verify_bundle` bestod for det faktiske databasedokumentet, uten godkjenninger,
produksjonskontroller eller valgte ruter. Åpningshashene er:

- Paper: `5ef8139799bfb339fcb792c25608610e8da2c918e53b2f598a202672915f14f2`.
- Autonomi: `e4856a6bcceee45d81729e9380de898f2b42c5155e1836261a05d9cf1aea395c`.
- Superportefølje: `356033c2efa49ad9800dcbd54b2987ae78468fc32845a09629254a2054c1402c`.

Kvitteringen angir `production_actions_performed=false`, `accounts_activated=false`,
`histories_changed=false`, `learning_changed=false`, `approval_B_ready=false`.
Superfond ble ikke endret eller undersøkt for migrering. Antall observerte
Superfond-nøkler er begrenset til 50 og er ikke oppgitt som totalt antall nøkler.
Ingen rå private bilag, modellpayloads eller nøkler publiseres i Git.

## Hva gjenstår før B?

Kostnadsrevisjonen og den etterspurte verifikasjonen av arkiv, restore og faktiske
DRAFT-kontoer er fullført. **Ingen ny operatørkontroll eller restore er nødvendig
for å fullføre denne rapporten.**

Gjenstående modellvalg er konkrete: om Paper skal innføre de dokumenterte
backtestforutsetningene, og om Autonomiens dokumenterte læringssensitivitet skal
bli et nytt kontanttrekk. Disse er ikke uendret videreføring og må ikke
iverksettes uten særskilt godkjenning. Superporteføljens gjeldende 10 bp trenger
ikke gjettes eller bekreftes av brukeren på nytt.

Separat må valutakostnader og kostnadsdeling ha et dokumentert grunnlag.
Dagens undersøkte data gir ikke en sats eller en tillatelse til å anta 0.
Det er derfor ikke utarbeidet signérbare policies med oppdiktede FX-beløp.
Den deployede faste-NOK-kontrakten må dessuten avklares mot prosentbaserte
modeller før korrekte grants kan utformes.

Før faktisk B kreves i tillegg fullstendige strategiinnstillingssnapshots for
alle familier, faktiske fullførte strategiinput og ferske pris-/FX-bevis, korrekt
verifikasjonsadapter for store rader og eksakt privat signering. Kostnadsbeviset
inneholder Superporteføljens valgte konfigurasjonsfelt, men ikke komplette
Paper-/Autonomi-strategisnapshots. Kvitteringen er **ikke godkjenning B**.

## Utført kontroll – bevart kilde, ikke behov for ny kjøring

Den fullførte kjøringen brukte
[KONTROLLER-KOSTNADER-OG-DRAFT.txt](KONTROLLER-KOSTNADER-OG-DRAFT.txt).
Filen er bevart for sporbarhet; den skal ikke kjøres igjen bare for denne rapporten.
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
Resultatfilen `cost-and-draft-evidence.json` er mottatt og kontrollert.
Originalarkiv, DB, nøkler og historikk bevares.

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

Faktisk produksjonskjøring er nå dokumentert separat ovenfor. Testfixtures
brukes ikke som erstatning for brukerens virkelige kvitteringer. Rapportoppdateringen
endrer bare dokumentasjon; ingen policy er innført, signert eller aktivert.
