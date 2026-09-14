# Deploy – RC16.31cg

## Render-delta

Last bare opp filene i den rene `RC16.31cg_RENDER_DELTA.zip`. Dokumentasjon, tester, skjermbilder og `.env` skal ikke lastes opp til Render.

## Kontroll etter deploy

1. Bekreft at appens versjon er `v19.22.0-rc16.31cg`.
2. Kjør én kontrollert rapportjobb og vent til status er fullført.
3. Bekreft at rapportfilene står samlet rett under Utkast/pågående kjøring.
4. Bygg komplett rapportpakke og kontroller at manifestet viser standard-PDF, teknisk PDF, JSON, tekst og eventuell diagnose.
5. Bekreft én Fresh Trend-syklus og at neste parallelle cron-oppvåkning blir hoppet over dersom låsen er opptatt.
6. Kontroller at Pushover viser børs, land, oppfølgingsdag, kursendringer, volumgrunnlag, fullscan-RS, oppsettstatus, retning og datadekning.
7. Bekreft fire desimaler i valutakurs og grense.

Ved avvik: behold forrige deploy aktiv og bruk diagnosepakken fra den aktuelle kjørings-ID-en.

