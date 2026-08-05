# Deploy v19.22.0 RC8

Deploy RC8 FULL-pakken som én samlet kildebase. Ikke bland filer fra RC6/RC7 eller eldre pakker.

## Før deploy
- Ta vare på varige runtime- og databasevolumer.
- Bekreft miljøvariabler og Render Cron.
- Kontroller SHA-256 mot SHA256SUMS_v19.22.0_RC8.txt når leveransen er bygget.

## Etter deploy
- Kontroller versjon v19.22.0-rc8.
- Kjør akseptansekravene i ACCEPTANCE_v19.22.0_RC8.md.
- Kontroller spesielt banner av/på, refresh, tidssoner, valutakjede og en ny rapport.

RC8 er ikke produksjonsgodkjent før live-kontrollene er dokumentert.
