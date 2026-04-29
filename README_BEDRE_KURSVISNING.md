# Bedre kursvisning / near-real-time

Denne pakken legger til:

1. Raskere auto-refresh i appen
- Endret fra 5 minutter til ca. 1 minutt.

2. Tydelig kurskort
- Siste kurs
- Endring i kroner/dollar
- Endring i %
- Sist oppdatert datapunkt

3. Cron-anbefaling
For Render Cron Job kan du bruke:

```text
*/1 * * * *
```

Dette kjører scanner hvert minutt.

4. Live-ish, ikke ekte streaming
Dette er near-real-time basert på datakilden, ikke sekund-for-sekund WebSocket/livefeed.
Ekte live streaming kan bygges senere med betalt/proff datafeed.
