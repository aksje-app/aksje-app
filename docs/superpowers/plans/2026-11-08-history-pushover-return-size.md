# Historical Pushover return size implementation plan

**Goal:** Complete the interrupted report improvement described in the user's screenshots: show net average return per test trade and the results of the two most common stop/holding combinations, separately for Autonomy and Super Portfolio.

**Architecture:** Read the existing first finalist, already selected before holdout. Use its held-out `avg_pct`, weighted by `trades`; never divide compounded `total_pct` by trade count. Keep all combination aggregates in the summary and show the two most frequently selected, with symbols/trades and signed returns. This describes results on different selected stock subsets, not a comparison proving a best rule.

**Files:** `services/history_research_notifications.py`, `tests/test_history_research_notifications.py`, `docs/historical-research-pushover-20261108.md`.

**Constraints:** No price downloads, optimizer reruns, rule changes, or unsolicited test notifications. Preserve original documents, indexes and delivery receipts. Use a versioned notification index to recollect missing averages in bounded batches. Daily delivery continues through the existing scheduler.

**Review focus:** Compounded versus arithmetic returns; unequal trade counts and losses; invalid/missing averages; safe resume from old indexes; message length including stale-data warning/runtime footer.

- [x] Add failing tests for source average validation, trade weighting and group results, old-index recollection and notification length.
- [x] Read held-out averages, build weighted overall/group summaries, and introduce versioned indexes.
- [x] Update Norwegian copy with costs, sample counts, two common rules and interpretation.
- [x] Run focused optimizer/notification tests and release checks appropriate to changed code; document results.
- [ ] Commit and open a reviewable pull request; report actual deployment/data access limitations.


## Verification

- 33 focused notification/optimizer/history tests passed with repository direct dependency versions.
- Full pytest run: 2641 passed, 219 skipped, 4 subtests passed; three failures reproduced on unchanged main d843b878:
  - `tests/test_rc16_31ae_deterministic_deploy.py::test_production_roots_and_complete_lock_are_exact_and_installed`: local transitive dependencies differ from requirements.lock.
  - `tests/test_rc16_31bh_oom_root_cause_closure.py::test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch`: FakeCursor lacks the context manager protocol used by storage.
  - `tests/test_rc16_31g_universe_coverage.py::test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master`: live authoritative Euronext universe contradicts the test's packaged-universe assumption.
- Separate code review found no important issues. No production database access or real notification/deployment verification.
- Recovered interrupted commit 5524e64e from fix/pr3-production-readiness-20261105 and preserved it as the parent of the final improvements.
