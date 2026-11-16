# Autonomy selection lifetime

The Nov 16 morning scheduler exceeded its 2 GiB cgroup limit at 07:09:46 UTC.
The deployed version already contains PR 204. Logs show a 49.8 MiB encoded
restart document and 1495.7 MiB process RSS after decoding. The durable morning
preparation receipt contains 60 candidates and a completed five-strategy result.
The next operation collects execution evidence while retaining all three journals.

Release the verified bundle before preparation and execution-quote requests.
Retain detached current portfolio, settings, period pointer, approval reference,
cost policy and only the latest position quotes needed by the existing fallback.
The locked trading transaction must still re-read, verify and authorize the current
bundle and preserve retry identity. Paused accounts and completed retries retain
their established behavior. No historical records are deleted or rewritten.

## Approaches

Raising the paid instance memory limit only delays failure as the document grows.
Partitioning journals is the durable storage redesign, but changes replay and
transaction boundaries and needs separate migration validation. This incident fix
removes avoidable overlap without changing persistence or accounting semantics.
This choice is the implementer's call under the user's standing instruction to
finish fixes and deploy autonomously, rather than a new user design decision.

An additional 356 MB probe showed lifetime release alone still peaked above 2 GiB.
The final scope also streams the existing base64/zlib envelope and parses journal
events individually with the standard JSON decoder, then streams financial
mutation encoding into the identical envelope. Preserve JSON number/escape/key
semantics and validate checksum/termination before returning any data. No new
dependency or storage migration. A cancelled initial CI candidate was not merged.

This does not bound the growing monolithic journal or guarantee future full reads
fit 2 GiB. Record that limitation explicitly and retain issue 200 as open.
Validate object lifetime at both boundaries, semantic evidence equivalence,
real-Postgres authorization/retry tests, and private archive memory measurements.
