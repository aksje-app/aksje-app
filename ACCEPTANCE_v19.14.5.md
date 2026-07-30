# Akseptanse v19.14.5

Versjonen kan godkjennes for ny UTKAST-test når:

1. Oppstartloggen inneholder ingen lokal PostgreSQL socket-feil fra `trading_rules`.
2. Oppstartloggen inneholder ingen `server.useStarlette`-advarsel.
3. REPORT-forhåndskontrollen bekrefter skrivbare mapper under `APP_RUNTIME_ROOT`.
4. En kontrollert rapport kan bygge JSON og PDF på persistent disk.
5. En konstruert REPORT-feil viser konkret feiltype, bane og traceback i Autonomi-panelet.
6. Diagnosefilen opprettes under runtime-loggene.
7. Ingen handels- eller analysegrenser er endret.
