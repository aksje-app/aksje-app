# v19.22.0-rc16.22 – Headless Scheduler Stabilization

Denne versjonen skiller webgrensesnittet fra den autoritative Render Cron-kjeden. Å åpne appen starter ikke lenger planlagte rapporter.

## Rettet

- én global PostgreSQL-lås dekker hele cron-syklusen;
- en separat rapportlås hindrer overlapp mellom cron og manuelle rapporter;
- reparasjon og revalidering kjøres høyst hver sjette time;
- Render-blueprint bruker 30-minutters cron og Standard 2 GB;
- forventede Streamlit bare-mode-varsler skjules i cronloggen;
- cron skriver et kompakt sluttresultat i stedet for hele rapporttilstanden;
- morgen- og kveldsrapporter bruker alltid Pushover-kvittering ved fullført kjøring;
- forsinket manuell innhenting kan ikke gjøre retroaktive portefølje- eller læringshandlinger;
- rapportsiden viser varig cronstatus uten å starte en lokal schedulertråd.

Ingen kjøps-, salgs-, stop-loss-, trailing-stop-, RSI-, score-, risiko- eller porteføljeterskler er endret.

Status: `LOCAL_PASS_LIVE_REQUIRED` til én planlagt morgen- eller kveldsrapport er observert ende-til-ende på Render uten å åpne appen.
