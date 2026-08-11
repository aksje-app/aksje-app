# Deploy – v19.22.0 RC16.1 Progress Hotfix

## Omfang

Kun automatisk fremdriftsoppdatering er endret.

## Deploy

1. Erstatt RC16-koden med RC16.1 FULL, eller legg RC16.1 DELTA over en ren RC16-installasjon.
2. Behold eksisterende miljøvariabler, persistent disk, DATABASE_URL og scheduleroppsett.
3. Bekreft versjonen `v19.22.0-rc16.1` i appen.
4. Start én manuell rapportkjøring i Rapportsenteret.
5. Ikke oppdater nettleseren manuelt de første 2–3 minuttene.
6. Dokumenter at polltidspunkt, prosent, steg og heartbeat oppdateres automatisk.

## Tilbakerulling

Rull tilbake til RC16 FULL dersom appen ikke starter. Ingen database- eller konfigurasjonsmigrering er inkludert.
