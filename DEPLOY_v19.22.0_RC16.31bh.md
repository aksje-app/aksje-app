# Deploy RC16.31bh

Deploy the CLEAN DELTA to the same GitHub branch used by both the web service and `aksje-app-report-scheduler`, or deploy the FULL package as a complete replacement.

No new required environment variables are needed. Existing `SCHEDULER_MEMORY_SOFT_LIMIT_MB` may remain at 1450 MB. Optional diagnostic threshold `SCHEDULER_LARGE_JSON_WARN_MB` defaults to 20 MB.

After deploy, verify that both web and scheduler report `v19.22.0-rc16.31bh` and the same commit. Then watch the first due cron. Acceptance requires no Render OOM kill. If a large legacy read remains, retain the complete log line containing `LARGE_JSON_READ` or `Scheduler blocked legacy monolith read`; that key identifies the remaining call path without risking a >2 GiB allocation.
