# Acceptance RC16.31bg

Production acceptance remains pending until live Render evidence is available.

RC16.31bg memory closure is accepted when:

- at least one ordinary cron cycle completes without Render `Out of memory (used over 2Gi)`,
- at least one market-open Paper scan completes or checkpoints cleanly without a hard OOM kill,
- peak process/cgroup memory is visible in scheduler diagnostics,
- no scheduler phase exceeds the 1450 MB soft limit without controlled `MEMORY_DEFERRED`,
- strategy decision/run writes no longer grow/rewrite the legacy monolithic collections,
- Norway-only scanner configuration is reported consistently by runtime diagnostics,
- no scoring, risk or trade authorization behavior changed.

A full 08:00 / 14:00 / 22:00 healthy production day is still required for final production status.
