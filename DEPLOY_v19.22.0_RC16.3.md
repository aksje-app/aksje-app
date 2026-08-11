# Deploy v19.22.0 RC16.3

1. Ta sikkerhetskopi av aktiv RC16.2-deploy.
2. Erstatt med RC16.3 FULL eller legg RC16.3 DELTA over en ren RC16.2-installasjon.
3. Bekreft banner `v19.22.0-rc16.3`.
4. Åpne System/admin og velg en visningstidssone.
5. Lagre tidssonen og bekreft at aktiv navigasjon og panel ikke endres.
6. Oppdater siden og logg inn på nytt; bekreft at tidssonen fortsatt er valgt.
7. Bekreft at sidefeltets klokke viser både PC-tid og apptid og oppdateres hvert sekund.
8. Bekreft at rapportjobbene fortsatt er 08:00 og 22:00 Europe/Oslo.
9. Utfør live Render-kontroll av UI, PDF, JSON, logger, scheduler og Pushover.

Rollback: gjenopprett RC16.2 FULL. Ingen database- eller skjemamigrering kreves.
