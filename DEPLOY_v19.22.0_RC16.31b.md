# Deploy – v19.22.0-rc16.31b

1. Deploy FULL-pakken som vanlig, eller legg DELTA-pakken over en komplett RC16.31a-installasjon.
2. Bekreft at app og Pushover viser `v19.22.0-rc16.31b`.
3. Åpne rapportplanleggingen én gang. Innlasting migrerer de tre faste profilene og lagrer renset konfigurasjon.
4. Kontroller leveransetabellen:
   - morgen 08:00
   - ettermiddag 14:00
   - kveld 22:00
5. Ikke start automatisk rapporttest samtidig med en ordinær fast rapport.
6. Kontroller at det bare finnes én aktiv `aksje-app-paper-scanner` i Render.

## Forventet etter deploy

- Ingen fast rapport ved halvtimepunktene mellom de tre faste tidene.
- `AUTOMATISK 1/4–4/4` vises bare når rapporttestmodus er aktiv.
- Paper-skanneren fortsetter på sin separate cron og oppdaterer skannestatus uavhengig av rapportmotoren.
