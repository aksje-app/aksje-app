# Deploy RC16.31bm

1. Deploy the clean DELTA to the repository root.
2. Confirm web and report-scheduler run the same commit and `v19.22.0-rc16.31bm`.
3. Keep `PRODUCTION_NORWAY_ONLY=true` during production stabilisation.
4. Run one Norway-only manual draft.
5. Verify `trend_discovery.version=v19.22.0-rc16.31bm` and that `early_signal_watchlist` is present.
6. Verify a strong technical setup can appear on the early-signal watchlist even if it is outside overall investment Top 10.
7. Verify each signal explanation includes what supports continuation, what confirms it next, and what weakens/invalidates it.
8. Verify no production threshold, risk gate or trade-authority value changed.
9. Continue normal memory/OOM acceptance monitoring from RC16.31bl.
