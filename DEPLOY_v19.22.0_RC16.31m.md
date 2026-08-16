# Deploy RC16.31m

1. Ta varig sikkerhetskopi av database, rapportarkiv, autonom portefølje, handler, beslutninger, konfigurasjon og audit.
2. Deploy FULL-pakken eller legg DELTA over en verifisert RC16.31l-installasjon.
3. Behold eksisterende miljøvariabler, inkludert en identifiserbar `SEC_USER_AGENT`.
4. Ikke nullstill portefølje, Paper Trading, scheduler eller persistent minimum alert score.
5. Kontroller at versjonen er `v19.22.0-rc16.31m` i UI, JSON, PDF, logger og varsler.
6. Kjør en manuell rapport uten produksjonsskriving og kontroller:
   - minst 60 analyserte kandidater når universet tillater det;
   - minst 10 per Norge/Sverige/USA når hvert marked har minst 10 tilgjengelige;
   - eksisterende posisjoner merkes `ALLEREDE I PORTEFØLJEN`;
   - uverifiserte poeng fremgår som fjernet;
   - SEC-registeret hentes én gang, uten ticker-for-ticker 429-serie;
   - rapport, JSON og replay viser samme sluttbeslutning.
7. Verifiser planlagte kjøringer 08:00 og 22:00 Europe/Oslo.
8. Verifiser Pushover, offentlig PDF-lenke og rapportarkiv.
9. Ved feil: gå tilbake til den bevarte RC16.31l FULL-pakken og gjenopprett kun fra sikkerhetskopi; ikke slett varige data.

