# Deploy RC16.31x

1. Deploy FULL, eller DELTA over verifisert RC16.31w.
2. Restart Render web og cron; kontroller `v19.22.0-rc16.31x`.
3. Start ett utkast med Norge, Sverige og USA og minst 25 kandidater per marked.
4. Kontroller at Autonomi viser snapshotfremdrift 10/60, 20/60 og videre.
5. Kontroller `resource_telemetry.process_peak_rss_mb` i diagnosepakken.
6. Bekreft at kjøringen passerer 84 %, bygger rapport og lagrer PDF/JSON.
7. Kontroller at execution owner ender `RELEASED`.
8. Verifiser de tre faste rapportene, Pushover og offentlig rapportlenke.

Produksjonsklar status krever vellykket live Render-stresstest.
