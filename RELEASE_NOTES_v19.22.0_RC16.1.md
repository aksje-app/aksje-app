# AI Aksje Analyzer v19.22.0 RC16.1

## Avgrenset fremdriftshotfix

Denne versjonen endrer bare automatisk statusoppdatering for manuelle rapportkjøringer i Rapportsenteret.

### Endret

- Rapportstatusfragmentet kjører eksplisitt hvert 2. sekund.
- Fragmentfeil kan ikke lenger skjules av en stille engangsvisning.
- Polling leser et skrivebeskyttet snapshot i prosessminnet.
- Etter prosessstart brukes atomisk lokal statusfil før en eventuell engangslesing fra varig lagring.
- Vanlig polling oppretter ingen PostgreSQL-tilkobling, skriver ingen speilfil og utløser ingen full app-rerun.
- UI viser pollkilde og tidspunktet statusen sist ble lest.

### Ikke endret

Rapportmotor, final_score, beslutningsporter, kandidatvalg, scheduler, tidssone, meny, ZIP-eksport, porteføljer, Paper Trading og produksjonshandel er uendret.
