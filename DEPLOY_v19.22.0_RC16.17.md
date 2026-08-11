# Deploy v19.22.0 RC16.17

1. Deploy FULL-pakken, eller legg DELTA-pakken oppå RC16.16.
2. Restart Render-tjenesten.
3. Bekreft `v19.22.0-rc16.17`.
4. Gjør én hard nettleseroppdatering (`Ctrl+F5`).
5. Kontroller at arkivet viser sidevelger og maksimalt 20 rapportlinjer.
6. Kontroller at hver rapport viser «Last rapportdetaljer» og at detaljer ikke er lastet som standard.
7. Trykk knappen for komplett rapport-, replay- og læringsarkiv.
8. Kontroller ny eksport-ID, tresekunders statuspolling og femsekunders watchdog-heartbeat.

FULL-pakken inkluderer `assets/`, fontene og den isolerte rapportworkeren.
