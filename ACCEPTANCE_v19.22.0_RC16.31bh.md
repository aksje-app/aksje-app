# Acceptance RC16.31bh

RC16.31bh is accepted only after live Render evidence satisfies all of the following:

1. Scheduler and web are both on `v19.22.0-rc16.31bh` and the same commit.
2. At least one full due scheduler cycle completes without `Out of memory (used over 2Gi)`.
3. Peak scheduler memory remains below the Render 2 GiB hard limit; target is below the existing 1450 MB soft limit during normal work.
4. No full scheduler read of the known legacy monoliths occurs. Any attempted oversized legacy access must be stopped before payload fetch and identify its key in the log.
5. Norway-only production scope from bf/bg remains active.
6. Retention remains enabled and protected data is not deleted.
7. No scoring, risk, recommendation or trade-authorization behavior changes relative to bg.

A controlled `MEMORY_DEFERRED` or explicit oversized-read diagnostic is preferable to an OOM kill, but production status still requires a subsequent complete ordinary run.
