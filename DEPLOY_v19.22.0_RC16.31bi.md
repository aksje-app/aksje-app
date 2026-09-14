# Deploy v19.22.0-rc16.31bi

Deploy the clean DELTA to the same GitHub branch used by the Render web service and report scheduler, then verify both services report `v19.22.0-rc16.31bi` on the same commit.

No new required environment variables are needed. Keep the existing memory settings and `PRODUCTION_NORWAY_ONLY=true` during production stabilisation.

After deploy, allow one ordinary cron attempt. If it succeeds, capture the scheduler status and peak memory. If Render still reports `Out of memory (used over 2Gi)`, immediately create a diagnostic bundle. The bundle must contain `runtime/OOM_BREADCRUMB_LATEST.json`; its `stage` field identifies the last expensive phase entered before the kill.
