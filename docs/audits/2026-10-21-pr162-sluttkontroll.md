# Sluttkontroll av PR #162

Kontrollgrunnlag: PR-hode `b9c7a04`, bestått Release gate på dette hodet, begge opplastede diagnosearkiver og nye isolerte regresjonstester. Nye rettinger legges i samme PR. Ingen produksjonstilgang, merge eller deploy er brukt.

## Bekreftet korrekt

### Overgang fra gammelt regnskap

`tests/fixtures/super_portfolio_20261021_opening.json` kopierer de relevante faktiske feltene fra `current_positions.json` og siste `recent_history.json` i tickerdiagnosen. Arkivets SHA-256 og kildefiler følger fixturen. De vedlagte dokumentene behandles som data.

Begge innganger, full vurdering og stoppovervåking, er kjørt uten handler med uendrede kurser. Resultatet er:

| Felt | Før / etter |
| --- | --- |
| NAV | 973 526,92 / 973 526,92 NOK |
| Beholdninger | HEXA-B.ST, AKVA.OL, MEDI.OL, AKRBP.OL, uendret |
| Målvekter | 15 % hver, uendret |
| Modellverdi per posisjon | 146 029,038 NOK ved inngående oppgjør |
| Beregnede inngående kontanter | 389 410,768 NOK |
| Nye handler / kostnader | 0 / 0 |

En andre kjøring bevarer kontanter, NAV og inngående regnskapsgrunnlag. PostgreSQL-testen legger den gamle dokumentformen uten `_revision`/`accounting_schema` i eksisterende tabeller, initialiserer oppgjøret og leser det med ny lagringsinstans. Det kreves ingen konstruerte transaksjoner.

Begrensning: ZIP-ene inneholder ikke komplett `state.json`, separat kontantdokument eller full konfigurasjon. Startkapital utledes fra eksportert NAV og avkastning; øvrig kjøringskonfigurasjon bruker applikasjonens standarder. Testen er en kopi av eksporterte produksjonsfelt, ikke en verifisert full produksjonsbackup. Kontantbeløpet ovenfor er modellens nye restberegning, ikke en bankbekreftet historisk kontantbeholdning.

### Kontanter, NAV og samtidighet

Kjøp, tilleggskjøp, reduksjon, fullt salg og kombinasjoner testes med uavhengig løpende kontroll av kontanter, beholdningsverdi, kostnader og NAV etter hver journalrad. En fullinvestert utskifting med kjøp først i beslutningslisten fungerer nå. Antall modellenheter videreføres gjennom senere markeringer.

Eksisterende og nye PostgreSQL-tester verifiserer gjenstart, samme jobb samtidig, konkurrerende forskjellige revisjoner og feil etter journal- og tilstandsskriving. Samme jobb gir én journalføring; feil før commit ruller alt tilbake. Worker-testene verifiserer at feil etter commit og nytt forsøk sluttfører status uten ny skanning eller nye handler. Dette verifiserer implementasjonens gjenforsøk, ikke manuelle inngrep som sletter kvitteringer eller oppretter en annen jobb-ID.

### Stoppovervåking

Testene kjører den faktiske kursinnhentingsfunksjonen og begge kursvalidatorene med kontrollerte femminuttersdata, uten å erstatte validatorene:

- Åpen norsk og amerikansk børs: fersk kurs under stop gir umiddelbart salg også én time etter kjøp.
- Stengt børs/helg: gammel siste børskurs gir ingen handel. En 16 minutter gammel femminutterskurs avvises også under åpen børs.
- Like etter børsslutt: en fortsatt gyldig ti minutter gammel ordinær børskurs kan gi modellsalg. Modellen har ingen separat sperre for stoppsalg utenfor åpningstid; dette er videreført, ikke en meglerbekreftet utførelse etter stengetid.
- Manglende data: posisjonen og siste verdsettingskurs beholdes. Manglende kurs for én aksje blokkerer ikke et dokumentert stoppsalg i en annen.

Kurskontrollenes 15-minutters grense og regler for råkurs/tidsstempel er ikke slakket på. Manglende kurs kan derfor utsette et nødvendig salg til et gyldig kursbevis finnes; testen gir ingen garanti for dataleverandørens tilgjengelighet.

## Nye feil som er rettet i samme PR

1. **Kjøp før finansierende salg.** Beslutningsbyggeren kunne legge kjøp først, slik at et fullinvestert oppgjør feilet på kontanter selv om godkjente salg finansierte kjøpet. `services/super_portfolio_accounting.py:44` gjør opp salg/reduksjoner før kjøp/tilleggskjøp. Kostnadene beholdes, og kjøp kan ikke overtrekke kontanter.
2. **Tilleggskjøp med manglende/gammel kurs.** Utførelsessperren omfattet utgående posisjoner, men ikke økninger av eksisterende posisjoner. `super_portfolio.py:2312` krever gyldig fersk kurs også for disse. Separate tester viser avvisning ved manglende og 16 minutter gammel kurs, samt utførelse ved fersk kurs.
3. **Tapt referanse for holdetid etter tilleggskjøp.** Oppgjøret registrerte ikke siste tilleggstid, og posisjonsbyggeren videreførte ikke feltet. `services/super_portfolio_accounting.py:69` og `super_portfolio.py:2102` registrerer og bevarer `last_added_at`. Ordinært salg kan ikke passere minimumshold ved å bruke eldre opprinnelig inngang; risikostopp er fortsatt uavhengig.
4. **Utilstrekkelig synlig historikk-/valutaforbehold.** Brukerflate, PDF og dekningsrapport oppgir nå eksplisitt at eldre avkastning ikke er fullstendig kontrollert og at valutaregulering mangler. Eksporten har `historical_return_fully_verified: false` og `fx_revaluation: false`.

