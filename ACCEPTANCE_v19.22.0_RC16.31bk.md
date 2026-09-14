# Acceptance RC16.31bk

## Market scope
- UI shows Norway as the only selectable market while `PRODUCTION_NORWAY_ONLY=true`.
- Manual draft status reports one market and Norway.
- Generated run JSON contains `markets=["Norge"]` and an effective custom/Norway market profile, not CORE.
- PDF/technical PDF show Norway only under planned/active market coverage.
- No Sweden/USA symbol may enter the active scan/candidate ranking for the Norway-only run. Existing foreign portfolio holdings may still be shown as existing positions and must remain clearly separated from active scanning.

## Trend UI
- Trend details exist for ranks 1-10.
- 20d is default; 60d can be selected.
- Price chart shows price, SMA20 and SMA50.
- RSI(14), volume/20d average, distance from 20d high, first discovery and rank change are visible when data exists.
- Technical PDF uses a 20d trend chart and retains 60d return in text.

## Stability
- RC16.31bj learning-memory closure remains intact.
- Scheduler completes without OOM.
- No investment/risk/trading thresholds change.
