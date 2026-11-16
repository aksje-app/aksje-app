# Scheduler memory incident, 16 November 2026

## Evidence

Render killed the morning report scheduler at 07:09:46 UTC for exceeding 2 GiB.
The deployed commit was c548644c, including PR 204. This was not a missed deploy.

At 07:07:44 process RSS was 516 MiB before another full restart bundle read.
The stored envelope was 52,191,282 bytes. At 07:07:50, after decode, RSS was
1495.7 MiB. A durable preparation receipt exists for the same morning, with
60 candidates and a completed five-strategy comparison. The last full-read
marker does not identify whether the eventual kill occurred during execution
evidence collection or before the next locked-read decode marker. It must not
be presented as proof of an optional-worker failure.

The root had reached 53,435,210 stored / 355,298,286 decoded bytes when inspected
later. Strategy request/state/result receipts account for most historical size.
Neither small current balances nor a legacy archive blob explain the growth.

## Change

The running Autonomy route extracts a detached current portfolio and the existing
execution reference, cost policy, held positions and latest fallback quotes.
It releases the selected bundle and trims free allocator arenas before optional
preparation and quote requests, and again before the locked transaction.
Small stdout memory markers distinguish those phases in future incidents.

The first candidate was held back after an additional realistic-size probe still
exceeded 2 GiB process RSS. The final change also streams base64/zlib decoding and
uses the standard JSON decoder for individual historical events, avoiding a
second full decoded-history string. Financial mutations stream JSON encoding
directly into the existing compressed envelope, avoiding the full plaintext JSON
and its encoder chunk list. Large-event retries grow geometrically to avoid
reparsing an event from the beginning for each small incoming chunk.

The persisted format stays ZLIB_BASE64_JSON_V1. Byte size, checksum, zlib termination
and complete JSON termination must pass before returning data or calling a
financial mutation. Previously encoded writes remain streamed if the rollout
flag is disabled. Other document types keep their existing behavior.

The transaction still reads the authoritative row under lock and verifies signed
authorization, journal replay, account reference, settings and duplicate run IDs.
No financial history, source data or learning records are removed. No failed
morning job is manually replayed, and no capital/strategy settings are changed.

## Verification

- Final CI-equivalent production lifecycle command, including actual PC/mobile
  browser exports, passed all 205 tests locally with the workflow's environment
  and compression enabled. The earlier CI found a separate operator read adapter
  returning the encoded envelope, plus a cursor test double lacking binary COPY.
  The adapter now decodes reserved restart records; the mock implements the DBAPI
  interface and explicitly tests compressed writes. Targeted reproduction: 37 pass.
  Full suite after these corrections: 2802 pass / the same five baseline failures.
  The opt-in real-engine 92 MiB journal test also passed (1443.3 MiB process peak;
  preserved 4902 historical events). Physical local cgroup limit remained 16 GiB.
- Final combined verification: 206 checks passed with compression enabled,
  including real PostgreSQL lifecycle, codec corruption/rollback and mutation
  cases. Full suite: 2801 passed, 272 skipped, four subtests passed, five failures.
  Those same five also fail on unchanged main: dependency pins
  (`test_rc16_31ae_deterministic_deploy`), old FakeCursor context manager
  (`test_rc16_31bh_oom_root_cause_closure`), universe authority
  (`test_rc16_31g_universe_coverage`), FX alert test order/timing
  (`test_v18713_fx_runtime_paper_alerts`) and the aged fixed SEC filing
  (`test_v1908_auditable_evidence`). They are not waived as a green full suite.
- Lifetime tests failed on the original code at both preparation and quote
  boundaries, and pass after releasing the selection.
- Real collector tests preserve a valid latest held-position quote during a
  provider outage and still reject a missing held-position quote.
- An independently replay-verified private Nov 10 archive (241,463,879 bytes)
  measured process RSS 681.5 MiB before detachment and 44.2 MiB afterward.
  Detached execution input was 1009 bytes, current portfolio 2622 bytes.
  This is an offline process measurement, not a production peak assertion.
- Earlier lifetime-only candidate: 86 focused checks passed, including real
  PostgreSQL production lifecycle; the larger probe still rejected that candidate.
- 57 strategy/cost/lifetime tests passed; one explicitly database-dependent test
  skipped in that separate non-Postgres invocation.
- Nine actual Superfond browser checks passed.
- Independent review found no critical or important issues; requested collector
  equivalence coverage was added and independently verified.
- A second probe grew the verified private archive to 356,447,278 decoded bytes
  using explicitly synthetic nonfinancial strategy receipts and retained a
  650 MiB background allocation. With the lifetime fix alone, process peak was
  2262.6 MiB; with streaming it was 1861.7 MiB. Both identity writes preserved
  the exact stored journal bytes. The streaming probe took about 59 seconds
  versus 41 seconds for the earlier candidate. This is not a full report timing.
- The requested Docker 2 GiB limit was not actually available to this probe:
  the observed cgroup limit remained 16 GiB. Only the process RSS comparison is
  established; these results must not be called acceptance under an enforced
  2 GiB limit.
- Streaming regressions first failed on whole-history JSON loads/dumps and on
  repeated parsing of a large event. Corruption/rollback, chunk boundaries,
  malformed data, old wire bytes and flag-off encoded writes are covered.
- A separate streaming review additionally matched 10,000 valid and 20,000
  malformed chunk comparisons against the standard JSON decoder, 1,000 codec
  round trips and 2,000 float/key wire comparisons. No important issues found.

Relative-date financial test fixtures initially selected the Nov 26 US holiday.
They now select an open trading week through the real market calendar, rather
than bypassing the market-closed gate. This changes test data only.

## Remaining limitation

The entire historical journal remains one decoded Python transaction document.
Releasing references and streaming serialization remove avoidable overlap, but
do not bound journal growth or guarantee future full reads/writes fit 2 GiB.
Issue 200 remains open for a separate
journal storage redesign with preserved hash chains, replay, locking and migration
recovery proof. Raising the memory plan or deleting history is not this change.

Production acceptance requires a naturally scheduled report completing on the
deployed change. A healthy deployment or ordinary idle cron alone does not prove
the morning report's financial chain will fit the memory limit.
