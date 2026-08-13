# Deploy – v19.22.0-rc16.31d

1. Bruk FULL-pakken ved komplett deploy. DELTA kan legges over en komplett RC16.31c-installasjon.
2. Bekreft at appen viser `v19.22.0-rc16.31d`.
3. Kontroller de tre aktive jobbene i rapportplanleggingen: morgen 08:00, ettermiddag 14:00 og kveld 22:00.
4. Kontroller i Render at bare én `aksje-app-paper-scanner` er aktiv.
5. Etter neste Paper-cron: bekreft nytt heartbeat. Skannedato skal bare endres dersom en virkelig skann ble fullført.
6. Etter neste daglige vedlikehold: kontroller `maintenance/storage_retention.json`. Status skal være `COMPLETED`, med `usage_before` og `usage_after`.
7. Ingen manuell SQL-rydding eller VACUUM kreves ved deploy. PostgreSQL kan bruke noe tid før frigjort plass vises i lagringsmåleren.

Ved normal drift skal Pushover bare vise de tre faste rapporttidene. `AUTOMATISK 1/4–4/4` skal bare vises når rapporttest er eksplisitt aktivert.

