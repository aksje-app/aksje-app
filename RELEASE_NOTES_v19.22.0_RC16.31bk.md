# RC16.31bk - Norway Scope and Trend UI Closure

## Purpose
Close the manual-run market-scope defect found in RC16.31bj and complete the agreed trend-detail presentation without changing investment thresholds.

## Production changes
- Manual one-off market selection now updates both `markets` and `market_profile`.
- `PRODUCTION_NORWAY_ONLY=true` is enforced as a second runtime guard for every manual execution path, including Report Center/Overview shortcuts. The saved job profile is not mutated.
- Norway-only draft runs are labelled `Utkast – Norge` in the effective execution/report instead of retaining a misleading three-market runtime label.
- During Norway stabilization the orchestrator market selector exposes only Norway; set `PRODUCTION_NORWAY_ONLY=false` to reopen all configured choices later.
- Trend details are available for candidates 1-10 in the program.
- Trend display defaults to 20 trading days, with a 60d switch, SMA20, SMA50 and RSI(14).
- Trend detail text also shows 5d/20d/60d return, volume vs 20d average, distance from 20d high, first discovery and rank change.
- Technical PDF trend charts use the final 20 trading days with price/SMA20/SMA50 while retaining 60d return in the evidence text.
- The technical report no longer claims 70/20/10 rotation when the active path is full-universe coarse scanning; it states that no such rotation is used at that stage.

## Not changed
- Investment-score thresholds
- Risk ceiling
- Liquidity/data-quality gates
- Portfolio rules
- Trading authorization
- OOM/learning memory fix from RC16.31bj
