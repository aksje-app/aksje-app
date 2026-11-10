# Restart storage memory correction

The evening report MI-20261110-220809 was delivered with an explicit limitation because its Autonomy transaction failed while writing the shared restart bundle. PostgreSQL logged a backend killed by signal 9 during binary COPY, terminated other active processes, and entered automatic recovery. The application then obscured the original SSL EOF error by calling rollback on the closed connection. The exact operating-system reason for signal 9 is not proven by the available logs; the document-sized memory allocation is independently reproduced and reduced here.

## Change and preserved behavior

Large restart-bundle documents have a versioned, lossless zlib/base64 JSON storage envelope when explicitly enabled. Both legacy JSON and encoded values are read transparently by the storage adapter. SHA256, decoded byte length, stream termination and JSON encoding are checked before financial callbacks receive the original value. Corrupt encodings fail closed, including when local fallback would otherwise be allowed. Normal document namespaces are unaffected.

The existing binary COPY now receives the small ASCII envelope. A transaction/advisory lock keeps format selection and financial writes serialized. Once encoded, a large row remains encoded even if the rollout flag is absent. Immutable creation still returns the existing decoded record on conflict. No write or financial callback is automatically retried after a disconnected/uncertain transaction. Rollback failures no longer hide the first error.

The original JSON bytes, event history, signed grants, request hashes and financial values are retained; this is a storage encoding, not a journal rewrite. Generic raw SQL sees a self-describing envelope for these keys and must use the documented decoder to inspect financial fields. The decoder is in `services/restart_payload_codec.py` and uses only the standard library.

Safety bounds: decoded JSON may not exceed 512 MiB; a database write may not exceed 64 MiB after encoding. The encoder stops early if its output would exceed the storage bound. A legacy write larger than 64 MiB is rejected before COPY when compatible encoding has not been enabled. Exceeding a bound preserves the previous document and requires partitioning/checkpointing, rather than sending an unsafe field to PostgreSQL. This does not claim that one ever-growing logical journal is an unlimited-scale architecture.

## Controlled rollout

1. Deploy codec-aware readers to both web and scheduler with `RESTART_BUNDLE_COMPRESSION_ENABLED` absent/off.
2. Verify both deployed commits and runtime identities before enabling writes.
3. Set the flag to `1` for both services. The ordinary scheduler performs at most one storage-only conversion per invocation, only for explicitly selected restart periods, under the same bundle lock. It records source SHA256 and before/after sizes. No financial callback, trade, new worker or schedule is introduced.
4. Verify the normal maintenance receipt, encoded record metadata, runtime identities and operational account health. Do not regenerate an old financial job to make a failed historical report look successful.

After encoded records exist, rollback targets must also understand this codec; do not roll back below this reader release. New readers continue to decode with the flag off, and the writer preserves an already encoded format. A missing or corrupt encoded value never becomes a fresh/empty financial account.

Storage envelopes are internal canonical records: preserve their serialized representation when copying/restoring them rather than reordering or pretty-printing envelope fields. Sticky encoding applies to documents at or above the 1 MiB large-write threshold; an explicitly replaced smaller document can use legacy JSON, which both deployed reader versions understand.

## Verification

A private, production-shaped 241,463,878-byte fixture from the user's restored database archive was tested only on disposable local PostgreSQL 18. Original transport: 708.0 MiB peak backend RSS. Encoded transport: 40,915,830 stored bytes and 155.0 MiB peak backend RSS. The entire original SHA256 and decoded content were verified. Native large-object staging was explored but rejected: it reduced backend RSS only to 668.8 MiB and added shared-catalog churn.

The local executor does not enforce Docker's requested 1 GiB limit (its observed cgroup limit is 16 GiB), so the local claim is backend RSS, not a hard-capped cluster acceptance. CI explicitly requires a genuinely enforced 1 GiB PostgreSQL 18 container, tests an approximately 250 MB partially incompressible fixture, requires zero OOM events and a cluster peak below 768 MiB, and verifies the decoded source hash.

Tests were observed failing before fixes for original-error preservation, reading encoded values, opt-in writes, sticky format, corrupt size/checksum/stream/version, UTF8 preservation and maintenance migration/concurrency. The focused real-PostgreSQL set passed 231 tests with 2 intentionally opt-in resource checks skipped. The complete local suite passed 2715 tests, skipped 253 and passed 4 subtests; the same four existing baseline failures remain:

- `test_production_roots_and_complete_lock_are_exact_and_installed`: local dependency pins.
- `test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch`: older FakeCursor context-manager fixture.
- `test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master`: existing universe-source authority fixture.
- `test_new_breach_sends_pushover_after_configuration_change`: an additional time-dependent FX alert.

Independent review also found corruption and size-bound errors could enter the older availability fallback in immutable and ordinary writes, and malformed outer JSON could fall back on read. Four regression tests reproduced these cases before the fix. These errors now fail closed without retry or stale local fallback; the final targeted adapter set passed 32 tests. The exact-head Release Gate, review and production rollout evidence are recorded in the PR and issue 200. No checks were relaxed. Source API quotas/rate limits are a separate limitation: this storage correction never lowers evidence requirements or invents buy signals.
