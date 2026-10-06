# Autonomi Parameter & Learning UX — rc16.34e

Status: TESTED locally. Not published, merged or deployed.
Base: aksje-app/aksje-app main, 9efd117b5cd3a689ad8d49e754b3f2828fabd41b.

## Changes
- Production parameters expanded immediately beneath Parameterlås; decisions above parameters; history and confirmed rollback below.
- Durable position-risk proposals with explicit confirmation and Godkjenn / Avvis nå / Utsett 7 dager / reversible permanent blocking.
- Proposal status, parameter value, approval snapshot and history commit atomically in the authoritative parameter document. PostgreSQL mutations use a transaction, advisory lock and row lock; local development uses a process lock and atomic replacement. Database mutation failures never fall back to a second local truth.
- Rejection requires 7 days plus 25 genuinely new closed trade IDs OR 20 newly mature observation IDs before re-proposal. Variants share the parameter cooldown. Champion rejection and hypotheses also suppress immediate repetitions.
- Stale approvals and manual saves refuse to overwrite newer values; Champion approval checks its original parameter snapshot.
- PAPER, PRODUKSJON and LÆRING have explicit dataset labels and separate statistics. Reports carry pending decisions and their state.
- Scoped mobile layout stacks Autonomi columns and wraps headings.
- Stored position sizing applies to new positions from the next Autonomi decision cycle. No Super Portfolio, portfolio/history document or existing position is modified by this decision flow.

## Evidence
- Full CI Quality regression suite: 242 passed (37 files).
- Active unversioned suite: 62 passed.
- Focused governance and existing controlled-learning tests: 24 passed.
- 23 CI release verifiers passed.
- Repository Python compilation and git diff --check passed.
- Actual Streamlit AppTest: approval confirmation, button click, persistence of 1.5%, updated slider, username in history and rollback to 3.0% passed.

## Outstanding deployment verification
- User explicitly authorized public GitHub publication and merge on 6 October 2026. Publication and CI verification are underway.
- User confirmed the existing Render workspace My Workspace for deployment checks on 6 October 2026.
- Live PostgreSQL transaction and deployed mobile rendering have not been observed. Local tests and source checks do not constitute live deployment verification.
