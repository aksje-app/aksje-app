# Super Portfolio Task List — RC16.32j

## Completed in this release
- [x] Candidate persistence: 2 consecutive fresh qualifying runs by default before ordinary challenger replacement.
- [x] Regime-aware thresholds: CALM is more patient, NORMAL uses baseline, STRESSED reacts faster.
- [x] Candidate data-coverage score and entry gate.
- [x] Broad USA discovery beyond S&P 500: S&P 500 + 400 + 600 + Nasdaq-100, deduplicated.
- [x] Resource-safe chunking for broad USA coarse scan.
- [x] Separate `ai_thinks` and `shadow_executed` state/snapshot fields.
- [x] Separate UI panels for AI THINKS and SHADOW EXECUTED.
- [x] Visible Regime Policy panel.
- [x] Visible Candidate Entry Gate panel.
- [x] Release/version/checklist/docs update to RC16.32j.

## Release blockers
None from the RC16.32i highlighted backlog.

Production observation after deploy is recommended to confirm live constituent-source availability and Render resource behavior with the broader USA first pass; this is operational validation, not unfinished implementation.

## Optional future improvements (not release blockers)
- [ ] Add exchange-level USA source telemetry (NYSE/Nasdaq listing source and constituent-source success counts).
- [ ] Learn persistence/confidence/margin parameters from controlled historical outcomes, approval-gated.
- [ ] Add a compact SP decision timeline comparing AI THINKS, gate result and SHADOW EXECUTED over time.
