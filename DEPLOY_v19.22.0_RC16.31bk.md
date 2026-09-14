# Deploy RC16.31bk

1. Upload/copy the four files from the clean DELTA to the repository root.
2. Commit and let Render deploy web + scheduler from the same commit.
3. Keep `PRODUCTION_NORWAY_ONLY=true` during production stabilization.
4. In Autonom Orchestrator, verify the run panel says `Denne kjøringen bruker: Norge`.
5. Run one manual draft test. Acceptance requires the generated JSON/PDF to report only Norway as active market and no Sweden/USA active candidates/scans.
6. Confirm the scheduler continues to complete with OOM breadcrumbs safely below the 2 GiB limit.

Rollback: redeploy RC16.31bj. To reopen other markets later without code change, set `PRODUCTION_NORWAY_ONLY=false` after Norway production acceptance.
