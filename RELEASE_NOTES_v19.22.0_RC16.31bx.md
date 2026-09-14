# RC16.31bx - Stabilization and UI Workflow Closure

## Scope
RC16.31bx closes the ten-item stabilization list raised after the first BW live run without changing scoring, BUY thresholds, risk limits, Fresh Trend, Paper Trade or portfolio policy.

## Changes
1. **AUTONOMOUS duplicate closure** - canonical candidates are deduplicated before decision reduction. The richer/more decision-ready row wins deterministically, missing non-conflicting metadata is merged, and `CANONICAL_DEDUP` is logged. The final integrity gate remains active.
2. **Norway master preserved** - BW XOSL/MERK/XOAS official Euronext parsing is unchanged. Live `OFFICIAL_LIVE` still requires Render verification.
3. **Immediate Utkast start** - the first click persists the new execution id, forces an immediate rerun and shows STARTING/0% instead of the previous completed run.
4. **Durable cross-session polling** - progress polling follows the pending/durable execution id and rehydrates it from durable status instead of depending only on local Streamlit session state.
5. **Unified report file center** - Standard PDF, Technical PDF, JSON and Diagnostic ZIP are shown together. An on-demand complete ZIP contains the available four files.
6. **Readable blocker table** - `Første blocker` wraps over multiple lines and receives the largest column width; mobile gets horizontal overflow instead of truncated text.
7. **Ground-control semantics** - UI explicitly states that e.g. `16/80` is the intermediate deep-analysis baseline control set, not 80 final BUY candidates.
8. **Memory closure preserved** - BQ/BL cleanup and cgroup guards remain unchanged; combined ZIP is built only on explicit request.
9. **Distribution banner closure** - fresh service identities remain strict, while retired/stale identities are separated and no longer keep a false mismatch banner alive indefinitely.
10. **Production acceptance** - mandatory 08/14/22 and full Norway `OFFICIAL_LIVE` remain live acceptance checks after deployment; the release does not claim those external checks are proven locally.

## Changed runtime files
- `app_version.py`
- `report_integrity.py`
- `autonomy_overview.py`
- `market_intelligence.py`
- `runtime_identity.py`

## No policy change
No scoring, BUY, risk, Fresh Trend, Paper Trade, portfolio or learning promotion thresholds were changed.
