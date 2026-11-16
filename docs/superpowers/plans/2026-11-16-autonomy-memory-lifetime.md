# Autonomy memory lifetime implementation

> Execute natively under the user's standing completion/merge/deploy authorization.

**Goal:** Release historical journals before preparation and quote requests.
**Architecture:** Detach the existing execution reference and compact quote inputs
from a verified selection, then use them for collection before the freshly
authorized locked financial transaction.
**Tech Stack:** Python, pytest, existing PostgreSQL storage.
**Spec:** ../specs/2026-11-16-autonomy-memory-lifetime-design.md

## Constraints and review

Keep all persisted bytes, signed approvals, fresh quote checks and idempotency.
Test latest quote fallback, held-position failures, completed retries, pause and
concurrent stop/authorization with the existing real database lifecycle tests.
Do not claim bounded journal growth or a successful production morning report
from offline verification alone.

## Task

- [x] Add failing weak-reference lifetime tests at preparation and quote boundaries.
- [x] Split context extraction from evidence fetching in production_routing.py.
- [x] Pass detached portfolio into autonomy_nok_companion.prepare; release selection.
- [x] Verify evidence equivalence, archived object lifetime and realistic-size probe.
- [x] Reject insufficient first candidate: 2262.6 MiB process peak at 356 MB.
- [x] Add failing full-history allocation and large-event CPU regressions.
- [x] Stream existing envelope reads/mutation writes without changing stored bytes.
- [x] Independently review parser/checksum/wire semantics and remeasure: 1861.7 MiB.
- [x] Complete final combined checks: 206 pass; full suite 2801 pass / five baseline failures.
- [ ] Review, run release checks, merge and deploy; verify production versions.
