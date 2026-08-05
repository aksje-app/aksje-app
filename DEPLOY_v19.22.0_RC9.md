# Deploy v19.22.0 Investor Edition RC9

## Viktig

Den opplastede GitHub/live-kilden som ble sammenlignet med RC8 inneholdt fortsatt den gamle særskilt-bannerimplementasjonen, selv om programversjonen var RC8. RC9 må derfor deployes som en ren FULL-erstatning. Ikke kopier bare versjonsfilen eller bland RC9 med en eldre `app.py`.

## Fremgangsmåte

1. Ta sikkerhetskopi av produksjonskonfigurasjon, database og varig runtime-disk.
2. Pakk ut `AI_Aksje_Analyzer_v19_22_0_INVESTOR_EDITION_RC9_FULL.zip` lokalt.
3. Erstatt repository-koden med innholdet fra FULL-pakken.
4. Ikke kopier `.app_runtime`, cache, logger, databaser, `.env` eller hemmeligheter til repository.
5. Commit og push hele endringssettet.
6. Kontroller i Render-buildloggen at riktig commit bygges.
7. Bekreft v19.22.0-rc9 i programmet.
8. Utfør hele `ACCEPTANCE_v19.22.0_RC9.md`.

## Rask kildekontroll etter deploy

Søk i deployet `app.py`:

- Skal finnes: `special-watch-surface-v19220rc9`
- Skal finnes: `pin_autonomy_workspace_route_v19220_rc9`
- Særskilt banner skal ikke bruke: `ticker-tape-item` eller `ticker-tape-wrap special-watch`

## Scheduler

Rapporttidene er uendret:

- Morgen: 08:00 Europe/Oslo
- Kveld: 22:00 Europe/Oslo

## Tilbakerulling

Ved kritisk feil rulles applikasjonskoden tilbake til den sist fungerende commit-en. Varig runtime og database skal ikke overskrives med innhold fra en distribusjons-ZIP.
