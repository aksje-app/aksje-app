# Deploy RC16.31aa

1. Suspendér cron under deploy.
2. Deploy FULL, eller DELTA over verifisert RC16.31z, til både web og scheduler.
3. Bekreft `v19.22.0-rc16.31aa` og samme commit i begge tjenester.
4. Restart web og scheduler.
5. Kjør ett manuelt utkast for Norge, Sverige og USA.
6. Bekreft fremdrift fra `59/59` til `Lagrer markedssnapshot separat` og videre til Autonomi og rapport.
7. Kontroller diagnosepakken, PDF, vedlegg, historikk og varsling.
8. Aktiver cron og verifiser én full planlagt kjøring.

Ingen automatisk sletting eller migrering av eldre snapshots utføres.

