# Deploy v19.22.0-rc16.24

1. Deploy FULL, eller DELTA kun over komplett RC16.23.
2. Behold Render Cron på `*/30 * * * *` og samme `DATABASE_URL` for web og cron.
3. `RENDER_EXTERNAL_URL` skal være webtjenestens rotadresse. `REPORT_PUBLIC_BASE_URL` kan fortsatt inneholde en gammel sti; bare domenet brukes.
4. Vent til webtjenesten viser v19.22.0-rc16.24.
5. Kjør én umiddelbar Autonomi-rapporttest under Fullt rapportsenter.
6. Kontroller at den nye Pushover-lenken åpner PDF uten innlogging.
7. Gamle Pushover-meldinger beholder sin gamle, ugyldige URL og er ikke en gyldig test av RC16.24.
