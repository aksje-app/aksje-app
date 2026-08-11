# Deploy v19.22.0 RC16.14

Den låste RC16.13-workeren må avsluttes ved å restarte Render-tjenesten før eller i forbindelse med deploy.

1. Deploy FULL-pakken, eller legg DELTA-pakken oppå en komplett RC16.13-installasjon.
2. Bekreft at appen viser `v19.22.0-rc16.14`.
3. Vent minst 45 sekunder etter restart dersom gammel status fortsatt står som `Kjører`.
4. Statusen skal endres til avbrutt/feilet og knappen skal bli tilgjengelig.
5. Start én ny komplett eksport.
6. Kontroller at heartbeat oppdateres omtrent hvert femte sekund selv om prosent står stille.
7. En rapport som bruker mer enn 120 sekunder skal tidsavbrytes, legges i karantene og etterfølges av neste rapport.
8. Kontroller ferdig ZIP, karantenetelling og SHA-256.

FULL-pakken inkluderer `assets/` og Noto Sans-fontene.
