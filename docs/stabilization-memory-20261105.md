# Restart-minne og produksjonsverifikasjon – 5. november 2026

## Påvist årsak og rettelse

Render-cron på commit `54bf027` rapporterte gjentatte `Out of memory (used over 2Gi)`. PostgreSQL-dokumentet `simulation_restarts/nok-20261025T012118Z/bundle.json` er 95 775 623 byte. Runtime-loggene viser omtrent 700 MiB ekstra RSS per deserialisering. Flere ruter holdt tidligere verifiserte snapshots mens nye komplette snapshots ble lastet eller transaksjonen startet.

Autonomi gjenbruker nå sitt verifiserte snapshot ved læringsforberedelse, visning og resultatberegning, frigjør før skrive­transaksjonen og leser ett nytt committed snapshot etterpå. Samme levetidsrettelse gjelder Paper, Superporteføljen og stoppovervåking. Innstillinger uten separat lagret overstyring kan gjenbruke den signerte godkjenningens innstillinger i den låste transaksjonen. Autorisasjon, siste stoppstatus og kanonisk konfigurasjon kontrolleres fortsatt under låsen.

Den private strategisesjonen leser journalen uten dype kopier. Rene regnskapsoperasjoner deler uforanderlige gamle hendelser, kopierer hendelseslisten og legger til egne nye payloads. Offentlige kontolesninger leverer fortsatt frakoblede kopier. Alle eksisterende hash-, replay-, åpnings-, godkjennings- og journalprefikskontroller beholdes. PostgreSQL-lesecursoren lukkes før transformasjonen, slik at både Python-tekst og libpq-resultatbuffer frigjøres mens transaksjonens radlås beholdes. Kanonisk SHA256 strømmer identiske JSON-byte uten en ekstra komplett streng.

UI-en gjenbruker valgt verifisert bundle til rapport og eksport, i stedet for å lese valgt periode flere ganger mens første snapshot fortsatt lever. Ingen historikk, journaler, læringsmoduler, tapsresultater eller handelsregler slettes eller nullstilles.

## Minneakseptanse

`tests/test_restart_large_bundle_budget.py` kjører den virkelige Autonomi-motoren mot over 92 MiB syntetiske, gyldige historiske strategikvitteringer. Samtlige 4 902 gamle journalhendelser beholdes; journalen verifiseres før og etter kjøring. Dette er en ressursregresjonstest, ikke produksjonsdata eller en avkastningstest.

Isolert kjøring med Docker `--memory=2g --memory-swap=2g` bestod:

| Måling | MiB |
| --- | ---: |
| Hard containergrense | 2 048,0 |
| Maksimal samlet containerbruk | 1 667,4 |
| Maksimal prosess-RSS | 1 489,7 |

Kjøringstid: 206,27 sekunder. Testen kan kjøres med `RUN_RESTART_MEMORY_BUDGET=1 pytest -q -s tests/test_restart_large_bundle_budget.py` og er lagt til Release Gate. Cron-sluttoppsummeringen eksponerer nå også maksimal prosess- og containerminnebruk for faktisk produksjonskontroll.

## Verifikasjonskrav før ferdigmelding

Bestått lokal stresstest erstatter ikke Render-verifikasjon. Begge eksisterende PR-er må ha bestått Release Gate. Utrulling skal knyttes til riktig main-commit, og en faktisk Autonomi-kjøring må fullføre på standardplanen under 2 GiB. Lærings-/Pushover-kvittering og eventuelle manglende live-markedsdata må rapporteres separat. Ingen av disse produksjonskravene markeres bestått bare fordi en deploy er `live` eller cron avslutter uten arbeid.
