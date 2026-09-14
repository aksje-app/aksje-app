# Super Portfolio – ny oppgaveliste RC16.32i

## Ferdig i denne releasen
- ✅ Freshness gate: ingen ordinær Shadow-rebalansering på gammel market-feed.
- ✅ Same-run audit: decision run ID følger råd, endringer, snapshot og impact.
- ✅ Confidence gate: ordinær rebalansering blokkeres under 65/100.
- ✅ Replacement hysteresis: eksisterende posisjon kan beholdes innen rank-buffer når challenger-forspranget er <2.0 scorepoeng.
- ✅ Reason codes: BUY/ADD/REDUCE/SELL får eksplisitt maskinlesbar årsak og forklaring.
- ✅ Before/after impact: Health, risk, correlation og turnover sammenlignes før mulig rebalansering.
- ✅ Scheduler: når ordinær AUTO-rebalansering er due, tvinges fersk SP market-feed før beslutningen.
- ✅ Hard stop: fortsatt umiddelbar og bypasser ordinære rebalance-gates.

## Neste kandidater / backlog – ikke markert som ferdig
- ⬜ Candidate persistence: challenger må være sterk i 2–3 ferske scans før normal utskifting.
- ⬜ Regime-aware thresholds: hysteresis/confidence-terskler tilpasses markedsregime.
- ⬜ Per-stock data coverage gate: minimum datadekning før aksjen kan erstatte en eksisterende posisjon.
- ⬜ USA-univers utvidelse utover dagens S&P-500-baserte kilde, med deduplisert Nasdaq/NYSE-bredde.
- ⬜ UI-kort for `AI THINKS` versus `SHADOW EXECUTED` med gate-reason synlig uten diagnose-ZIP.
