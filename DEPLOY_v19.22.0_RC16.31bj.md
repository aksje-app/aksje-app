# Deploy RC16.31bj

1. Deploy the clean DELTA files to the production repository, preserving paths.
2. Confirm both web and scheduler report `v19.22.0-rc16.31bj` after deploy.
3. Do not change the current Render memory plan or analysis thresholds for this acceptance run.
4. Allow the next scheduler cron to run learning maintenance.
5. Check the Render log for `OOM_BREADCRUMB stage=learning:` markers and confirm the cron does not terminate with `Out of memory (used over 2Gi)`.
6. If it still terminates, create a new background-job diagnostic package immediately; `runtime/OOM_BREADCRUMB_LATEST.json` should now identify the internal learning step.
