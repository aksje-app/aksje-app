# Deploy RC16.31r

1. Ta databasebackup og noter aktiv rapportlåseier før deploy.
2. Deploy FULL-pakken, eller DELTA-pakken over en verifisert RC16.31q-installasjon.
3. Restart web- og cron-tjenestene slik at en eventuell eldre hengende worker og rapportlås avsluttes.
4. Kontroller synlig versjon `v19.22.0-rc16.31r` og at `parallel_strategy_isolated_worker.py` finnes i runtime-roten.
5. Verifiser en kontrollert manuell kjøring: AUTONOMOUS passerer parallelstrategisteget, PDF og JSON lagres, og rapporten kan lastes ned fra rapportarkivet/den offentlige lenken.
6. Verifiser de tre neste faste kjøringene 08:00, 14:00 og 22:00 Europe/Oslo samt helgevalget.
7. Verifiser Pushover-lenken på mobil. Pushover inneholder en lenke til rapporten, ikke selve PDF-vedlegget.
8. Ved STALLED: kontroller feltene `worker_terminated` og `report_lock_released`; restart webtjenesten hvis en eldre worker fortsatt holder låsen.

Ikke merk produksjonen som endelig verifisert før UI, PDF, JSON, logger, scheduler og Pushover er kontrollert på Render.