De to første feilene ble gjenskapt som feilede tester før retting. Risikoterskler, gevinstsikringsgrenser og kandidatrangering er ikke endret.

## Kjente begrensninger

**Valuta:** For NOK-noterte aksjer er prisforholdet direkte sammenlignbart med basisvalutaen NOK, men antall er fortsatt modellenheter. For USD, SEK, DKK og EUR fordeles et NOK-modellbeløp etter målvekt og endres med lokal aksjekurs. Det gjøres ingen konvertering med faktisk valutakurs ved kjøp/salg og ingen løpende FX-omvurdering. En amerikansk aksje med uendret USD-kurs får derfor uendret modellverdi selv om USD/NOK endres. Dette er ikke korrekt verdiutvikling for en faktisk utenlandsk aksjebeholdning i NOK. Tester dokumenterer denne eksisterende begrensningen for alle fem valutaer; PR-en innfører ingen ny valutastrategi eller oppdiktede valutakurser.

**Historikk:** Tidligere tapte BWE-/OMC-salgskurser finnes fortsatt ikke. Ny regnskapsstart etterberegner ikke gammel NAV eller realisert avkastning. Ved overgang uten handler er den nye journalen tom, og dekningsrapporten markerer hullene eksplisitt. Eldre avkastningskurve videreføres som uverifisert modellhistorikk.

**Utførelse:** Femminutters Close og bekreftet neste-sesjonsåpning er simulerte prisgrunnlag. Spread, ordrebok, meglerfyll og valutaveksling er ikke dokumentert. Journalen er varig innenfor beholdt database/backup; fysisk datatap eller administrativ sletting håndteres ikke av jobbkvitteringen.

## Produksjonsovergang på Render

Ingen ny SQL-tabell, DDL-migreringsfil, ekstern avhengighet eller manuell transaksjonsimport kreves. `services/storage_service.py:231` bruker eksisterende `app_kv_store` og `app_jsonl_store`; nye dokumentnøkler/journalrader opprettes ved vanlig kjøring. Inngående modellenheter, restkontanter og regnskapsversjon etableres automatisk ved første oppgjør med tilstrekkelig data. Det skjer ikke nødvendigvis på en stoppsyklus som bare mottar manglende kurser.

For en kontrollert overgang må operatøren:

1. Kontrollere Render sin faktiske deploykobling **før merge**. `render.yaml:4` og `:82` angir `autoDeployTrigger: commit` for web og cron. Et merge kan dermed utløse deploy selv om ingen separat deploykommando kjøres. Slå av automatisk deploy dersom produksjonsovergangen skal godkjennes separat.
2. Ta konsistent databasebackup og kopi av aktuell SP-tilstand, jobber og kvitteringer. Lagre en diagnose før overgangen. Kontroller at web og scheduler bruker samme PostgreSQL og at lokal fallback er deaktivert.
3. Stans/tøm aktive SP-jobber og stopp gamle skrivende scheduler-/worker-/web-prosesser under overgangen. Gamle versjoner kjenner ikke revisjonskontroll og journal; samtidig gammel og ny skriving er ikke trygt. Eksisterende FAILED-jobber med ukjent oppgjør må ikke startes som nye jobber for å omgå verifikasjonen.
4. Start én ny kontrollert skriver, kontroller inngående NAV/vekter og `cash + market_value = NAV`, deretter journal/kvittering og kostnader. Åpne øvrige skrivere først når de kjører samme versjon. Ingen testordre i produksjon er nødvendig for å etablere inngående balanse.
5. Ved eventuell tilbakerulling må både kode og regnskap/journal avstemmes. Gammel kode skal ikke få skrive videre i en ny regnskapstilstand med bokførte nye handler uten en kontrollert gjenopprettingsplan.

Dette er tiltak før produksjonsovergang; ingen av dem er utført her.

## Forhold som fortsatt ikke er verifisert

- Komplett aktuell Render-tilstand, faktisk DB-skjema/rettigheter, backup, aktive jobber og deployinnstillinger er ikke hentet fra produksjon.
- Fullstendig historisk NAV og BWE-/OMC-oppgjør kan ikke etterprøves med de vedlagte dataene.
- Korrekt reell NOK-verdsetting av utenlandske beholdninger er ikke implementert eller bevist.
- Direkte Yahoo-tilgjengelighet og nettleserlayout er ikke verifisert lokalt i denne kontrollen; CI-resultatet for nytt hode rapporteres separat.

## Tester og vurdering

109 målrettede tester, inkludert sluttkontrollen og fem reelle PostgreSQL-tester, består. Hele eksisterende «Quality regression suite» består med 478 tester. Aktiv samling uten eldre versjonsfiler og direkte Yahoo-akseptanse gir 611 beståtte og 7 valgfrie nettlesertester hoppet over. Samlingene overlapper. Python-kompilering, diff-kontroll og fem rapportdelingskontroller består.

**Vurdering:** Koden kan merges som retting av Superporteføljens eksisterende simuleringsmodell når Release gate for det nye hodet er grønn. Kontrollert deploy forutsetter tiltakene ovenfor. PR-en gir ikke grunnlag for å omtale modellen som et fullstendig valuta- og historikkavstemt produksjonsregnskap.
