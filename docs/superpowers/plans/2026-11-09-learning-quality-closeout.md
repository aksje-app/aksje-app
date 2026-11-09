# Learning quality closeout implementation plan

**Goal:** Finish the authorized data-quality work in points 1–4 before a historical strategy test. Every retained item has a recorded disposition; missing sources are not invented or described as validated.

**Architecture:** Preserve the original 92 decisions, 78 transactionally quarantined outcome backups and the new V2 cohort. Freeze legacy observations in place: no quote requests, new outcomes, active quota usage or active learning statistics. Keep a reproducible closeout inventory and a recovery export outside the repository. No new worker, notifications, trading policy or historical replay.

**Approach:** Existing engine with a strict method boundary. Recalculating old rows would overwrite provenance; deleting them would lose signals. The chosen approach preserves them and prevents further use. This is an implementation decision within the user's existing repair authorization.

**Tech Stack:** Python, pytest, existing PostgreSQL storage and Render services.

## Global constraints

- Point 5 stays on hold. No historical profitability conclusion.
- Negative returns and missing cost evidence are not deletion criteria.
- Original decisions and stored measurements remain unchanged.
- Only V2 rows may consume active outcome quotas or receive new measurements.
- Gross listing-currency references are not net NOK performance. Costs/FX and missing Swedish benchmark remain explicit qualification failures.
- Production reads use exact keys and bounded payloads; no full-report scan or heavy new job.

## Review focus

Unknown method versions must fail closed; a mixed legacy/V2 run must request only V2 symbols and preserve legacy bytes logically; a legacy-only report must not propose threshold changes or publish correlations; the active cap remains 120 V2 samples; quarantine protection and original snapshot hashes must survive the change.

## Task 1: Freeze unqualified legacy producers and consumers

- [ ] Add regressions in `tests/test_learning_quality_closeout.py` for legacy-only no-provider/no-source-write, mixed cohorts, legacy quota saturation and legacy-only analysis exclusion. Run them and observe failures.
- [ ] Update `learning_observation_engine.py` registration, evaluation and analysis to accept only the explicit current measurement policy. Return preserved legacy counts. Remove the legacy outcome producer.
- [ ] Update older evaluator fixtures to exercise V2 completed-session behavior; retain the legacy evidence arithmetic and quarantine tests.
- [ ] Run focused tests including isolated PostgreSQL, then the repository suite and required Release Gate. Record baseline failures truthfully.

## Task 2: Recovery and durable closeout evidence

- [ ] Compare all original decisions and unaffected legacy rows with original export; verify all 78 compressed backups and receipts and the new report census checksum/receipt.
- [ ] Write a machine-readable disposition inventory for every retained observation and historical scheduled report. Missing source is distinct from a zero signal count; source presence alone is not validation.
- [ ] Create a downloadable recovery archive and SHA256 manifest, retaining DB backups. Never purge sole recovery copies.
- [ ] Commit a concise closeout document with explicit statuses and acceptance evidence. Record remaining source/financial prerequisites for point 5 without marking them passed.

## Task 3: Review and rollout

- [ ] Obtain independent whole-change review; fix important findings with regressions.
- [ ] Merge only the successful exact CI head, deploy web/cron, verify commit and health and normal scheduler completion.
- [ ] Record any future report-specific nonzero census check as pending if none has occurred; do not fabricate a production signal to satisfy the check.

## Ledger

Initial evidence: deployed PR194 completed normal scheduler at 23:20:42 UTC, all runtime roles on 7da8a440. Scheduled report MI-20261109-220857 persisted an immutable zero-signal census and matching post-gate receipt; 41 V2 control/reference samples registered. Source has 133 rows: 78 quarantined legacy, 14 other legacy, 41 V2. Point 5 has not started.

Ruling: legacy baseline generation is held before archive loading or notification; the existing stored baseline and forensic builder remain preserved. Otherwise an empty/restored store could silently restart the rejected method. Existing VERIFISERT is retained only as original metadata; its figures are shown as legacy references, not qualified horizons. Cost if wrong: loss of automatic legacy baseline generation, intentionally required until point 5 defines a qualified replacement.

Ruling: factor-attribution placeholders with count=0 and correlation=null are retained; an empty list is not needed to prevent use of legacy data. No statistics are calculated from legacy rows.
