# Release notes v19.22.0 RC16.3

## Endret
- Valgt visningstidssone lagres varig via eksisterende sentralt innstillingslager og konfigurasjonsregister.
- Lagring av visningstidssone utløser ikke lenger en ekstra helsidererender.
- Aktiv hovedside, panel og fane skal derfor beholdes når tidssonen lagres.
- En passiv live-klokke i sidefeltet viser både PC-/nettlesertid og apptid i valgt visningstidssone.

## Uendret og beskyttet
- Navigasjonsrenderer er byte-for-byte identisk med RC16.2.
- Scheduler kjører fortsatt 08:00 og 22:00 Europe/Oslo.
- Rapportmotor, score, terskler, porteføljer, Paper Trading og ekte handel er ikke endret.
- Produksjonshandel er fortsatt fail-closed.
