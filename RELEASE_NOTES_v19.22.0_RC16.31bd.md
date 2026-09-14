# v19.22.0-rc16.31bd — Production Closure

Denne versjonen er en ren stabiliseringsleveranse. Ingen kjøpsterskler, risikogrenser, porteføljeregler eller strategi-score er endret.

## Rettet
- Storage-retensjon reagerer umiddelbart på `STORAGE_RETENTION_APPLY=True`; den venter ikke lenger opptil ett døgn etter overgang fra DRY_RUN.
- Retensjonsdiagnostikk viser rå Render-verdi, normalisert verdi, parset boolsk verdi, effektiv verdi og eventuell blokkårsak.
- Retensjon er fortsatt begrenset av batch og tidsbudsjett, og beskyttede trade-/decision-/audit-/learning-data slettes ikke.
- Paper-porteføljen kan ikke lenger falle tilbake til lokal JSON når PostgreSQL er autoritativ og midlertidig utilgjengelig. Produksjon feiler lukket og lar neste cron gjenoppta arbeidet.
- Scheduler-status skiller analysekrasj fra midlertidig lagringsfeil etter ferdig tickeranalyse.
- Sluttstatus er sannferdig: maintenance-feil gir `COMPLETED_WITH_WARNINGS`, lagringsavbrudd etter full analyse gir `DEGRADED_STORAGE`, og reelle kritiske feil gir `FAILED`.
- Scheduler-state bruker lengre kontrollert retry før lokal recovery-receipt.
- Diagnosepakken inkluderer gjeldende retention-konfigurasjon ved siden av sist lagrede retention-state.
- Hver cron publiserer et kompakt `production_closure`-bevis med eksplisitte blokkere.
