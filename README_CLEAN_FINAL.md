# CLEAN FINAL

Dette er én ren pipeline:

SIGNAL -> auto_trade() -> faktisk BUY/SELL i paper portfolio -> Pushover-varsel

Viktig:
- Gamle direkte signalvarsler i app.py er deaktivert.
- scanner_worker.py sender bare varsel hvis en faktisk trade skjer.
- Samme signal for samme ticker sendes ikke flere ganger.
- Database schema migreres automatisk.
- `take_profit`-feilen er fikset.

Etter deploy:
1. Deploy Web Service
2. Deploy Cron Job
3. I appen: trykk "Kjør DB schema fix"
4. Trykk "Nullstill anti-spam signalhistorikk"
5. Trykk "Reset paper portfolio"
6. Trigger Run på Cron Job

Sjekk logs:
Du skal se linjer som:
- Auto trade GOOGL: Paper BUY GOOGL
- Pushover status: 200 ...
eller:
- Auto trade GOOGL: Ingen trade
Da skal det ikke sendes varsel.
