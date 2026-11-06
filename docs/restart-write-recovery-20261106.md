# PostgreSQL restart write and report recovery

At 13:10:37 UTC on 2026-11-06, PostgreSQL killed backend PID 3585529 with
signal 9 while it executed the upsert of the production restart bundle. The
database reinitialized and accepted connections again at 13:10:43.796 UTC.
The afternoon report failed reading autonomous_portfolio/parameters.json
during that recovery window. Its failed history entry remains preserved.
The production bundle was 152,520,523 bytes when inspected afterwards.

The scheduler has 2 GiB; the separate PostgreSQL service has 1 GiB. Reducing
application reads does not fix PostgreSQL's write-side SQL parsing overhead.
psycopg2 v2 inserts text parameters into SQL literals before sending them.
That gives PostgreSQL's parser additional full-document buffers.

Large restart writes now use bounded binary COPY into a temporary text row,
then INSERT/ON CONFLICT from that row. Both operations remain inside the same
connection, transaction, advisory lock and row lock as the original mutation.
The temporary row disappears on commit/rollback/connection loss. The durable
payload is still the complete ordinary JSON document; no history is moved,
compressed into a private format, pruned, or omitted. Unicode escapes change
only serialization, not decoded values or canonical journal hashes.

Reads retry transient PostgreSQL availability failures up to five attempts,
with 1/2/4/8-second waits. Corrupt JSON and non-transient SQL errors still fail.
The retry stays at the read operation: it never re-executes a strategy callback,
a whole report, or an uncertain write/commit. In particular, a lost commit
acknowledgement must not replay a financial mutation. A longer outage still
fails explicitly instead of silently substituting local/default production data.

## Isolated measurements

Real PostgreSQL 16, 1 GiB kernel limit, identical 157,125,552-byte synthetic
journal-like input (SHA-256
5acbadcdc5f74fc4c166e2531108bf2b1ccfec0f1dc36b4d41a9da23f5069405):

| Controlled baseline load | Original SQL literal | Binary COPY |
| --- | --- | --- |
| No additional resident process | 680.5 MiB, 3.042 seconds | 522.5 MiB, 1.764 seconds |
| 380 MiB additional resident memory | 1024 MiB, memory-limit hits; write completed | 906.1 MiB, no limit hits/OOM; 1.985 seconds |
| 450 MiB additional resident memory | 1024 MiB, one OOM kill, connection lost | 983.4 MiB, no limit hits/OOM, successful write |

The added resident processes are isolated test pressure, not a measurement of
production's background load. The final pressure test reproduces an OOM in
the old path and demonstrates the new path preserving all input bytes under
the same limit/load. It is not a claim of unlimited future history capacity.

Tests cover real PostgreSQL Unicode round trips, unchanged-write row revisions,
concurrent increments, rollback after staged upsert, temporary-table isolation,
bounded availability retries, corrupt data failing closed, and no replay after
a deliberately lost commit acknowledgement. Release Gate also runs a separate
150 MiB PostgreSQL write acceptance with an actual 1 GiB kernel limit.

## Production acceptance

Pending until this exact source passes Release Gate, both services are deployed,
a full report/Autonomi/Pushover cycle completes under the 2 GiB runner limit,
and PostgreSQL logs confirm no new recovery incident during that run. Recover
the failed afternoon report through its ordinary scheduled report path, retaining
the original planned time and failed attempt and recording the actual late
completion. Do not claim the original report was delivered on time.
