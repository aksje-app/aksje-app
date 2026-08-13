# Deploy – RC16.31e

1. Ta sikkerhetskopi av database og nåværende applikasjon.
2. Deploy FULL-pakken, eller DELTA-pakken over en verifisert RC16.31d-installasjon.
3. Kontroller at versjonen er `v19.22.0-rc16.31e`.
4. Kontroller at bare de tre obligatoriske rapportprofilene er aktive: 08:00, 14:00 og 22:00 Europe/Oslo.
5. Kontroller Render-jobber: det skal bare finnes én aktiv `aksje-app-paper-scanner`.
6. Vent til et åpent markedsvindu og bekreft nytt Paper-heartbeat, ny skann-ID og ny dato for siste vellykkede skann.
7. Kontroller neste faste rapport: riktig navn, tidspunkt, PDF, lagring og ett Pushover-varsel.
8. Kontroller Autonomi-læring: observasjonsteller øker, mens ordinære handler og kapital ikke påvirkes av observasjonen.
9. La lagrings-autoskalering være avslått dersom dette er ønsket kostnadskontroll; følg brukt lagring de første dagene.

Ved avvik: behold diagnosepakken, deaktiver duplikatjobb og gå tilbake til sikkerhetskopien. Ikke slett produksjonsdata for å skjule feilen.
