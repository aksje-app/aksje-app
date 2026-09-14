# RC16.31bt - Euronext Official Live Source Closure

## Formål
Lukke BR-feilen der Render falt tilbake til det gamle 82-aksjeuniverset fordi den offisielle Euronext-masteren ikke ble hentet live.

## Endringer
- Primær livekilde er nå Euronexts nåværende offentlige product-directory for Oslo: XOSL + MERK + XOAS.
- Parseren leser Name / ISIN / Symbol / Market fra den server-renderte produktlisten og paginerer til hele Oslo-universet er samlet.
- Den eldre `/en/pd/data/stocks` JSON-kilden beholdes som kompatibilitetsreserve.
- Euronext-session primes mot den offentlige Oslo-listen før univershenting.
- Livehenting krever minst 150 verifiserte Oslo-aksjer før snapshot kan erstatte last-known-good.
- Alle henteforsøk logges med strategi, HTTP-status og antall rader.
- Render-logg får eksplisitt `NORWAY_UNIVERSE status=...` for OFFICIAL_LIVE, stale last-known-good eller FALLBACK_UNVERIFIED.
- Fallback beholder konkret hente-feil i `error` slik at årsaken ikke lenger forsvinner i rapport/diagnose.
- Ingen endring i scoring, BUY-terskler, risiko, Fresh Trend, Paper Trade-rotasjon eller evidenslogikk.

## Viktig live-akseptanse
Før BT godkjennes skal Render vise `NORWAY_UNIVERSE status=OFFICIAL_LIVE` med et antall klart over 150 og børsfordeling for Oslo Børs, Euronext Growth Oslo og Euronext Expand Oslo.
