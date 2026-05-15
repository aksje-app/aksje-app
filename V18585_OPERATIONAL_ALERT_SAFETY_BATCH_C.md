# v18.5.85 – Operational Alert Safety Batch C

## Scope
Batch C lukker oppgavene rundt Pushover test og varslingsvalidering/logging.

## Endringer
- Lagt inn egen knapp: `Verifiser token/user`.
- Verifiserer `PUSHOVER_APP_TOKEN` og `PUSHOVER_USER_KEY` mot Pushover `/users/validate.json` uten å sende varsel.
- `Send testvarsel` sender faktisk Pushover-melding og viser HTTP-status/API-respons.
- Siste Pushover-sjekk lagres i `st.session_state` og vises i `Varselinfo / Pushover-status`.
- Token og user-key maskeres i UI slik at hemmeligheter ikke eksponeres.
- `send_pushover_alert` returnerer nå response-info internt i app.py for bedre feilsøking.

## Forventet UI-adferd
- Mangler env-variabler: verifisering/test er deaktivert, status viser MISSING.
- Env finnes men er feil: verifisering viser feil med Pushover API-respons.
- Env finnes og er gyldig: verifisering viser OK.
- Testvarsel viser om meldingen faktisk ble akseptert av API-et.

## Ikke endret
- Selve Pushover-hemmelighetene lagres ikke i app-settings. De skal fortsatt ligge som miljøvariabler.
- Varsler for paper trades/watchlist følger fortsatt eksisterende toggles og confidence-grenser.
