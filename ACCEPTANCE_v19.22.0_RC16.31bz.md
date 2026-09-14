# Acceptance RC16.31bz

## Required live checks
- [ ] Web/scheduler/paper scanner all show `v19.22.0-rc16.31bz` on one commit.
- [ ] Manual Utkast reacts immediately and keeps auto-refreshing on desktop and mobile.
- [ ] Same execution ID has monotonic visible progress; no backward percentage.
- [ ] EXTENDED_ANALYSIS produces visible progress after MARKET_DATA rather than a long flat spot.
- [ ] EVIDENCE/INSIDER/NEWS/SHORT and baseline controls continue to move progress before SCORING.
- [ ] AUTONOMOUS advances within 84-91% when its substages report work units.
- [ ] REPORT/COMPLETE reaches 100% and artifacts are persisted.
- [ ] Norway universe remains 294/294 authoritative; no regression to fallback.
- [ ] No change to scoring, BUY threshold, risk, Fresh Trend, evidence budget or portfolio logic.

## Production gate
Do not mark production-ready from local tests alone. One full live Utkast and at least one ordinary scheduled 08:00/14:00/22:00 run should complete without OOM, stale progress, or artifact failure.
