# Acceptance - RC16.31bx

## Local/build acceptance
- [x] Changed Python files compile.
- [x] BX focused tests pass.
- [x] Autonomy overview regression tests pass.
- [x] Current BW parser tests (excluding historical version-lock assertion) pass.
- [x] BQ/BL behavior tests (excluding historical version-lock assertions) pass.
- [x] Canonical report/decision reduction regression tests pass except one unrelated historical wording assertion from AB.
- [x] Clean DELTA contains runtime files only.

## Render live acceptance - required before production-ready
- [ ] First Utkast click shows STARTING immediately on PC and mobile.
- [ ] Progress continues without manual F5 through terminal state.
- [ ] AUTONOMOUS completes even if duplicate candidate ingress occurs; no canonical duplicate ValueError.
- [ ] Report file center exposes Standard PDF, Technical PDF, JSON and Diagnostic ZIP together.
- [ ] Complete ZIP downloads and passes ZIP integrity.
- [ ] `Første blocker` text is fully visible.
- [ ] Norway master reaches `OFFICIAL_LIVE` and no 82 fallback is used as complete coverage.
- [ ] 08:00/14:00/22:00 scheduled reports complete without OOM/recovery failure.
- [ ] web/scheduler/paper scanner share the same fresh version+commit and stale identities do not keep a false red banner.
- [ ] Multiple consecutive normal runs remain within the 2 GiB Render memory limit.
