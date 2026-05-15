# v18.5.93 – Pushover Button Restore

## Bakgrunn
I v18.5.92 ble Pushover-knappene visuelt komprimert så hardt at de i praksis fremstod som fjernet. Dette var feil.

## Endret
- Flyttet Pushover-handlingsknappene ut av trang statuslinje.
- Gjeninnført to tydelige knapper i aktivt Auto trading-panel:
  - `🔐 Verifiser token/user`
  - `📣 Send testvarsel`
- Lagt status/resultat under knappene i én tydelig rad.
- Lagt CSS-beskyttelse slik at knappetekst ikke skjules av kompakt/horizontal block styling.

## Ikke endret
- Ingen endring i analyse-, trading- eller forecast-motorer.
- Ingen endring i Pushover API-funksjonene utover synlig UI-render.

## Test
- `python3 -m py_compile app.py` OK
- `pytest -q` OK: 213 passed
