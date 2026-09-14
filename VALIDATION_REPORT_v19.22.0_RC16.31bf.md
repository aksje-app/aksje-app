# Validation report v19.22.0-rc16.31bf

## Utført
- Python compile: PASS for `app_version.py`, `candidate_market_data.py`, `trend_intelligence.py`, `scanner_worker.py`, `market_intelligence.py`.
- RC16.31bf trend/discovery targeted tests: PASS.
- Eksisterende kompakt PDF-regresjon: PASS.
- Eksisterende live-report closure-regresjon: PASS.
- Samlet målrettet kjøring: 14 passed, 0 failed.

## Verifiserte kontrakter
- Faktisk markedsserie brukes til 60-dagers trendgraf; ingen syntetisk kursserie genereres.
- 5/10/20/60d, SMA20/SMA50, volum/20d og toppavstand beregnes fra samme historikk.
- Trend receipt kan annotere kandidat uten aa endre `investment_score`.
- `production_scoring_changed` er eksplisitt false.
- Automatisk Norge-only-modus er reversibel med `PRODUCTION_NORWAY_ONLY=false`; manuelle markedsvalg er ikke fjernet.

## Begrensning
Full pytest-suite er ikke hevdet som kjort i dette byggmiljoet. Miljoet mangler `yfinance`, slik at bred samling av tester som importerer analysemodulen ikke kan kjores uten runtime-avhengighetene. Render-liveaksept gjenstaar.
