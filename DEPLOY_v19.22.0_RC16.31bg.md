# Deploy RC16.31bg

1. Deploy the DELTA to the same GitHub branch used by both web and report scheduler, or deploy the FULL package if a clean replacement is preferred.
2. Keep `PRODUCTION_NORWAY_ONLY=true` (or leave it unset; true is the default during stabilization).
3. Recommended scheduler memory settings on the 2 GiB Render service:
   - `SCHEDULER_MEMORY_SOFT_LIMIT_MB=1450`
   - `SCANNER_MEMORY_SOFT_LIMIT_MB=1700` may remain set; the effective scanner limit is capped at 1450 MB by RC16.31bg.
4. Do not increase Render RAM to mask the defect before the live memory checkpoints have been reviewed.
5. After deploy, trigger one cron run and collect a fresh background diagnostic.

Expected evidence:
- runtime identity `v19.22.0-rc16.31bg` on scheduler and web,
- scanner configuration `automated_markets=["NORGE"]` while Norway-only is active,
- scheduler state is not killed by Render OOM,
- `memory_observations` contains checkpoints from start through the executed phases,
- new strategy persistence uses `repositories/strategy_decisions/items/*` and `repositories/strategy_runs/items/*` plus lightweight indexes.
