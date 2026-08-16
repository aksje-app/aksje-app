# Deploy RC16.31k

1. Ta sikkerhetskopi av gjeldende deploy og varig database.
2. Deploy FULL-pakken, eller bruk DELTA-pakken mot nøyaktig RC16.31j.
3. Bevar alle miljøvariabler og varige volumer. Ikke kopier lokal `.app_runtime`.
4. Kontroller at app, rapportmetadata og Pushover viser `v19.22.0-rc16.31k`.
5. Kontroller at faste rapporter fortsatt kjører 08:00 og 22:00 Europe/Oslo.
6. Kjør én kontrollert rapport for Norge, Sverige og USA.
7. Verifiser i JSON at `candidate_selection.policy` er `FULL_LOCAL_SCORE_THEN_GLOBAL_SHORTLIST`, at `selected` er opptil 60 eller mer når operatøren har konfigurert mer, og at `production_threshold_changed` er `false`.
8. Verifiser PDF, JSON, logger, scheduler og Pushover før produksjonsklar status.

## Forventet driftsvirkning

Lokal scoring utføres for flere kandidater og kan øke CPU-tid. Dyr evidensinnhenting er fortsatt avgrenset av eksisterende evidens- og forslagstelling. Overvåk kjøretid, minne, kildebudsjett og watchdog ved første live kjøring.

## Tilbakerulling

Rull tilbake kode til RC16.31j. Ikke slett eller nullstill portefølje, handler, rapporthistorikk, Paper Trading eller konfigurasjon.
