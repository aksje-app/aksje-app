# Læringsgjennomgang 5. november 2026

Produksjonskilde: Render `aksje-paper-db`, lesetilgang 5. november. Ingen læringshistorikk eller produksjonsparametere endres av denne PR-en.

## Faktisk fremdrift

Siste `acceptance_latest.json` er datert 2. november kl. 07:16 UTC. Operativ PASS dokumenterer regnskap, ikke forbedret strategi. `strategy_readiness=NOT_VALIDATED`, 0 modne strategiposisjoner og 0 benchmark-målte posisjoner. Den bredere læringsporteføljen har 83 åpne og 115 lukkede posisjoner; disse tallene kan ikke brukes som om alle tilhører aktuell valideringskohort.

Historisk baseline fra 5. september inneholder 1382 signaler, med 1382 målinger på både 1 og 5 dager. Gjennomsnittlig avkastning er henholdsvis −0,9556 % og −1,1344 %, meravkastning −0,5880 og −1,0866 prosentpoeng. Ingen 20-/60-dagersmålinger i denne rapporten. `VERIFISERT` er en datarevisjonsstatus. Det dokumenterer ikke positiv meravkastning.

Observasjonsmotorens siste lagrede daglige resultat er 5. november kl. 05:31 UTC: 91 aktive, 1 oppdatert, 0 modne og 0 manglende. Siste ukesrapport er W44 fra 30. oktober, med lagret `notification.sent=true`. Dette er avsenderkvittering, ikke bevis på at telefonen har vist varselet.

Forward-dokumentene er sist oppdatert 29. oktober (Autonomi) og 30. oktober (Superporteføljen). Eksperimentrammer er oppdatert 5. november. De ulike tidsstemplene skal vises separat; en oppdatert samlerapport er ikke bevis på at alle eksperimentene kjører.

## Moduler og bevaring

| Læringsløp | Kode / lagring | Kontroll og avgrensning |
| --- | --- | --- |
| Historiske anbefalinger | `historical_learning.py`, recommendation snapshots | 1/5/20/30/60/90 børsdager; historiske resultater beholdes |
| Utfall og læringskurver fra handler | `ai_learning_foundation.py`, `learning_advisor.py` | Hypoteser og testkø; historisk resultat er ikke automatisk parameterfullmakt |
| Kontrollert parameterlæring | `controlled_parameter_learning.py`, hypoteser/eksperimenter/versjoner/audit | Godkjenning og produksjonsseparasjon beholdes |
| Kohorter, baseline og ukesrapport | `learning_observation_engine.py`, `learning_acceptance.py` | Målehorisont, kohortmodenhet og benchmark må skilles |
| Superporteføljeeksperimenter | `learning_experiments.py` | Kronologisk oppdeling, embargo, begrenset søk og forward-kontroll |
| Historiske rammer og forward | `learning_runtime.py`, `learning_dataset.py` | Uforanderlige checksummede rammer, gap og proveniens; ingen rekonstruert fullstendighet |
| Autonomi og separat læringskonto | `services/autonomy_nok_companion.py`, `services/autonomy_learning_account_service.py` | Handelsjournalen er økonomisk sannhet; læringskontoen er separat |
| Parallelle strategier / oppdagelse | `autonomi_core/discovery_data/controlled_learning.py`, isolert worker | Shadow-resultater og observasjoner er ikke ordinære kjøp |
| Superfond | `superfund_learning.py` | Forward-evidens, historiske eksperimenter og uttrykkelig forslagsgodkjenning |
| Quality/turnaround/shadow | `quality_turnaround_shadow.py`, `quality_v2_shadow_store.py` | Egen historikk og modenhet; skal ikke summeres som Autonomi-resultat |
| Daglig varsling | `services/shadow_daily_guard.py` | Faktisk koblet inn etter læringsvedlikehold i `scheduled_runner.py`; feil isoleres fra handel |
| Alternativ operativ watch | `services/shadow_daily_watch.py` | Biblioteksfunksjon; ikke en ekstra scheduler eller ekstra daglig utsending |

Lagringsinventaret viser 146 `controlled_learning`-dokumenter (148 295 884 byte), samt separate dokumenter for autonom læring, oppdagelse, Quality og Superfond. Dette er lagringsdekning, ikke en prosentvis ferdigstillelse eller valideringsscore.

## Rettelser og grenser

Den hardkodede sluttdatoen 23. oktober fjernes fra begge daglige watch-funksjoner. Eksisterende daglige kvitteringer og deduplisering beholdes. Schedulerens aktive guard varsler nå med historiske målinger, kohortmodenhet, benchmarkdekning og akseptrapportens alder. En akseptrapport eldre enn 48 timer kan ikke gi grønn driftskontroll. Ingen automatisk strategifremming legges til.

`services/learning_progress.py` samler små statusdokumenter og indeksen; den laster ikke hele rammehistorikken. Manglende data forblir ukjent. Nye tester dekker november, vedvarende deduplisering, separate målebegreper og gammel PASS.

Gjenstående produksjonsverifikasjon: ny cron må fullføre etter utrulling, oppdatere læringsrapporten og lagre en faktisk Pushover-avsenderkvittering. Historiske råkurser, publiseringstidspunkter og survivorship er ikke kryssvalidert på nytt i denne endringen. Strategien er fortsatt ikke validert.
