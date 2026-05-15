# v18.5.89 – UI/Data Trust Batch G

## Formål
Kontrollert stabiliseringspatch for D5/D7 og resterende D6-forklaringer uten å omskrive analysemotorene.

## Endret
- La til `ui_trust.py` som dependency-light helper for:
  - datakvalitet: `LIVE`, `CACHED`, `FALLBACK`, `PARTIAL`, `STALE`, `MISSING`
  - cache-/stale-age-beregning
  - konsistente blokkeringsforklaringer
  - UI consistency tokens
- Oppdaterte Safe build-panelet med **UI/data trust**-seksjon.
- La inn lavrisiko CSS-tokens for knapphøyde, statuskort og blokknotater.
- Top Picks viser nå enkel datakvalitetslinje basert på marked/cache-situasjon.
- Batch-kjøp viser warning når en eller flere handlinger blokkeres, i stedet for alltid suksess.
- Trading-block meldinger bruker tydeligere format: `Kjøp blokkert: ...`.
- Feature registry og protected zones er oppdatert med UI/data trust.
- Changelog og app-versjon oppdatert til `v18.5.89`.

## Ikke endret
- Ingen omskriving av analyse-, forecast-, portfolio- eller risk-motorer.
- Ingen endring av beslutningslogikk for scoring/rangering.
- Ingen endring av reelle Pushover-credentials eller API-flyt.

## Tester
- `py_compile` OK
- Full test-suite: `210 passed`
