# Bounded working journal and genuine report acceptance

The growing compressed financial root is approaching its existing 64 MiB write
limit. Move historical event payloads into immutable content-addressed rows,
while retaining event order, original hashes, current account state and complete
financial replay. Historical payloads load one at a time; bounded compressed
caching avoids repeated network reads. Do not change strategy parameters,
learning data, execution evidence requirements or source coverage.

Deploy compatible readers before enabling the explicit migration flag. Under
the existing root transaction lock, preserve the exact original stored root,
verify the complete source, externalize payloads, decode the replacement, verify
all financial accounts again and compare canonical logical hashes. Commit the
root, immutable payloads, backup and migration receipt atomically. Any failure
rolls back everything. No history is deleted. Once migrated, writes remain in
V2 even if the migration flag is removed. Old binaries cannot read V2; rollback
requires compatible readers or verified materialization of the CURRENT journal.

Test immutable lazy mapping semantics, malformed references/checksums, bounded
reads/cache, lossless real PostgreSQL migration, idempotency, transaction rollback,
post-migration trading/retry and immutable history before activation. Run the
existing production lifecycle and browser gates and independent review.

A separate observational receipt may accept only the next genuine fixed-slot
required report after migration, with financial assessment, final PDF, actual
delivery and observed process/cgroup memory within 2 GiB. Ordinary cron cycles,
synthetic tests, old report repair and source-limited readiness are not proof.
