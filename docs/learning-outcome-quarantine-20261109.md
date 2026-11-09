# Controlled repair of inconsistent observation outcomes — 2026-11-09

The user explicitly requested isolating unusable learning data and controlled deletion from the database. This narrow repair supersedes the general preserve-all-history policy **only for the active outcome fields of the 78 explicitly identified row versions** in `services/learning_quarantine_20261109.json`.

## Evidence and scope

The production observation document contained 92 rows. Original frozen decision snapshot hashes all verify when the original Python numeric representation is retained. Seventy-eight outcome sets have a mathematically impossible relationship across their measured windows: maximum gain decreases or minimum return increases across extended windows (26 rows), daily and horizon returns disagree for the same endpoint (76 rows), or benchmark returns cannot be reproduced from their frozen denominator (31 rows). These overlap. There are 234 horizon measurements and 3,251 daily marks on these rows. Those outcome sets cannot safely be mixed into learning statistics.

The producer downloaded a fresh adjusted history when each new horizon matured, retained earlier frozen measurements, and had no cross-window consistency check. This permits mixed history revisions. Provider adjustment changes are a plausible contributor, not a verified explanation for each affected row. An additional producer defect allowed an unfinished same-day bar to be frozen as a daily outcome. A new regression proves that failure mode. The evaluator and provider loader now require the exchange close plus a 15-minute publication buffer before using a daily bar. This explains a possible mechanism for conflicting endpoints, not the provenance of every historical mismatch. The invariant failures themselves are reproducible from persisted evidence, without trusting a new provider download.

Poor returns, small samples, controls, obsolete model versions and missing cost evidence are **not** deletion criteria. Remaining rows have only passed the implemented mathematical checks; this is not proof of source accuracy, complete signal capture, net profitability or a valid causal experiment. The stale September baseline and published historical reports remain historical artifacts, not proof of an investment edge. No deletion of research progress, raw decision archives, executed transactions, closed-position benchmarks, financial balances or original signals is allowed by this repair.

## Transaction and recovery

`apply_manifest` defaults to a dry run. The scheduled entry point applies only the fixed 78-row manifest. It requires authoritative PostgreSQL without local fallback, limits the source to 4 MiB and each transaction to 30 rows (three fixed batches for this 78-row repair), and uses a two-second lock timeout and ten-second statement timeout. Changed, missing or duplicate source identities abort or defer cleanup. All row hashes must match before any mutation.

In one transaction it creates a compressed immutable original-row backup under `controlled_learning/quarantine/outcomes/`, reads it back, verifies its checksum and contents, removes the active outcome arrays and daily marks, marks the observation `QUARANTINED`, and writes a receipt. Original decision metadata is retained. A failure rolls back the source and backup writes together. Repeat execution is idempotent and checks the recovery copy. Normal observation writes retain authoritative quarantine tombstones so stale report/price jobs cannot resurrect deleted active results.

The backup is intentionally retained in PostgreSQL. There is **no automatic irreversible purge** of the recovery copy. Removing active fields is distinct from permanently deleting every copy. An external durable backup must be exported and verified before a separate scoped purge of quarantine could be justified. No extra confirmation is needed for the cleanup already authorized; this is the recovery constraint on the implementation.

For explicit recovery, `restore(storage=..., backup_key=..., apply=False)` previews restoration; `apply=True` restores only matching quarantine identities. Never run restoration as a scheduler task. Restored inconsistent outcomes remain excluded by report validation.

## Prevention and reporting

The producer checks the proposed union of old and new horizon measurements before publishing any new window. An inconsistent union is rejected, old evidence is retained for audit, and source health becomes `OUTCOME_WINDOW_INCONSISTENT`. It does not silently rewrite old observations to make them agree.

Weekly analytics and measured-horizon summaries exclude inconsistent or quarantined rows. Weekly analytics expose the excluded count and degraded data health. Exclusion changes sample composition; no improved average after cleanup demonstrates a better strategy. The state remains `NOT_VALIDATED`.

## Validation

Regression tests reproduce report contamination and the producer accepting contradictory new windows. Real PostgreSQL tests cover dry-run safety, backup read-back, affected-field removal, preservation of valid negative returns and unrelated research, source-change rejection, rollback on backup failure, idempotency, full restoration, and stale-writer protection. The release workflow runs these tests against its isolated PostgreSQL.

An additional isolated PostgreSQL exercise on the exact exported 92 production rows verified: 78 isolated rows, 234 active horizon measurements and 3,251 daily marks removed; all other 14 rows unchanged; backup contents equal original rows; repeated cleanup idempotent; complete restoration equal to the input. The exercise took approximately 0.63 seconds, max RSS approximately 43 MiB. These are local measurements, not a production CPU benchmark.

Production application is only considered complete after a deployed scheduler run has written the matching receipt and a read-only SQL check confirms the cleaned source and backup.

Full local suite: 2,657 passed, 223 skipped, 4 subtests passed, with the same four failures previously reproduced on the unchanged baseline in this session: `test_production_roots_and_complete_lock_are_exact_and_installed` (local transitive dependency versions), `test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch` (old FakeCursor lacks context-manager protocol), `test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master` (live universe authority differs), and `test_new_breach_sends_pushover_after_configuration_change` (extra time-dependent FX alert in full suite). The focused learning/integrity/PostgreSQL suite passes. The current release gate remains required before deployment.
