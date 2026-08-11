# Deploy v19.22.0-rc16.28

1. Last opp alle filer fra FULL-pakken, inkludert `assets/`.
2. Commit og push til GitHub-grenen Render bruker.
3. Bekreft at både webtjenesten og cron-jobben bygger samme commit.
4. Cron-kommandoen skal være `python scheduled_runner.py`.
5. Behold eksisterende hemmelige miljøvariabler. Ikke last opp `.env`.
6. Etter deploy: rediger og lagre de faste rapportprofilene du vil bruke. RC16.28 overstyrer dem ikke automatisk.
7. Kjør kontrollene i `ACCEPTANCE_v19.22.0_RC16.28.md`.

`assets/` skal med til GitHub fordi PDF-fontene og distribusjonsressursene brukes i produksjon.
