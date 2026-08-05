# Deploy v19.22.0 RC4

## Base
Bruk kun `AI_Aksje_Analyzer_v19_22_0_INVESTOR_EDITION_RC4_FULL.zip`, eller RC4 DELTA oppå eksakt v19.22.0 RC3.

## Før deploy
1. Ta sikkerhetskopi av varige runtime-data og database.
2. Kontroller SHA-256 mot `SHA256SUMS_v19.22.0_RC4.txt`.
3. Ikke overskriv `.env`, Streamlit secrets, runtime-, cache-, logg- eller rapportdata.
4. Kontroller at Render har varig autentiseringslager. «Husk meg» krever at serverens tokenregister overlever restart.

## Etter deploy – obligatorisk live-test
- Innlogging uten og med «Husk meg», F5/refresh, utlogging og token-tilbakekalling.
- Alle hovedmenyer, Oversikt ↔ Rapporter, Driftssenter ut/inn og AI Kontrollsenter.
- Opplevd responstid og at scheduler-kick ikke gjentas ved hver rerun.
- Rapportsenterets rekkefølge, luft mellom kontrollene og mobilvisning.
- Utkast, morgen-, kveld- og nattanalyse med synlig fremdrift og terminalstatus.
- Manuell kjøring av manglende planlagt rapport.
- Ny rapport: samme Top 3, final_score og beslutning i UI, JSON og PDF.
- PDF-side 1 og alle øvrige sider visuelt.
- Scheduler 08:00/22:00 Europe/Oslo og ubemannet Pushover.
- Minste score for varsel gjelder neste manuelle og planlagte jobb.

## Sikkerhetsmerknad
Streamlit-komponenten kan ikke sette HttpOnly på nettlesercookien. RC4 reduserer risikoen med tilfeldig token, serverlagret SHA-256, SameSite=Strict, Secure på Render, utløp, session-version og tilbakekalling. Live nettlesertest og normal XSS-beskyttelse er fortsatt påkrevd.

## Tilbakerulling
Rull tilbake applikasjonsfilene til RC3. Ikke slett eller rull tilbake varige bruker-, jobb-, rapport- eller porteføljedata uten separat godkjent gjenopprettingsplan.
