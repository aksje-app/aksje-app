# Validering v19.22.0-rc16.20

## Automatiske kontroller

- Python-kompilering: bestått.
- Watchdog/livssyklus: 13/13 bestått.
- Målrettet bakgrunn, avbrudd, fremdrift og replay: 34/34 bestått.
- Full pytest-regresjon: 750 bestått, 38 eldre forventningsfeil.

De 38 fullregresjonsfeilene er eksisterende forventninger til eldre RC-identitet eller rapportseksjoner som den harde offentlige eksportporten allerede har fjernet. De er ikke godkjent som nye funksjonsfeil og er oppført åpent i leveransen.

## Sikkerhetskontrakt

`STALLED` er terminal for jobbleasen. Den gamle tråden kan fortsatt eksistere frem til et blokkert bibliotekskall returnerer, men alle senere fremdrifts- og sluttpubliseringer avvises fordi `lease_revoked=true`. Dette er trygg trådhåndtering uten forsøk på usikker tvangsavslutning av en Python-tråd.
