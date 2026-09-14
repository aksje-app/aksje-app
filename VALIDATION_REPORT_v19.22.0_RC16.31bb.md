# Validation report v19.22.0-rc16.31bb

## Automated verification

- Full regression suite: **1123 passed**.
- Additional unittest subtests: **4 passed**.
- Failures: **0**.
- Full-system audit: **PASS**, zero errors and zero warnings.
- Version and traceability audit: **PASS**, all twelve contracts verified.
- Python bytecode compilation: **PASS**.
- Six PDF variants generated end to end from real BA report data: morning,
  afternoon and evening, both public and technical.
- PDF render inspection: **PASS**, 48 pages rendered; no blank, truncated or
  structurally broken pages observed.

## Corrected production findings

- The scanner has a real hard cap and cannot expand a 30-ticker run to 50
  tickers when a checkpoint is resumed.
- A database in recovery now defers the complete cron run before analysis or
  trading. State persistence is retried and a local recovery receipt is
  replayed when PostgreSQL is authoritative again.
- Storage retention is bounded by batch size and time budget, refuses unsafe
  production fallback storage, and exposes partial/pending work in diagnostics.
- Required-report alerts use a 60-minute grace period and do not report a job
  missing while its execution owner is active.
- Report history separates analytical matches, buy-ready candidates, source
  deviations and actual pipeline errors.
- Report filenames use the canonical run identity.
- Report-detail loading avoids repeated multi-megabyte canonical-run reads and
  avoids unnecessary durable rewrites when PDFs already exist.
- Every diagnosis archive includes the independent storage-retention receipt.

## Safety result

- Production scoring, trade thresholds and portfolio risk limits are unchanged.
- Existing positions and protected trade, decision, audit and learning ledgers
  are never retention targets.
- Database recovery cannot silently fall back to local JSON for production
  trading or report execution.
- Existing re-entry quarantine, result learning and durable mobile report
  delivery remain active.

## Production acceptance boundary

This package is a **locally verified release candidate**. It must not be marked
production-approved until Render documents one healthy ordinary scanner cycle
and the next complete 08:00, 14:00 and 22:00 report sequence, including PDF,
JSON, database persistence and Pushover delivery. Keep
`STORAGE_RETENTION_APPLY=false` for the first healthy ordinary cron after
deployment. Enable it only after database health is stable; the first applied
run must be checked for a bounded `PARTIAL` or `COMPLETED` receipt.

Archive hashes and distribution validation results are recorded in the build
result generated with the final packages.
