# Deploy RC16.31p

1. Ta varig backup av database, rapportarkiv, Autonomi-portefølje og læringsportefølje.
2. Kontroller at aktiv versjon er RC16.31o og at ingen rapport-/Autonomi-kjøring holder aktiv lås.
3. Deploy FULL-pakken til staging først. Ingen nye miljøvariabler er obligatoriske.
4. Kjør rask systemkontroll og ett manuelt utkast uten porteføljehandling.
5. Kontroller PDF og JSON for kandidatdatadekning, `UKJENT` shortstatus og avstemt portefølje.
6. Last ned replay/service-ZIP og kontroller `candidate_data_audit.json`, `short_intelligence.json`, læringsrapport og SHA-256-manifest.
7. Kontroller scheduler 08:00/22:00 Europe/Oslo, låseeier, heartbeat, avbryt og Pushover.
8. Kjør minst én planlagt shadow-kjøring uten regelendring før vanlig drift fortsetter.
9. Rollback: redeploy RC16.31o FULL. Ingen databaseskjemamigrering kreves av RC16.31p.

RC16.31p skal ikke omtales som produksjonsbekreftet før livepunktene ovenfor er dokumentert.

