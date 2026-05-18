# v18.6.3 — Core Stabilization & Refactor

- Added `utils.py` as single source of truth for `_safe_float`, `_clamp`, `_now_iso`, and `using_postgres`.
- Replaced duplicated helper definitions across modules with imports from `utils.py`.
- Replaced `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`.
- Centralized duplicate Pushover helper imports through `notifier.py` where applicable.
- Converted simple `except Exception: pass` blocks to warning logs where safely detectable.
- Added this changelog as a stabilization marker.

This release targets the structural issues found in the v18.6.2 code analysis: duplicated helper logic, hidden exceptions, deprecated UTC calls, and inconsistent shared behavior.
