# Akseptanse RC16.31bt

PASS krever:
- Runtime-versjon `v19.22.0-rc16.31bt` på alle Render-tjenester.
- `NORWAY_UNIVERSE status=OFFICIAL_LIVE` ved første vellykkede livehenting.
- Offisielt univers >= 150 instrumenter.
- `by_exchange` inneholder Oslo Børs, Euronext Growth Oslo og Euronext Expand Oslo.
- Rapportens `source_authoritative_exchange_master=true`.
- Rapporten viser ikke `Reell dekningsfeil: Norge` etter vellykket livehenting.
- Ingen regresjon i BQ-minne/terminalstatus eller BS-evidenssemantikk.

FAIL dersom kun 82 aksjer / `Packaged Norway fallback` / `FALLBACK_UNVERIFIED` brukes.
