# Verified learning price archive implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace only explicitly verified, finished price inputs with recoverable archive references, preserving ongoing learning and all results.

**Architecture:** The existing, checksum-matched and restore-tested Render backup on the user's PC is the external recovery source. An exact, versioned authorization manifest binds 1,344 price keys and both result hashes to that backup. A bounded PostgreSQL transaction verifies current completion, immutable source hashes and row locks before replacing prices with small references. Readers stop explicitly on archived input; restoration accepts only the exact original bytes. No automatic access to the user's PC is assumed.

**Tech stack:** Python 3.12, PostgreSQL 18, existing StorageService and cron scheduler. No new dependencies or paid resources.

**Spec:** The agreed manual PC archive workflow; verified backup SHA-256 `bcde2be937aa8317a9f26234de01df872acd2bfe3e42567a95de41ed6d495309`; export 2026-11-17T16:06Z, 888151608 bytes. The prior inventory is an eligibility proposal, not a claim that prices were removed.

## Global constraints

- Only `strategy_history/prices/<sha256>.json` may be replaced. All learning results, forward accounts, observations, financial history and backup proofs remain.
- Replacement is enabled only by a dedicated flag and a checksum-pinned exact manifest; broad retention remains disabled.
- Both engine results must remain COMPLETE_RESEARCH with the authorized method and exact authorized hashes; both collection and optimization ledgers must contain the ticker.
- Checkpoints, results and price rows are locked; source mismatch or changed method fails closed. A receipt and its batch changes commit together.
- Each pass is bounded to at most 128 keys and 30 seconds of SQL. No large journal or latest_run.json reads.
- Restore accepts only the exact raw bytes identified by the reference. Restored inputs are not automatically archived again after the one-time pass completes.
- A later method reset must yield WAITING_ARCHIVE, not insufficient history or a rejected ticker. Price collection must not fetch replacement history or overwrite an archive reference.
- Restored data retains its original financial limitations; an archive is not financial approval. Report byte savings as stored-value estimates, not reduced Render disk allocation.

## Review focus

- Concurrent method/checkpoint/result changes: row locks and exact hash guards preserve active work.
- Partial failure/retry: replacement and progress receipt are atomic and idempotent.
- Cold or malformed reference: both consumers stop explicitly without writing invalid results or fetching new history.
- Restore or operator rerun: changed references/bytes are rejected, completed authorization does not consume restored data again.
- Activation: both deployed consumers must understand references before the scheduler flag can be enabled.

## Task 1: Integrated archive lifecycle

**Files:** Create `services/learning_price_archive.py`, `services/learning_price_archive_batch.py`, `services/learning_price_archive_20261117.json`, `tests/test_learning_price_archive.py`, `tests/test_learning_price_archive_postgres.py`. Modify both price consumers, their status view, and the scheduler's bounded maintenance section. Document restoration and activation.

**Interfaces:** `read_price(storage, key)`, `write_price(storage, key, value)` and `restore_price(storage, key, raw)` live in learning_price_archive. `archive_batch(storage, manifest, max_items=128)` is the native transactional worker. `run_scheduled_archive()` loads only the pinned manifest when enabled.

- [x] Write and run failing tests for reader/collector suspension and exact restoration.
- [x] Implement reader/writer guards and visible resumable archive status; verify regression tests.
- [x] Write and run failing native PostgreSQL tests for completion/source checks, atomicity, locks, idempotence, scoped limits and exact restoration.
- [x] Implement bounded replacement and authorization manifest; add the disabled-by-default scheduler hook.
- [x] Test dry-run eligibility against the restored snapshot without changing it; test apply/restore against a separate fixture database.
- [ ] Obtain fresh whole-branch review, run required CI once on final head, merge and deploy both services under standing authorization.
- [ ] Enable only the exact manifest after both consumers are live; observe a real bounded batch and receipt before claiming any production savings.

## Execution ledger

Baseline: 35 historical optimizer, collection, status and notification tests pass on main. Existing full-suite baseline failures remain documented separately. User selected the manual PC/full-backup route and requested continuation without more download attempts. No new external store is provisioned.
