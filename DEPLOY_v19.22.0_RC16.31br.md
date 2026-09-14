# Deploy – RC16.31br

## GitHub / Render
Bruk den rene DELTA-pakken og erstatt de ni produksjonsfilene i repository-roten. Commit og push til samme produksjonsgren som Render følger.

Ingen database-migrasjon eller ny miljøvariabel er obligatorisk.

## Første live-kontroll
Etter deploy skal app, scheduler og Paper scanner rapportere `v19.22.0-rc16.31br`.

Kjør eller vent på en Norge-rapport og kontroller:

1. Norge-masterstatus er `OFFICIAL_LIVE` eller `OFFICIAL_LAST_KNOWN_GOOD` / `OFFICIAL_LAST_KNOWN_GOOD_STALE` fra en tidligere verifisert offisiell master.
2. `source_authoritative_exchange_master=true`.
3. Alle tre segmenter finnes i børsfordelingen: Oslo Børs, Euronext Growth Oslo og Euronext Expand Oslo.
4. Offisielt univers er vesentlig større enn den gamle 82-listen og `coverage_failure=false` når alle offisielle symboler ble raskt skannet.
5. Fresh Trend-screeningens stage-1-dekning tilsvarer hele Norge-masteren, mens utvidet analyse er en mindre, kontrollert delmengde.
6. Paper scanner viser samme Norge-universstørrelse og roterer en bounded batch uten å overskride `SCANNER_MAX_TICKERS`.
7. Børs/markedssegment følger kandidater i UI/rapport/Paper Trade.

## Fail-safe
Hvis live Euronext-oppslag feiler før en verifisert master er etablert, er `FALLBACK_UNVERIFIED` forventet. Ikke godkjenn komplett Norge-dekning før en offisiell master er verifisert på Render.
