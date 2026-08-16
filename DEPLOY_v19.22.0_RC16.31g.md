# Deploy RC16.31g

1. Ta sikkerhetskopi av database og vedvarende disk.
2. Deploy FULL eller bruk DELTA mot nøyaktig RC16.31f-baseline.
3. Bekreft at appen viser `v19.22.0-rc16.31g`.
4. Kjør systemkontroll uten handler.
5. Kontroller Univers- og dekningsrapporten. Manglende symboler skal gi synlig feil.
6. La neste faste rapport kjøre og kontroller antall grovskannede per marked, sektorfordeling og BUY-blockere.
7. Kontroller at Paper-skannerens heartbeat fortsetter å oppdateres separat.

Første komplette kjøring kan ta lengre tid fordi hele kontrollisten henter data. Senere kjøringer bruker tidsbegrenset cache.
