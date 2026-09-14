# Deploy RC16.31bl

1. Copy the four files from the clean DELTA to the repository root.
2. Commit and let Render deploy web + scheduler from the same commit.
3. Keep `PRODUCTION_NORWAY_ONLY=true` during Norway production stabilization.
4. Start one manual Norway draft and verify that progress updates without manual browser refresh.
5. Open one archived report, enable `Last rapportdetaljer`, refresh the browser, and verify the same report remains open.
6. Verify that the detail panel appears immediately and that large files are fetched only after `Klargjør rapportfiler`.
7. Inspect one Top-10 trend chart: 20d should be visibly scaled around the actual move, with SMA20/SMA50 and a separate RSI 0-100 panel with 30/70 references.
8. After the manual report completes, inspect the diagnosis/log for `report:memory_guard:before_final_export` and `report:memory_cleanup:after_final_gate`. The run must retain safe headroom below the 2 GiB Render limit.

Rollback: redeploy RC16.31bk.
