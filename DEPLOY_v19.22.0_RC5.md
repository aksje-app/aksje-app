# Deploy v19.22.0 RC5

## Base

Deploy FULL-pakken for v19.22.0 RC5. Ikke kombiner kildefiler fra eldre pakker.

## Render

- Webtjenesten beholder `RUNTIME_BACKGROUND_ENABLED=false` og `REPORT_SCHEDULER_ENABLED=false`.
- Den eksisterende cron-tjenesten `aksje-app-report-scheduler` skal fortsatt kjøre `python scheduled_runner.py` hvert femte minutt.
- Cron-jobben kjører nå både valutakontroll og rapportplanlegger i samme one-shot-prosess.
- `DATABASE_URL`, `PUSHOVER_APP_TOKEN` og `PUSHOVER_USER_KEY` må være tilgjengelige for cron-tjenesten.

## Live kontroll

Etter deploy:

1. Vent inntil fem minutter og åpne Valutavarsler.
2. Bekreft grønn automatisk status med nytt cron-tidspunkt.
3. Trykk «Hent kurs nå» og kontroller ny kurs og kurstid.
4. Trykk «Sjekk valutagrense nå» og sammenlign UI/runtime/Pushover.
5. Send Pushover-test og kontroller at meldingen har samme kurs og status som UI.
6. Kjør helkjedetest og kontroller at ordinær kurs/status gjenopprettes.
7. Kontroller siden på mobil uten horisontal overflyt.

RC5 er ikke produksjonsgodkjent før disse kontrollene er dokumentert.
