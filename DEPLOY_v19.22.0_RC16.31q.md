# Deploy RC16.31q

## Før deploy

1. Bekreft SHA-256 for FULL- og DELTA-pakken.
2. Bekreft at lokal fullsuite og strict-xfail-kontroll er grønn.
3. Bevar eksisterende PostgreSQL-data, rapporthistorikk, porteføljer, handler og innstillinger.

## Etter deploy på Render

1. Bekreft programversjon `v19.22.0-rc16.31q` i UI og JSON.
2. Åpne de tre obligatoriske profilene og kontroller 08:00, 14:00 og 22:00 Europe/Oslo.
3. Slå helgekjøring av/på på én fast profil og bekreft at neste tidspunkt endres korrekt uten ekstra skanningsvinduer.
4. Bekreft at rapportsenteret viser alle tre neste faste tidspunkter samtidig.
5. Bekreft navigasjon Oversikt ↔ Autonom portefølje ↔ Læringsportefølje på desktop og mobil.
6. Kjør full systemkontroll og bekreft database, rapportlås, PDF, offentlig lenke og Pushover.
7. Verifiser én ordinær rapport ende-til-ende: UI, PDF, JSON, schedulerlogg og Pushover-kvittering.
8. Bekreft at en utløpt leveringsretry får terminal status og ikke kommer tilbake neste cronrunde.

## Rollback

Redeploy RC16.31p FULL. RC16.31q krever ingen databaseskjemamigrering og endrer ingen handels- eller porteføljeterskler.

RC16.31q skal ikke omtales som produksjonsbekreftet før livepunktene er dokumentert.

