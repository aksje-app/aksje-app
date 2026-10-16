# Faktiske individuelle Shadow-utfall hentet fra Render – 2026-10-16

Kilde: read-only SQL, Render Postgres `aksje_paper_db`, `app_kv_store` → `controlled_learning/observation_cohorts.json`, array `horizon_measurements`. 91 registrerte observasjoner, entry dates 2026-08-31 til 2026-10-06. **Alle har status ACTIVE selv når målte delhorisonter foreligger.**

| Horisont dager | Ferdige målinger | Gj.snitt avkastning | Gj.snitt meravkastning vs. indeks | Positive |
|---|---:|---:|---:|---:|
| 1 | 91 | -0.804 % | -0.291 pp | 28 |
| 5 | 91 | +0.115 % | +0.361 pp | 45 |
| 20 | 90 | -0.373 % | +0.557 pp | 34 |

**Interpretation:** `status=ACTIVE` and aggregate `matured_count=0` are whole-observation / final-horizon lifecycle gates, **not** proof that short-horizon measurements do not exist. Therefore UI/acceptance must show `measured per horizon` and `fully matured lifecycle` separately. This cohort is separate from the historical baseline's 1,382 signal measurements; don't mix their results.

SQL to reproduce:
```sql
SELECT h.key horizon, count(*) n,
 round(avg((h.value->>'return_pct')::numeric),3) avg_return,
 round(avg((h.value->>'excess_return_pct')::numeric),3) avg_excess,
 count(*) filter (where (h.value->>'return_pct')::numeric>0) wins
FROM app_kv_store,
 lateral jsonb_array_elements(payload::jsonb) v,
 lateral jsonb_each(v->'horizon_measurements') h
WHERE name='controlled_learning/observation_cohorts.json'
GROUP BY h.key ORDER BY h.key::int;
```

These are real **persisted** observed metrics but have not been independently re-priced or assessed for survivorship/selection bias, corporate actions, or transaction costs. They cannot justify production strategy change.
