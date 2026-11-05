# Restart journal CPU and memory follow-up

The preceding full production run completed below the 2048 MiB limit, but its
1898.5 MiB cgroup peak left only 149.5 MiB headroom. This follow-up is **not
production accepted** until its exact source passes Release Gate and a full
deployed workload has completed with measured memory and journal preservation.

## Measured cause

On deployed source `6ed8f1a73273474e5639933b1625cb4e45510032`, a read-only
`production_routing.view('paper')` profile on the real signed restart history
made 327,462,645 calls, taking 87.104 CPU seconds with cProfile enabled.
Canonical hashing, rather than JSON parsing or SQL, dominated the profile.
Baseline job: `job-dbmgfnuk1f9s7386jro0`.

The bounded subtree candidate repeated that same read-only verification in
`job-dbmgqpegekts73es2tgg`: 81,910,120 calls and 39.354 CPU seconds under the
same profiler. The projection SHA-256 was identical:
`2fbda75b75e6e0b84bc56311f6283c634709f8820c70348e10ce67ccb3e35363`.
These are profiler measurements, not normal application response times.
Single-core utilization can still reach 100% during useful work; CPU seconds
and run duration determine whether redundant work was actually removed.

The same probe found a 116,257,031-character database JSON string occupying
465,028,184 bytes in Python because Unicode widened the entire string to four
bytes per character. This temporary allocation overlaps the decoded history.

## Changes and preserved guarantees

- Canonical SHA-256 still includes every event and byte under the same sorted
  keys, separators, UTF-8 and finite-number rules. Native JSON encoding is
  restricted to subtrees with a conservative 8 MiB serialized allocation
  bound and 262,144-node bound. Large containers are streamed in canonical
  order. Unsupported values retain the previous encoder's validation.
- Normal locked restart-bundle writes persist ASCII JSON escapes. Decoded
  Unicode values and signature/event hashes remain identical. No standalone
  rewrite, retention deletion or historical truncation is performed. Other
  stored documents retain their existing serialization behavior.
- A mutation closes its libpq result cursor before decoding. The connection
  transaction, advisory lock and row lock remain held through transformation
  and commit; exceptions still roll back. Real PostgreSQL tests check a second
  connection cannot acquire either lock after the read cursor has closed.
- Execution-only Superportfolio stop surveillance explicitly defers when
  **all** held tickers have recognized exchange suffixes and all those
  exchanges are closed. This avoids repeatedly requesting an impossible fresh
  EVO.ST quote after Stockholm closes. It neither invents prices nor extends
  quote freshness, adjusts stops, writes trades or changes strategy settings.
  Unknown, continuous, mixed/open instruments retain the strict existing path.
  The result states MARKET_CLOSED and includes the next exchange opening.
- That read-only deferral may reuse an already verified account projection
  from the same run only after fresh route/bundle PostgreSQL row versions,
  installation/certificate and valuation clock bounds match. It never loads a
  new bundle on cache miss. Actual execution still selects and verifies fresh
  history and validates again inside the locked transaction.

## Verification

The read-only candidate checked the actual production signatures and journal
chains without mutation. Local tests cover canonical-byte parity, large-history
bounded allocation, rejection of malformed/circular values, Unicode/hash
round trips, rollback, lock lifetime, exchange holidays/weekends/DST, open-market
quote rejection and detached version-checked reuse. Release Gate explicitly
includes the new PostgreSQL tests. Final deployment and full-run measurements
must be appended to the existing PR #190; this predeployment record does not
claim acceptance.
