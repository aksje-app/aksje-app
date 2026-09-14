# v19.22.0 RC16.32e — Super Portfolio Multi-Market

## Formål
Super Portfolio har nå et eget markedsunivers som er uavhengig av `PRODUCTION_NORWAY_ONLY` i den autoritative produksjonskjeden.

## Markeder
- Norge
- Sverige
- Danmark
- Finland
- USA

## Viktige endringer
- Ny separat Super Portfolio market-feed lagres under `super_portfolio/market_pipeline.json`.
- Produksjonsstabilisering kan fortsatt være Norge-only uten å snevre inn Super Portfolio.
- Kandidater hentes og scores per marked med de eksisterende lokale markeds-/score-primitivene.
- Dyr evidensinnhenting (news/insider) er deaktivert i denne bounded market-feed-en for å holde CPU/minne og eksterne kall nede.
- Maks 25 kandidater enriches per marked som standard; de 12 beste per marked går videre til samlet Super Portfolio-rangering.
- Feed caches i 12 timer som standard for å hindre at hver Render-cron gjør 5-markedsarbeidet på nytt.
- Den autoritative `investment_pipeline/latest_run.json` overskrives ikke.
- Scheduler og manuell Super Portfolio-vurdering bruker den separate market-feed-en.

## Sikkerhet / isolasjon
Ingen reelle handler sendes. Super Portfolio forblir SHADOW. Eksisterende Norway-only scannerpolicy endres ikke.
