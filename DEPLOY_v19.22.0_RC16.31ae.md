# Deploy RC16.31ae

1. Legg FULL-pakken i repository og commit alle filene samlet.
2. Synkroniser eksisterende Render Blueprint dersom tjenestene opprinnelig ble opprettet manuelt.
3. Kontroller én gang at `aksje-app`, `aksje-app-report-scheduler` og `aksje-app-paper-scanner` peker til samme repository og branch. En eventuelt feilnavngitt eller duplisert scanner må knyttes til scanner-definisjonen uten å endre databasen.
4. Kontroller under **Builds/Events** at alle tre bygger samme nye commit. **Trigger Run** starter bare sist vellykkede cron-bygg og er ikke en deploy.
5. Alle tjenester skal bruke byggekommandoen fra `render.yaml`: cache-fri installasjon fra `requirements.lock`, deretter låse- og runtimekontroll.
6. Verifiser at webheader, Pushover, JSON og begge PDF-er viser `v19.22.0-rc16.31ae`.
7. Kjør én utkastkjøring, én scanner-kjøring og la én fast rapport fullføre. Bekreft at naive/aware-datetime-feilen, repeterende OOM og gammel versjonsidentitet ikke forekommer.

Et mislykket automatisk bygg skal rettes før **Trigger Run** brukes. Ved commitavvik skal cron blokkeres kontrollert; ikke overstyr commitkontrollen manuelt.
