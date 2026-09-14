# Deploy RC16.31bf

1. Last opp den rene DELTA-pakken til GitHub-repoet eller bruk FULL som komplett kilde.
2. Render web og report-scheduler skal kjore samme commit/version.
3. Ikke opprett ny miljo-variabel for Norge-modus med mindre du vil overstyre standarden. Standard i RC16.31bf er Norge-only for automatiske faste rapporter og Paper-skanner.
4. For senere aa gjeninnfore Norge + Sverige + USA: sett `PRODUCTION_NORWAY_ONLY=false` og redeploy/restart.
5. Etter deploy: bekreft version `v19.22.0-rc16.31bf`, at faste rapporter viser `markets=[Norge]`, og at Paper scanner bare viser Norge som automatisk marked.
6. Kontroller en rapport med minst tre kandidater: rang 1-3 skal ha trendbevis; rang 4-10 skal ha `Vis trend`-detaljer i UI naar de finnes.

Ingen eksisterende STORAGE_RETENTION-innstillinger skal endres.
