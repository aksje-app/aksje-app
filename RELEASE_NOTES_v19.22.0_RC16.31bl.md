# RC16.31bl - UI Stability and Manual Report Memory Closure

## Purpose
Close three production-readiness regressions observed in RC16.31bk: stale live progress in the Autonomy/Report UI, slow/non-persistent archive details, and unsafe memory headroom at the end of manual full-report runs. The trend presentation is also corrected after live visual review.

## Production changes
- Autonomy/report progress polling now compares the in-process status snapshot with the atomic local status mirror and renders whichever is newest.
- Live progress refreshes every 2 seconds. The main percentage remains monotonic total progress; the work counter is explicitly labelled phase progress.
- Report-detail selection is persisted in the browser URL (`report_detail=<run_id>`), so a normal/manual page refresh reopens the same report panel.
- Opening report details is now lightweight. Large canonical JSON/PDF/text data is fetched only after explicit `Klargjør rapportfiler`.
- Closing a prepared report detail releases the single-report cache and trims process memory.
- Trend charts use Plotly with a normalized start index of 100 and a tight y-axis range, so 20d direction is visible instead of visually flattened.
- Trend details retain the 20d/60d switch, SMA20/SMA50, RSI(14) with visible 30/70 reference levels, current trend metrics and first-discovery/selection markers when dates are available.
- Manual report finalization releases Shadow duplicates and the large final PDF/JSON/text validation buffers before the COMPLETE callback.
- A 1450 MB memory guard runs before final artifact serialization. If pressure is already unsafe, the report fails in a controlled validation state instead of pushing the Render web container into a 2 GiB OOM kill.
- New memory breadcrumbs record the pre-final guard and post-final cleanup.

## Not changed
- Norway-only stabilization from RC16.31bk
- Investment-score thresholds
- Risk ceiling
- Liquidity/data-quality gates
- Portfolio rules
- Trading authorization
- RC16.31bj learning-memory closure
