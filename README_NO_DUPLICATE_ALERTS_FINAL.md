# No duplicate alerts final

Fikser Pushover-spam:
- Samme ticker + samme signal sendes bare én gang.
- Nytt varsel sendes bare ved signalendring, f.eks HOLD -> BUY eller BUY -> SELL.
- Gamle direkte signalvarsler forsøkes deaktivert.
- Bruk knappen "Nullstill anti-spam signalhistorikk" hvis du vil starte varsling på nytt.

Viktig:
DATABASE_URL må ligge på både Web Service og Cron Job for felles anti-spam.
