# Deploy v19.22.0-rc16.22

1. Last opp FULL-pakken, eller DELTA-pakken kun over komplett RC16.21.
2. Kontroller at webtjenesten har `REPORT_SCHEDULER_ENABLED=false` og `RUNTIME_BACKGROUND_ENABLED=false`.
3. Kontroller at `aksje-app-report-scheduler` kjører `python scheduled_runner.py` på Standard 2 GB.
4. Bruk cronplan `*/30 * * * *` under live-akseptansen.
5. Sett `REPORT_MAINTENANCE_INTERVAL_MINUTES=360`.
6. Behold `DATABASE_URL`, Pushover- og dataleverandørnøkler i Render-miljøet; de skal ikke ligge i GitHub.
7. Deploy, og ikke åpne appen før den neste planlagte rapporten er kontrollert i Render Logs og Pushover.

Godkjenn når cron viser `COMPLETED`, rapporten finnes med samme rapport-ID i arkivet og Pushover, og ingen duplikatrapport er opprettet.
