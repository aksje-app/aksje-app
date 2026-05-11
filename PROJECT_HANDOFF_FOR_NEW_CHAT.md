# Project handoff – v18.5.29 Persistent Storage Hardening

## What changed

- Updated the single source of truth in `app_version.py` to `v18.5.29`.
- Hardened `services/storage_service.py`:
  - Postgres/DATABASE_URL remains the primary persistent backend.
  - Local JSON/JSONL is explicitly treated as dev/test fallback.
  - Added storage health/status helpers.
  - Added safer storage key normalization.
- Added `persistent_storage_status.py` for compact storage diagnostics.
- Added Services/persistent-storage status in AI Kontrollsenter.
- Routed more runtime state away from root JSON files and through StorageService fallback paths:
  - paper trading fallback
  - app settings fallback
  - trading rules fallback
  - strategy-test logs and profiles
  - signal alert anti-spam state
- Existing StorageService-backed flows remain in place for:
  - forecast logs
  - learning stats
  - forecast alerts / event-risk alerts
  - score explanations
  - watchlist
  - active Smart Universe
  - Smart Universe results

## Expected version in UI

```text
Professional Trading Workspace v18.5.29
```

## Storage expectation on Render

```text
DATABASE_URL configured → Postgres/StorageService active
DATABASE_URL missing → local JSON fallback only for dev/test
GitHub data folders → only .gitkeep placeholders
```

## Verified locally

```bash
python -m compileall .
pytest -q
```

Expected result at handoff: all tests pass.

## Next planned work

Punkt 7: Legacy cleanup, after Render smoke-test confirms storage status and core features still work.
