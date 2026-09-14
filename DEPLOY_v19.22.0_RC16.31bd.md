# Deploy v19.22.0-rc16.31bd

1. Deploy den rene DELTA-pakken over RC16.31bc på både web og `aksje-app-report-scheduler`, eller FULL ved komplett erstatning.
2. Kontroller at begge tjenester viser `v19.22.0-rc16.31bd` og samme commit.
3. Behold på scheduler: `STORAGE_RETENTION_APPLY=True`, `STORAGE_RETENTION_BATCH_SIZE=20`, `STORAGE_RETENTION_TIME_BUDGET_SECONDS=45`.
4. Neste cron skal vise retention `PARTIAL` eller `COMPLETED`, `apply_requested=true`, `apply_enabled=true` og et positivt `deleted_this_batch` så lenge backlog finnes.
5. Ved PostgreSQL recovery skal Paper-porteføljen ikke logge lokal fallback. Arbeid skal i stedet utsettes/gjenopptas fail-closed.
6. Produksjonsaksept krever én frisk ordinær scanner-syklus og komplett 08:00/14:00/22:00-sekvens med PDF, JSON, databasepersistens og Pushover uten dubletter eller uavklarte recovery-receipts.
