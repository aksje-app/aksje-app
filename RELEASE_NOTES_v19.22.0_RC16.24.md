# v19.22.0-rc16.24 – Varig Pushover-rapportlenke

## Dokumentert årsak

PDF-en ble lagret med en gyldig varig `public_report_token`, men tokenfeltet ble utelatt da det canonicaliserte rapportobjektet ble kopiert til Pushover-varslingen. Varslingen falt derfor tilbake til den gamle `/app/static/reports/...`-ruten, som Streamlit tolket som en appside og avviste med «Page not found».

## Retting

- `public_report_token` følger eksplisitt med til både rapportarkiv og Pushover.
- Nye rapportlenker bruker bare `/?public_report_token=...` på webtjenestens domene.
- Den gamle statiske ruten er fjernet som fallback.
- Manglende token feiler lukket uten rapportlenke i stedet for å sende en ødelagt lenke.
- Den komplette `_notification → send_pushover_alert`-overleveringen er testet.

Ingen handels-, score-, risiko-, lærings- eller porteføljeterskler er endret.
