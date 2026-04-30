# Market hours + database anti-spam

Nytt:
- Ingen scanning/varsler når alle markeder er stengt
- Hver ticker sjekkes mot sitt marked:
  - USA
  - Norge
  - Sverige
- Anti-spam lagres i database via `DATABASE_URL`
- Samme BUY sendes ikke igjen og igjen
- Cooldown styres av `ALERT_COOLDOWN_MINUTES`

Anbefalte Environment Variables på både Web Service og Cron Job:

```text
DATABASE_URL=postgres://...
ALERT_COOLDOWN_MINUTES=30
ALLOW_REPEAT_ALERTS_AFTER_COOLDOWN=false
```

Hvis `DATABASE_URL` mangler, brukes lokal fallback-fil, men da deler ikke Web App og Cron Job signalhistorikk.
