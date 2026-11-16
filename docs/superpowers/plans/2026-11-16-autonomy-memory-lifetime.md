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
- [ ] Split context extraction from evidence fetching in production_routing.py.
- [ ] Pass detached portfolio into autonomy_nok_companion.prepare; release selection.
- [ ] Verify evidence equivalence, focused and full suite, archived memory probe.
- [ ] Review, run release checks, merge and deploy; verify production versions.
