# Deploy v19.22.0-rc16.23

1. Deploy FULL, eller DELTA kun over komplett RC16.22.
2. Behold web-scheduler deaktivert og Render Cron på `*/30 * * * *`.
3. Kontroller at både web og cron bruker samme `DATABASE_URL`.
4. Kontroller `REPORT_PUBLIC_BASE_URL`; gammel `/app/static/reports`-sti er tillatt som input fordi RC16.23 henter ut domenet automatisk.
5. Åpne Fullt rapportsenter → Rapporter, historikk og avansert → Planlegging og avanserte innstillinger.
6. Aktiver 30-minutters rapporttest eller trykk «Kjør én test umiddelbart».
7. Åpne Pushover-lenken uten innlogget nettleserøkt og sammenlign rapport-ID.
8. Slå av testmodus når akseptansen er bestått.
