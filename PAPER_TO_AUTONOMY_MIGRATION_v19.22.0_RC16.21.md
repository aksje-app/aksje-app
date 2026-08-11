# Kontrollert migrering fra Paper til Autonomi

## Nå: Observasjonell bro

Paper fortsetter å gjennomføre sine eksisterende simulerte handler. Samtidig sendes samme immutable tekniske snapshot til Autonomi som dokumentert input og benchmark. Ingen score eller ordre påvirkes av broen.

## Neste port

Før Paper kan avvikles må minst følgende dokumenteres over en representativ periode:

1. Begge motorer mottar samme ticker, pris, timestamp og tekniske indikatorer.
2. Forskjeller i BUY, SELL og HOLD får eksplisitt årsakskode.
3. Stop-loss, trailing stop, take-profit og RSI-exit har lik eller strengere sikkerhet i Autonomi.
4. Ingen dobbeltordre eller manglende exit ved restart, timeout eller leverandørfeil.
5. Pushover/outbox leverer idempotent og kan retryes uten duplikat.
6. Portefølje, kontanter, handler og replay kan avstemmes.
7. Paper kjøres først i SHADOW, deretter read-only benchmark, før eventuell avvikling.

Paper bør ikke slettes nå. Den er den eneste live-verifiserte ubetjente referansemotoren og brukes som sikker sammenligningsgrunnlag mens Autonomi beviser tilsvarende drift.
