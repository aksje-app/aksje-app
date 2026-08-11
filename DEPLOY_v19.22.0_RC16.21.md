# Deploy v19.22.0-rc16.21

1. Last opp FULL-pakken til GitHub, inkludert `assets/`.
2. Kontroller at Render Blueprint oppdaterer cronservicen `aksje-app-report-scheduler`.
3. Cronkommando skal være `python scheduled_runner.py`, med intervall `*/5 * * * *`.
4. Cronservicen skal ha `REPORT_SCHEDULER_ENABLED=true`; webservicen skal ha `false`.
5. `DATABASE_URL`, Pushover-nøkler og øvrige API-nøkler må finnes på cronservicen.
6. Deploy/restart web og cron.
7. Kontroller Drift etter første femminutterskjøring: execution mode skal være `AUTHORITATIVE_UNATTENDED_CRON`.

Paper sin eksisterende separate cron beholdes i denne fasen. Ikke opprett en ekstra Paper-cron dersom én allerede finnes.
