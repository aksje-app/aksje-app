# Release notes - RC16.31by

## Report Semantics and Final Export Memory Closure

RC16.31by is a focused stabilization release on top of RC16.31bx/bw. It does not change scoring, BUY thresholds, risk thresholds, Fresh Trend calculations, Paper Trade rules, or portfolio limits.

### Fixed

1. **Closed-market status now shows the next ordinary opening**
   - Norway at 02:10 now reports `Åpner 09:00` instead of only `02:10 · Utenfor ordinær åpningstid`.
   - After market close it reports the next weekday opening, e.g. `Åpner tor 09:00`.
   - The technical PDF now uses `Neste ordinære åpning` rather than repeating the local clock.

2. **Night draft mission no longer hard-codes USA**
   - Nattrapport/overnight mission is now market-neutral and Norway-safe.
   - It prepares the next Norwegian trading day and may consider relevant global signals without claiming that the job is a USA report.

3. **Norway exchange metadata is rehydrated before report publication**
   - Canonical `.OL` candidates missing exchange/ISIN metadata are filled from the durable authoritative Euronext master.
   - Report finalization never performs a new Euronext network call for this enrichment.
   - Fresh Trend display falls back to the canonical candidate exchange metadata when a trend receipt itself lacks `exchange_name`.

4. **Full-universe report funnel is explicit**
   - The old discovery-composition table is suppressed when a complete authoritative Norway master is active.
   - Technical report instead shows separate stages: official universe scanned, technical/Fresh screen, active deep analysis, evidence control, and report candidates including existing positions.
   - This prevents 294 / 100 / 60 / 20 / 73 from being misread as conflicting universe sizes.

5. **Evidence quality semantics are consistent**
   - Visible quality deviations use `evidence-ready / evidence-controlled`, not the obsolete `ready / 60` denominator.
   - The legacy all-candidate coverage field remains for JSON compatibility but is explicitly labeled as legacy.
   - Weak/unverified source counts explicitly state when they include candidates that were not prioritized to full evidence control.

6. **Final artifact memory gate no longer treats reclaimable Linux file cache as Python memory pressure**
   - Final report export now runs allocator cleanup plus best-effort cgroup reclaim first.
   - The final export guard evaluates non-reclaimable memory (RSS / anon / shmem / kernel) while still fail-closing if the cgroup is within 3% of its hard limit.
   - Scheduler callers keep the previous total-cgroup behavior unless they explicitly opt into file-cache-aware mode.
   - This closes the BX case where a large file cache could create a false controlled stop before final artifacts even though process RSS remained healthy.

### Preserved from BX/BW

- Complete Norway exchange master / Euronext parsing.
- Canonical candidate dedup before AUTONOMOUS release gate.
- Immediate Utkast STARTING handoff and durable polling logic.
- Unified report file center: standard PDF, technical PDF, JSON, diagnostic ZIP and optional complete ZIP.
- Wrapped blocker text.
- Stale runtime identity handling.
- BQ/BL memory cleanup architecture.
