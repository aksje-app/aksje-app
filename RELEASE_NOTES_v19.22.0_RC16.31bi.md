# Release notes v19.22.0-rc16.31bi

## OOM Breadcrumb + Status Compaction

Base release: RC16.31bh. This release does not change scoring, risk, recommendation or trade-authorisation rules.

### Changes

- Adds durable `runtime/oom_breadcrumb_latest.json` plus append-only breadcrumb events written before expensive scheduler/report phases.
- Breadcrumbs include process RSS, cgroup memory, stage and a bounded detail payload. The latest marker survives a hard Render OOM kill and identifies the last entered phase.
- Scheduler records breadcrumbs around the due-report cycle, paper scanner and learning maintenance.
- Report execution records breadcrumbs around previous-run load, market phases, Autonomy, canonical persistence, main/technical PDF generation, run JSON persistence and historical learning.
- Manual/background `status.json` now stores a compact operational Autonomy-chain summary instead of duplicating large learning portfolio/decision trees. Canonical report and learning storage are unchanged.
- Diagnostic bundles now include `runtime/OOM_BREADCRUMB_LATEST.json` and compact old chain data before serialising the support ZIP.

### Purpose

RC16.31bi is an observability/containment release. If Render still kills the scheduler above 2 GiB, the last durable breadcrumb is the authoritative next root-cause locator.
