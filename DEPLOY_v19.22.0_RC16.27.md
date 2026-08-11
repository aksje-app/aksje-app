# Deploy v19.22.0-rc16.27

1. Legg inn alle filer fra FULL-pakken, inkludert `assets/`.
2. Commit og push til samme GitHub-gren som Render-tjenestene bruker.
3. La både webtjenesten og `aksje-app-report-scheduler` bygge samme commit.
4. Behold eksisterende hemmelige miljøvariabler. `NEWSAPI_DAILY_BUDGET` kan stå til 60; programmet håndhever likevel en operativ grense på 50.
5. Kontroller cron-kommandoen `python scheduled_runner.py` og tidsplanen hvert 30. minutt.
6. Kjør RC16.27-akseptansen i `ACCEPTANCE_v19.22.0_RC16.27.md`.

Ikke kopier `.env` til GitHub. `assets/` skal lastes opp fordi PDF-fontene og øvrige distribusjonsressurser er del av programmet.
