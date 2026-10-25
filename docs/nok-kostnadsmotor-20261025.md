# NOK-handelsmotor: handelsavhengige kostnader og kontrollert oppgjør

Denne endringen retter beregningen i den nye NOK-rutingen. Den oppretter ikke
kontoer eller arkiver, migrerer ikke journaler og innfører ingen nye
produksjonsforutsetninger for Paper Trading eller Autonomi. Ingen aktivering,
merge eller deploy er utført. Godkjenning B må fortsatt gis personlig og bindes
til de eksakte kontoene, forutsetningene og signerte forespørslene.

## Grunnlaget som allerede er kontrollert

[Kostnadsrevisjonen med kildehenvisninger og faktiske kvitteringer](https://github.com/aksje-app/aksje-app/blob/d7731082c7bf6a5ffbbbb1c04a92e7ecb5bd9cab/docs/kostnadsrevisjon-20261025/RAPPORT.md)
ligger til grunn. Den beskriver den deployede versjonen
`2559bcfc1a1da11d3ce9406322410bd02bebaa62`, før denne rettingen.

Den brukerutførte READ ONLY-kontrollen 25. oktober 2026 kl. 02:57:57 norsk tid
bekreftet `production`, `postgres`, `aksje-app-production-nok-v1` og perioden
`nok-20261025T012118Z`. Paper, Autonomi og Superporteføljen var DRAFT med
henholdsvis 100 000, 500 000 og 1 000 000 NOK, null handler/posisjoner, ingen
aktiveringsgodkjenninger og ingen valgte ruter. Arkivets kontrollsum, bevarte
restore-filer og fysiske restorebevis for alle 12 tabeller bestod kontrollen.

Kvitteringens kanoniske SHA256:
`b853945a5ff7f90f160cee29bdef1df36e610b3cc4224fddee4c6251aed4dac3`.
Eksisterende restore-review SHA256:
`3118134d55f84c0935ab4d22704117db160bd730f46636ab5488547290f1e90a`.
Ingen rå private bilag eller nøkler legges i PR-en. Denne utviklingen bruker
bare isolerte testkontoer og krever ingen ny operatørkontroll av disse bevisene.

## Beregning per faktisk utførelse

`services/trading_costs.py` støtter både dokumenterte faste NOK-beløp og
`NOK_COST_POLICY_V2`. Hver V2-komponent har egen `source_ref` og minst ett
uttrykkelig term: `fixed_nok`, `rate_bps` eller `rate_pct`. Fast beløp kan
kombineres med én proporsjonal sats; prosent og basispunkter kan ikke angis
samtidig for samme komponent. 10 bp = 0,10 % = 0,001 av handelsverdien.
Ukjente felt, negative/ikke-endelige verdier og boolske beløp avvises.

For kjøp/salg brukes:

- Utførelseskurs = dokumentert referansekurs × (1 ± dokumentert slippage).
- Brutto NOK = faktisk antall × utførelseskurs i instrumentvaluta × NOK per
  valutaenhet fra det daterte FX-beviset.
- Hver kostnad = dokumentert fast NOK-beløp + dokumentert sats × brutto NOK.
- Kjøp trekker brutto og gebyr fra kontanter; begge inngår i NOK-kostprisen.
- Delsalg fordeler beholdningens dokumenterte NOK-kostpris proporsjonalt.
  Realisert resultat = bruttoproveny − salgsgebyr − fordelt kostpris.
- NAV verdsetter gjenværende beholdning til den observerte markedskursen og
  dokumentert NOK-kurs. Slippage påvirker derfor resultatet umiddelbart,
  uten et ekstra gebyrtrekk.

Kjøpsantallet beregnes innenfor budsjettet etter både faste og proporsjonale
kostnader, FX og eventuell slippage, og rundes ned til fire desimaler.
En siste kontroll følger hovedbokens faktiske kontantsammenligning ved
flyttallsgrenser. Kostnader beregnes på nytt fra det faktiske antallet ved
oppgjøret; et estimert beløp fra før ordrestørrelsen brukes ikke som fasit.

Journalen beholder policy, referansekurs, side og FX-grunnlag i
`cost_calculation`. Den samme rene beregningen gjentas ved journalverifikasjon
og replay, også etter utbytte/andre økonomiske hendelser. Endrede satser,
slippage, valutagrunnlag eller komponenter blir avvist selv om noen regner om
den ytre hashkjeden.

## Kostnadskategorier og valuta

En spesifisert modell bruker alle tre dokumenterte komponenter:
`brokerage_nok`, `fx_cost_nok`, `other_nok`.

Superporteføljens eksisterende, ufordelte modell bruker i stedet
`model_transaction_cost_nok` og `fx_cost_nok`. Samlet modellkostnad kan ikke
kombineres med kurtasje/øvrige kostnader som et ekstra identisk fradrag.
Rapporteringen viser samlet modellkostnad separat og markerer at full
kostnadsdeling mangler. En ukjent oppdeling blir ikke rapportert som null
kurtasje eller null øvrige kostnader.

**Uavklart FX-komponent (`None`) er ikke gyldig grunnlag for signering eller
handel.** Et uttrykkelig dokumentert nullbeløp er mulig, men opprettes aldri
som standard. V2s FX-komponent gjelder valutakonvertering; når instrumentet
allerede er i NOK finnes ingen slik konvertering. Journalen angir da
`NO_CURRENCY_CONVERSION`. Dette er ikke en antakelse om gratis utenlandsk valuta.
Utenlandske instrumenter krever fortsatt fersk, kildebelagt NOK-kurs og en
uttrykkelig kostnadsregel. FX-kurs og valutakostnad er separate størrelser.

Slippage er valgfri, men kan bare innføres gjennom en uttrykkelig dokumentert
og signert policy. Uten slippageregel endres ikke den dokumenterte prisen.
Den kan ikke legges som en ekstra kostnadskomponent med et ukjent feltnavn.

## De tre modellene

| Konto | Eksisterende dokumentasjon | Hva rettingen innfører |
| --- | --- | --- |
| Paper Trading | Ingen dokumenterte produksjonskostnader i de undersøkte reglene/journalmetadataene. 5 bp kurtasje / 10 bp slippage finnes i backtesting | Beregningsstøtte, ingen satser eller ny policy som standard. Backtestverdiene forblir forslag inntil særskilt godkjenning |
| Autonomi | 20 bp er læringssensitivitet og beslutningsterskel, ikke dokumentert kontanttrekk i de 77 undersøkte handlene | Beregningsstøtte, ingen automatisk overføring av 20 bp til hovedboken |
| Superporteføljen | Lagret og journalført `transaction_cost_bps=10`; tilgjengelig journal kostnadsførte 144,146144 i modellens NOK-enhet | Nye godkjenningsforespørsler krever nøyaktig konfigurert sats som proporsjonal samlet modellkostnad, ikke et fast NOK-beløp. Den eksisterende satsen er 10 bp |

`super_portfolio_proposal` lager bare et forslag fra gjeldende innstillinger.
Ukjent FX beholdes som `None`, slik at forslaget ikke kan signeres/brukes før
grunnlaget er avklart. Ingen faktisk produksjonspolicy skrives av helperen.
Rutingen bruker allerede NOK-sessionens oppgjør fremfor det eldre oppgjøret;
10 bp belastes der én gang. Turnover-rapporten summerer de faktisk journalførte
kostnadene og trekker ikke et nytt estimat fra NAV.

Gamle faste NOK-policyer og journalposter beholder sin tidligere regnskapssemantikk
og er fortsatt verifiserbare. Nye Superportefølje-forespørsler må derimot følge den
proporsjonale modellen. Ingen DRAFT må slettes eller opprettes på nytt.

## Godkjenning, atomisitet og bevaring

Kostnadspolicyen inngår i den eksisterende signerte forespørselen. Den valideres
ved forespørsel og aktivering og sammenlignes med instrumentbeviset under samme
transaksjonslås som oppgjøret. Endret kostnadspolicy blir ikke en ny implisitt
modellforutsetning. Superporteføljens godkjente sats kontrolleres også mot de
kanoniske innstillingene ved hver produksjonskjøring.

En feil før commit ruller tilbake hele jobben, inkludert markering, gebyr,
beholdning og strategiresultat. Samme jobb-ID og innhold returnerer eksisterende
kvittering; endret innhold avvises. Samtidig dobbelt levering gir én bokføring.
Dette testes med faktiske PostgreSQL-transaksjoner, ikke bare minneobjekter.

Det er ingen import-/oppstartskrok for aktivering eller migrering. Gamle tap,
modellhistorikk, læringsnøkler, Superfond og de to andre kontoene skrives ikke
av et oppgjør for én konto. Ingen produksjonsdatabase eller ekstern tjeneste er
brukt av testene. Oppslag/signering i testene bruker syntetiske nøkler og et
midlertidig lokalt PostgreSQL-miljø.

## Verifikasjon

**300 tester bestod** i én samlet kjøring mot midlertidig lokal PostgreSQL16
(90,73 sekunder). Ingen tester var hoppet over i denne kjøringen. Omfang:

- `test_trading_costs`, `test_production_restart`, `test_restart_trading`.
- `test_portfolio_accounting`, `test_economic_ledger`, `test_economic_events`.
- `test_simulation_restart`, `test_revision_trade_postgres`.
- `test_superfund_accounting`, `test_superfund_postgres`, `test_superfund_v1`.
- `test_production_reconciliation`, `test_restart_startup_guards`,
  `test_autonomy_pending_restart_20261012`.

Etter siste vern mot bruk av en NOK-policy i en hovedbok med annen basisvaluta
bestod **130 fokuserte tester** (2,94 sekunder). Seks PostgreSQL-tilfeller ble
hoppet over bare i denne siste kjøringen uten DB-miljøvariabel; de samme
integrasjonstilfellene inngikk i den fulle PostgreSQL-kjøringen over. Tallene
overlapper og skal ikke summeres som unike tester.

Testene dekker prosent/bp/faste beløp, USD/NOK og NOK-identitet, slippage på
kjøp/salg og umiddelbar NAV, budsjettrunding, delsalg og historisk NOK-kostpris,
replay etter utbytte, ugyldige/manglende FX-/kostnadsvilkår, manipulert policy og
hashkjede, overflyt, feil basisvaluta, rollback, samtidig dobbelt levering,
produksjonssignaturer i et lokalt testmiljø, fysisk syntetisk arkiv/restore og
uendret gammel historikk/læring/Superfond. De ordinære Paper-, Autonomi- og
Superporteføljemotorene brukes i testene; det er ikke bare en separat kalkulator.

`python -m compileall -q services tests` og `git diff --check` bestod.
De lokale testprosessene fikk ingen produksjons-DSN, Render-API-nøkkel eller
GitHub-token. Faktiske private produksjonsbilag ble ikke lastet inn i testene.
PostgreSQL16-testen er ikke en påstand om ny produksjons-/Windows18-kjøring.

Fortsatt før faktisk B: dokumenterte kostnadsvalg/FX, personlige signerte grants,
ferske strategi-/pris-/FX-bevis og den allerede validerte native verifikasjonsbanen
for store produksjonsrader. Den deployede gamle `row_to_json`-banen er ikke
produksjonsgodkjent av disse små, isolerte regnskapstestene. Denne PR-en retter
kostnads-/oppgjørsbanen og innfører ingen ny arkiv-/restoreprosedyre eller
produksjonsaktivering.

## Rettelse av nettlesertestens miljø i PR #168

Release gate-run `40155049112`, jobb `121054533700`, feilet i begge størrelser
av `test_documented_model_dividend_and_cashflow_report`. Testens syntetiske,
lokale modelloppsett brukte `scope='test'`, men manglet eksplisitt testmiljø.
Når `APP_ENVIRONMENT` mangler, skal aktiveringssperren behandle miljøet som
produksjon. Sperren var allerede slik i basecommiten og er ikke endret av PR-en.

Feilen ble reprodusert lokalt i begge tilfeller før retting. Testen setter nå
`APP_ENVIRONMENT='test'` med funksjonsavgrenset `monkeypatch`, som automatisk
restaurerer miljøet etter testen. Lagringen må fortsatt være lokal i den isolerte
`/tmp/aksje-browser-*`-mappen; ingen produksjonssignatur eller testunntak i
produksjonskoden er lagt til. Nettlesertesten for restart-rapporter bruker allerede samme uttrykkelige testmiljø.

Begge tidligere feiltilfeller bestod i ekte Chromium (1280/375). Regnskaps- og
oppstartstestene bestod: **59 tester mot lokal PostgreSQL, ingen hoppet over**.
Negativkontrollen omfatter nå både eksplisitt produksjonsmiljø og manglende
miljøvariabel; begge må avvise usignert aktivering uten å endre kontoen.
Full nettleserkjøring avdekket også en separat ventefeil: 81 bestod, mens
Superporteføljens desktop-rapport fantes i DOM-en, men var skjult i ekspanderen
etter Streamlit-rerender. Testen ventet tidligere 300 ms og kunne lese den gamle
sidens idle-/åpen-status. Den venter nå på at den forespurte rapporten faktisk er
lagt i DOM-en før panelet kontrolleres og åpnes; kravene til synlig innhold,
verifisert regnskap og alle nedlastinger er uendret.

Etter denne synkroniseringsrettingen bestod **alle 8 målrettede nettlesertilfeller**
(utbytte/kapitalflyt og restart-rapporter for alle familier, begge bredder),
uten hoppede tester. Ingen retry eller økt timeout er lagt til. Hele
Release gate-steget kjøres på nytt ved push til den eksisterende PR-grenen;
resultatet fra denne CI-kjøringen må fortsatt avventes før merge/deploy.
