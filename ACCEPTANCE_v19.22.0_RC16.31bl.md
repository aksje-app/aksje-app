# Acceptance RC16.31bl

## Live progress
- No manual browser refresh is required to see current phase/ticker/progress.
- Main progress percentage never moves backwards.
- `Fasefremdrift` may restart for each phase and is clearly separate from total percentage.
- Heartbeat and real-progress timestamps continue to identify a genuinely stalled worker.

## Report Center
- `Last rapportdetaljer` remains enabled for the selected report after a browser refresh.
- Opening the detail panel itself is fast and does not fetch the complete canonical report.
- PDF/JSON/text/trace are fetched only after `Klargjør rapportfiler`.
- Closing details releases the prepared single-report cache.
- Old/failed replay-export state does not block ordinary archive detail viewing.

## Trend UI
- Top 1-10 keep 20d/60d switching.
- Price/SMA chart is normalized to start index 100 and uses a tight visible range.
- RSI has a fixed 0-100 scale and 30/70 reference levels.
- First-discovery and selected-candidate markers appear when their dates fall inside the visible period.

## Manual report memory
- A pre-final memory guard is logged before final PDF/JSON/text serialization.
- A post-final memory cleanup breadcrumb is logged before COMPLETE.
- A normal Norway-only manual report must finish with materially more than the ~10 MB headroom observed in RC16.31bk.
- Unsafe memory pressure must produce a controlled final-validation failure, not a Render OOM kill.

## Invariants
- Norway-only stabilization remains active while `PRODUCTION_NORWAY_ONLY=true`.
- No investment, risk, liquidity, portfolio or trading threshold changes.
