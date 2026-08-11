# v19.22.0-rc16.14

- Hver historiske rapport bygges og replayes offline i en egen avsluttbar underprosess.
- Standard tidsgrense er 120 sekunder per rapport og kan konfigureres med `REPORT_EXPORT_TIMEOUT_SECONDS`.
- En prosess som overskrider tidsgrensen avsluttes hardt og rapporten legges i karantene med `REPORT_EXPORT_TIMEOUT`.
- Eksporten fortsetter med neste rapport etter timeout.
- En separat watchdog oppdaterer worker-heartbeat hvert femte sekund, også mens ett rapportsteg arbeider.
- Lagret `QUEUED`/`RUNNING`-status uten levende lokal worker og med foreldet heartbeat markeres automatisk som avbrutt.
- Etter serverrestart kan en ny eksport dermed startes når gammel status er foreldet.
- Sluttsammendraget viser både karantenesatte og tidsavbrutte rapporter.

Den harde offentlige PDF/TXT/JSON-auditen, offlinekravet og skrivebeskyttet eksport er beholdt.
