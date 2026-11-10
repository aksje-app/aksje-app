# Restart storage memory correction implementation plan

> For agentic workers: execute inline; verify before completion and review the final change.

Goal: prevent the document-sized database COPY allocation that killed a PostgreSQL backend in MI-20261110-220809, while preserving all historical data, financial atomicity and original exceptions.

Architecture: add a versioned, lossless zlib/base64 JSON storage envelope only for large restart-bundle documents. The storage adapter reads legacy and encoded forms, verifies size and SHA256 before returning the original JSON value, and never exposes the envelope to financial callbacks. Writes are explicitly opt-in after compatible readers are deployed; an already encoded row stays encoded even if the write flag is subsequently absent. Existing transaction/advisory locks, idempotency and fail-closed governance remain intact. No retry is added. No trading/evidence threshold changes.

Evidence: production backend killed by signal9 during COPY; approximately249MB stored state. Isolated241463878-byte archive fixture: current backend RSS708.0MiB; native large-object staging668.8MiB, insufficient improvement to justify its shared-catalog churn. Use compressed transport instead. No production reproduction is permitted.

- [x] Write and observe failing real-PG tests: decode stored envelope, opt-in compressed roundtrip, unchanged opaque hashes, sticky format, corrupt SHA/size/payload rejection without callback execution, scope isolation and disconnect error preservation.
- [x] Implement one codec module, integrate only restart decoding/write staging, preserve original rollback exception. Bound decoded size512MiB and verify exact checksum/stream termination before JSON parsing.
- [ ] Verify legacy/encoded roundtrip, concurrent mutation, rollback, idempotency and explicit source-shaped memory benchmark. Run focused PG suite and full suite; report existing baseline failures.
- [ ] Independent review, exact-head CI, merge and deploy compatible readers with encoding off. Confirm both runtime services use that release before enabling the write flag. Do not downgrade below a codec-aware reader after encoded data is written.
- [ ] Enable encoding for web and scheduler, deploy as required, and verify normal maintenance plus the stored format/semantic checks without forcing trades or a new report. Record any unavailable ordinary-report observation explicitly.

Tradeoffs: raw SQL sees an explicit versioned envelope for these large keys; callers must use the storage adapter or the documented decoder. Backend memory and transfer are reduced; the logical history remains intact. Large-object staging is rejected because its memory reduction is small and it introduces shared-catalog churn. Splitting immutable journals is a possible later architectural improvement, not an excuse to delete history here.

Progress: 231 focused PG tests passed,2 opt-in memory checks skipped; full suite2715 passed,253 skipped,4 subtests and the same4 named baseline failures. Source-shaped encoder83.06% smaller; database backend155.0MiB versus708.0MiB before. Existing ordinary-maintenance conversion is storage-only and limited to one selected period per run. Source API quotas remain a separate issue.
Ruling: decoded limit512MiB and encoded database-field limit64MiB fail closed before unsafe transport. Original data remain recoverable; journal partitioning remains a future scaling improvement rather than data deletion.
