# Deploy RC16.31y

1. Deploy FULL, eller DELTA over verifisert RC16.31x.
2. Restart Render web og cron; kontroller `v19.22.0-rc16.31y`.
3. Start ett utkast med Norge, Sverige og USA og 25 kandidater per marked.
4. Bekreft snapshotfremdrift til 59/59 og deretter arbeidsenhet 1/10 eller høyere.
5. Kontroller at rapport, PDF og JSON blir lagret.
6. Last ned diagnosepakken og kontroller `resource_telemetry.process_peak_rss_mb`.
7. Bekreft at execution owner ender `RELEASED`.
8. Verifiser Pushover og offentlig rapportlenke.

Produksjonsklar status krever vellykket live Render-kjøring.
