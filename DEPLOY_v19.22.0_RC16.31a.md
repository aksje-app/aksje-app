# Deploy – v19.22.0-rc16.31a

Deploy `render.yaml` slik at disse tre tjenestene finnes:

1. `aksje-app` – web.
2. `aksje-app-report-scheduler` – rapport-cron hvert 30. minutt.
3. `aksje-app-paper-scanner` – Paper-skanner hvert 30. minutt.

Den nye Paper-tjenesten skal ha `DATABASE_URL`, markedsdatanøkkel og Pushover-hemmeligheter. `PAPER_TRADING_ENABLED=true` gjelder bare Paper-skanneren; web og rapport-cron står fail-closed med `false`.

Etter deploy kontrolleres:

- Programversjon viser `v19.22.0-rc16.31a` i app og Pushover.
- Paper-status går gjennom `RUNNING` og `COMPLETED`, eller viser `MARKET_CLOSED` når alle markeder er stengt.
- `last_successful_scan_at` endres bare etter en reell skann.
- Det finnes nøyaktig én aktiv Paper-cron i Render. En eventuell eldre, manuelt opprettet Paper-cron skal deaktiveres for å unngå dobbelt oppsett.
- Faste rapporter står på 08:00, 14:00 og 22:00 Europe/Oslo.
