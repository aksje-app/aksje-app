# RC16.31r – Autonomous Worker Timeout Closure

RC16.31r er bygget direkte fra RC16.31q etter diagnose av kjøring `MBJ-20260816-182653-2031A3`.

## Endringer

- Den valgfrie parallelle strategivurderingen kjøres i en separat prosess med en hard tidsgrense på normalt 300 sekunder.
- Ved timeout termineres barneprosessen, hendelsen auditeres og den etablerte Autonomi-motoren fortsetter uten bidraget.
- Den isolerte sammenligningen har fortsatt ingen handelsfullmakt.
- Watchdog og brukergrensesnitt skiller nå tilbakekalt publiseringsrett fra faktisk avsluttet worker og frigitt rapportlås.
- Diagnosepakken inkluderer de nye eksplisitte feltene for publiseringsrett, worker og rapportlås.

## Uendret

Produksjonsterskel 73, kjøps-/salgsporter, risiko- og porteføljegrenser, de faste rapporttidene 08:00, 14:00 og 22:00 Europe/Oslo, Paper Trading-persistens og fail-closed produksjonshandel er uendret.

