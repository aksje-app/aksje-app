# Deploy RC16.31l

1. Ta sikkerhetskopi av kode, varig database, porteføljer og konfigurasjon.
2. Deploy FULL-pakken, eller bruk DELTA mot nøyaktig RC16.31k.
3. Bevar varige data og miljøvariabler; ikke kopier lokal runtime eller hemmeligheter.
4. Kontroller versjon `v19.22.0-rc16.31l` i UI, JSON, PDF og varsler.
5. Kjør kontrollert 22:05-replay og bekreft SSAB-A.ST som `BUY` med uendrede terskler.
6. Kjør én ny kontrollert Norge/Sverige/USA-rapport med handel deaktivert.
7. Verifiser at global Top 20 har evidenssøk og at USA viser faktisk SEC-status.
8. Verifiser scheduler 08:00/22:00 Europe/Oslo, logger og Pushover.
9. Aktiver ikke autonom produksjon før alle livepunkter er dokumentert bestått.

## Forventet driftsvirkning

Evidensinnhenting kan øke til lokal Top 20 per marked for å garantere at global Top 20 er kontrollert. Overvåk API-kvoter, kjøretid, minne og watchdog. Kildebegrensning skal gi eksplisitt fail-closed status, aldri skjult nedgradering.

## Tilbakerulling

Rull kode tilbake til RC16.31k og deaktiver ordinære autonome kjøp. Ikke slett portefølje, handler, rapporthistorikk, Paper Trading eller varige konfigurasjoner.
