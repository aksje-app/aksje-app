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

The transaction still reads the authoritative row under lock and verifies signed
authorization, journal replay, account reference, settings and duplicate run IDs.
No financial history, source data or learning records are removed. No failed
morning job is manually replayed, and no capital/strategy settings are changed.

## Verification

- Lifetime tests failed on the original code at both preparation and quote
  boundaries, and pass after releasing the selection.
- Real collector tests preserve a valid latest held-position quote during a
  provider outage and still reject a missing held-position quote.
- An independently replay-verified private Nov 10 archive (241,463,879 bytes)
  measured process RSS 681.5 MiB before detachment and 44.2 MiB afterward.
  Detached execution input was 1009 bytes, current portfolio 2622 bytes.
  This is an offline process measurement, not a production peak assertion.
- 86 focused tests passed, including the real PostgreSQL production lifecycle.
- 57 strategy/cost/lifetime tests passed; one explicitly database-dependent test
  skipped in that separate non-Postgres invocation.
- Nine actual Superfond browser checks passed.
- Independent review found no critical or important issues; requested collector
  equivalence coverage was added and independently verified.

Relative-date financial test fixtures initially selected the Nov 26 US holiday.
They now select an open trading week through the real market calendar, rather
than bypassing the market-closed gate. This changes test data only.

## Remaining limitation

The entire historical journal remains one decoded transaction document. Releasing
unneeded references removes avoidable overlap, but does not bound its growth or
guarantee future full reads/writes fit 2 GiB. Issue 200 remains open for a separate
journal storage redesign with preserved hash chains, replay, locking and migration
recovery proof. Raising the memory plan or deleting history is not this change.

Production acceptance requires a naturally scheduled report completing on the
deployed change. A healthy deployment or ordinary idle cron alone does not prove
the morning report's financial chain will fit the memory limit.
