# Faktisk læringshistorikk – 16. oktober 2026

Kilde: leseadgang til Render Postgres `aksje_paper_db`. Tallene er fra eksisterende produksjonsrapporter; ingen strategier er endret.

| Horisont | Målinger | Gjennomsnitt | Meravkastning vs. benchmark |
|---|---:|---:|---:|
| 1 dag | 1382 | -0,9556 % | -0,5880 prosentpoeng |
| 5 dager | 1382 | -1,1344 % | -1,0866 prosentpoeng |
| 20 dager | 0 | Ikke vurderbar | Ikke vurderbar |
| 60 dager | 0 | Ikke vurderbar | Ikke vurderbar |

Historisk baseline er merket VERIFISERT, men `analysis.matured_count=0`, samtidig som 1/5-dagersmålinger finnes. Dette er ulike målebegreper og *må merkes separat*, ellers misforstår man resultatet.

Den nyeste driftsrapporten `controlled_learning/acceptance_latest.json` viser `operational_verdict=PASS`, men `strategy_readiness=NOT_VALIDATED`, null modne avsluttede strategiposisjoner og null benchmark-målte posisjoner. Ingen automatisk produksjonsfremming.

Det finnes lagrede historiske observasjoner i `controlled_learning/observation_cohorts.json`, samt `controlled_learning/experiment_frames.json`. Disse skal analyseres etter opptaksdato og kohort; hver rapport må opplyse datadekning, avkastning, benchmark og modenhet uavhengig.

**Begrensning:** Oppsummerte historiske returverdier er ikke ferdig kryssvalidert mot rå kurser, utbytter, publiseringsdatoer eller delistede verdipapirer. Derfor ingen dokumentert økonomisk gevinst og ingen produksjonshandel.

**Videre datainnhenting:** bygg fra eksisterende, faktisk lagrede kandidatbeslutninger og supplementer med historiske justerte dagskurser og dokumenterte publiseringsdatoer. Ikke bruk dagens regnskapstall som historiske.
