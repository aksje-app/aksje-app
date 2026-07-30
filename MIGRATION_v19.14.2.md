# Migrering til v19.14.2

v19.14.2 krever ingen destruktiv database- eller porteføljemigrering.

## Konfigurasjonsendring

- Paper Trading er fail-closed. Miljøvariabelen må være eksplisitt `true` for å tillate handler.
- Testmiljø bør ha `APP_ENVIRONMENT=test` og alle runtime-tjenester eksplisitt AV.
- Streamlit bruker standard servermodus. Den tidligere `useStarlette`-innstillingen er fjernet i v19.14.5 fordi den ikke støttes av installert Streamlit.
- Webtjenesten og cron-jobben skal ikke kjøre samme scheduler samtidig. `render.yaml` setter den innebygde web-scheduleren AV når separat cron brukes.

## Oppgradering

1. Ta backup av runtime-data og miljøvariabler.
2. Deploy til isolert testtjeneste.
3. Fullfør `ACCEPTANCE_v19.14.2.md`.
4. Verifiser at ingen testtjeneste peker mot produksjonsdatabase eller Pushover.
5. Merge først etter dokumentert godkjenning.
