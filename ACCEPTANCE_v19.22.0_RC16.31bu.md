# Acceptance RC16.31bu

PASS when all are true:
1. Runtime identities are all `v19.22.0-rc16.31bu` on one commit.
2. Every Euronext attempt is observable in Render as `NORWAY_UNIVERSE_ATTEMPT`.
3. On success, final status is `OFFICIAL_LIVE` with >150 rows and exchange distribution.
4. On failure, final status may remain `FALLBACK_UNVERIFIED`, but the exact source failure is present in durable diagnostics and in the manual diagnosis ZIP.
5. Diagnosis includes both Norway-universe JSON files.
6. Existing terminal-status, memory, evidence semantics and Norway-only scanner policy remain unchanged.
