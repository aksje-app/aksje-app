# Deploy – v19.22.0-rc16.34b

1. Merge bare etter grønn Release gate.
2. Deploy web fra samme commit som scheduler.
3. Behold eksisterende persistent storage/database.
4. Bekreft versjon `v19.22.0-rc16.34b`.
5. Live-smoke:
   - Start → «Åpne hele Super Portfolio».
   - Marked og signaler → Super Portfolio.
   - Kontroller at porteføljeposisjoner, totalgraf og per-aksje-graf er synlige.
   - Kontroller at kompaktkortet ikke har tekst-overlapp.
   - Kontroller innsiderdelen på smal og bred skjerm.
6. Ved avvik: ikke kall releasen ferdig; rull tilbake til siste grønne main.
