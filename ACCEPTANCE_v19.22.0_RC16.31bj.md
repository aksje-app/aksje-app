# Acceptance RC16.31bj

RC16.31bj is accepted for the OOM closure only when all of the following are true:

- Scheduler identity is `v19.22.0-rc16.31bj`.
- A cron that reaches learning maintenance completes without Render killing the process at 2 GiB.
- Breadcrumbs progress beyond `scheduler:learning_maintenance:before` and reach `learning:maintenance:done`, or a legitimate NOT_DUE/controlled failure path.
- Peak/cgroup memory remains below the Render 2 GiB hard limit with meaningful safety margin.
- Historical baseline, daily learning and weekly learning retain their existing result contract.
- No analysis, buy, risk, portfolio or execution threshold changes are observed.

If OOM remains, the release is not accepted even if other scheduler components succeed.
