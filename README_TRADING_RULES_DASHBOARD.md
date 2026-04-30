# Trading Rules Dashboard

Nytt:
- Egne bokser/slidere i sidepanelet for Kjøp, Hold og Salg.
- Kan lagres direkte fra appen.
- Hvis `DATABASE_URL` er satt, lagres reglene i databasen.
- Da bruker både Web App og Cron Job samme regler.

Regler som kan endres:
KJØP:
- Min BUY score
- Min confidence
- Maks RSI for kjøp
- Maks trades per dag

HOLD:
- Min hold-dager
- Ignorer små svingninger %

SALG:
- SELL/AVOID exit
- Stop-loss %
- Take-profit %
- RSI exit nivå
- RSI må falle etter topp

Viktig:
Legg `DATABASE_URL` inn på både Web Service og Cron Job for felles regler.
