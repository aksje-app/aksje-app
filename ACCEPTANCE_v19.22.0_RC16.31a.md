# Akseptanse – v19.22.0-rc16.31a

- [x] Diagnose dokumentert før kodeendring.
- [x] Rapport- og Paper-låser har forskjellige advisory lock-ID-er.
- [x] Paper-status inneholder heartbeat, tilstand, skann-ID, siste vellykkede skann og antall handler.
- [x] Market-closed heartbeat endrer ikke tidspunktet for siste reelle skann.
- [x] Paper-handel får skann-ID, worker execution-ID og datatid i `trade_context`.
- [x] `THEORETICAL_DECISIONS` godkjennes fra eget undertrinn og feiler fortsatt ved `BLOCKED`/`ERROR`.
- [x] Testprofil er midlertidig og gamle testprofiler migreres bort.
- [x] Faste rapporttider er 08:00, 14:00 og 22:00 Europe/Oslo.
- [x] Målrettet regresjonstest: 43 bestått.
- [x] FULL- og DELTA-pakkene er validert uten mangler, hemmeligheter eller ugyldige arkivbaner.
