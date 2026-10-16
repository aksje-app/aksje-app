# Roadmap fase 1 – læringsrevisjon (foreløpig)
Dato: 2026-10-15. Kilde: lesetilgang til Render Postgres `app_kv_store` / `controlled_learning/weekly_reports.json` og `controlled_learning/forward/*.json`. Ingen produksjonsparametere endret.

## Reviderte ukesrapporter
| Uke | Valgt utvalg N | Treffprosent | Valgt minus matchet kontroll (prosentpoeng) | Modne | Produksjonsparametere endret |
| --- | ---: | ---: | ---: | ---: | --- |
| W35–W39 | Ikke tilstrekkelig målt | – | – | 0 | Nei |
| W40 | 19 | 26,32 % | −1,7858 | 0 | Nei |
| W41 | 29 | 37,93 % | +0,8225 | 0 | Nei |

Sammenligningene kommer fra hver ukes lagrede rapport og må ikke behandles som uavhengige eller som realiserte porteføljehandler. Rapportene kan dele observasjoner. Kausale årsaker er ikke etablert.

## Revisjonsfunn
1. W41 viser teknisk kontroll PASS mens strategiklarhet er NOT_VALIDATED; kvalitetsporten mangler modning, komplett benchmarkdekning, positiv gjennomsnittlig meravkastning og profit factor >= 1,10.
2. Forward `AUTONOMY` og `SUPER_PORTFOLIO` registrerte begge `ACTIVE_SHADOW`, fire observerte handelsdager og `production_approval_available=false` ved kontroll.
3. De syv ukesrapportene viser `production_parameters_changed=false`; dette dokumenterer ikke alle tidligere produksjonsendringer i hele repositoriet.
4. W41 inneholder foreløpige faktorkorrelasjoner med 20-dagers meravkastning (N=89): `portfolio_fit_score` −0,4453, `validation_score` +0,3453, `fundamental_score` −0,2858. Ingen kausal konklusjon eller justering av vekter er forsvarlig uten kontroll for sektor/marked og utvalgseffekter.
5. W41 rapporterer oversette kandidater som DELL, CRWD og WWI.OL. Neste tiltak er å sammenligne originale avvisningsårsaker og tidspunkter med samtidige markedsdata, ikke anta at de var kjøpbare gevinster.

## Tiltak med prioritet
- A: Undersøk avvisningsårsaker og signaltidsstempler for oversette kandidater; ingen etterpåklokskap.
- B: Lag parvis, identisk og fremoverrettet evaluering av endret `portfolio_fit_score` og `validation_score` mot gjeldende regler. Mål nettoavkastning, treffprosent, tap, drawdown og turnover.
- C: Revider eventuelle produksjonsendringer mot commit/parameter-diff/godkjenning og resultat etter endring. Mangel på bevis må stå som UKJENT, ikke null.
- D: Før hvert godkjent forslag via eksplisitt status: funnet → hypotesetest → anbefaling → godkjenning → implementering → kontroll.
- E: Diagnose-ZIP skal skille teknisk PASS fra strategi NOT_VALIDATED; ikke utlede faktisk lønnsomhet av kjørestatus.

Arbeidsstatus: Fase 1 pågår, fase 2 tapsårsaker gjenstår. Ingen automatiske handler, DB-skriving eller ekstra markedshenting i denne revisjonen.

## Opprinnelige beslutninger for oversette kandidater
Kilde: lagrede `decision_snapshot` i `controlled_learning/observation_cohorts.json` – kontrollert 2026-10-15.

| Aksje | Handling | Utfall | Risiko-score | Datagrunnlag gyldig for beslutning | Tolking |
|---|---|---|---:|---|---|
| DELL | SKIP | AUTOMATISK_AVVIST | 73,96 | Ja | Undersøk hvilke risikoregler som utløste avvisning; ikke anta at terskelen er feil. |
| CRWD | SKIP | AUTOMATISK_AVVIST | 73,62 | Nei | Datakvalitet og avvisningsgrunn må undersøkes uavhengig. |
| WWI.OL | HOLD | OVERVÅKES_AUTOMATISK | 23,90 | Ja | Ikke automatisk avvist; undersøk manglende opptrapping fra overvåking til kjøpskandidat. |

Alle tre er i `MATCHED_CONTROL` i den lagrede læringskohorten. Ingen av disse observasjonene dokumenterer hypotetisk ordre, kostnader eller realisert avkastning. Valider historiske kurs-/beslutningstidspunkter før testing av endrede terskler.

## Fase 2 – første tapsdiagnose, Autonomi
Kilde: `autonomous_portfolio/trades.json` i Render `app_kv_store`, lesekontroll 2026-10-15. Gjelder registrerte SELL-hendelser; ingen syntetiske handler eller nye markedsdata.

| Salgskategori basert på `reason` | Antall | Tapshandler | Sum registrert P&L |
|---|---:|---:|---:|
| STOP_LOSS | 11 | 11 | −11 469,05 |
| KAPITAL_BUNDET | 11 | 6 | −101,61 |
| FALL_FRA_TOPP | 4 | 3 | +666,59 |
| GEVINSTSIKRING | 8 | 2 | +2 575,39 |
| ANNET | 4 | 0 | +4 861,26 |

Kategoriseringen er tekstbasert og må ikke tas som kausalt bevis. Undersøk opprinnelig entry-score, kursutvikling før kjøp, alder, forventet volatilitet, posisjonsstørrelse og feil eller forsinkede kurser for de elleve stop-loss-salgene. **Ikke fjern stop-loss automatisk.** Tallene må avstemmes mot periodisering og nettoresultat før økonomisk konklusjon. 
