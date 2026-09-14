# Deploy v19.22.0-rc16.31bb

Deploy the FULL archive to both the Render web service and report scheduler.
No destructive database migration is required. Existing portfolios, trades,
reports, settings, learning observations and re-entry quarantines are retained.

After deployment verify both services display `v19.22.0-rc16.31bb` and the same
commit. The next completed scheduled report must include `Analyse mot
kjøpsklarhet`, separate analytical and buy-ready lists, and a precise learning
health explanation. Pushover must open the durable report page on mobile.

Candidate-passport storage is bounded to 500 tickers and 120 events per ticker.
Existing controlled-learning retention remains bounded. Deploy initially with
`STORAGE_RETENTION_APPLY=false`. After one healthy ordinary cron, enable it on
the scheduler with `STORAGE_RETENTION_BATCH_SIZE=20` and
`STORAGE_RETENTION_TIME_BUDGET_SECONDS=45`. Confirm the next diagnosis contains
`runtime/STORAGE_RETENTION.json` with `COMPLETED` or `PARTIAL`, database health,
deleted count, pending count and before/after usage.

Production acceptance requires one complete 08:00/14:00/22:00 operating day,
no duplicate authoritative reports, no unexplained restart and no database
growth anomaly.

If PostgreSQL reports recovery, verify `DEFERRED_DATABASE`, zero analysis/trade
work and a later successful replay receipt. Keep the previous deploy available
for rollback until the first complete operating day has passed.
