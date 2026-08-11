# Deploy v19.22.0 RC16.18

1. Deploy FULL-pakken, eller legg DELTA-pakken oppå RC16.17.
2. Restart Render-tjenesten.
3. Bekreft `v19.22.0-rc16.18`.
4. Gjør én hard nettleseroppdatering (`Ctrl+F5`).
5. Rapporter skal åpne med «Hurtigarkiv og komplett ZIP» valgt.
6. Kontroller at full scheduler-, historikk- og jobbprofilvisning ikke vises.
7. Trykk ZIP-knappen én gang.
8. Kontroller ny eksport-ID innen tre sekunder og watchdog-heartbeat omtrent hvert femte sekund.

Velg bare «Fullt rapportsenter» når rapportkjøringer, historikk eller avanserte innstillinger faktisk skal brukes.
