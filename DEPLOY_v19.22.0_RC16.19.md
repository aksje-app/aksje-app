# Deploy v19.22.0-rc16.19

1. Last opp hele fullpakken, inkludert `assets/`.
2. Bevar eksisterende `.app_runtime`, database og miljøvariabler.
3. Start Render-tjenesten på nytt og bekreft versjon `v19.22.0-rc16.19`.
4. Kjør én ny Autonomi-analyse med minst én komplett kandidat.
5. Bekreft `Replaystatus siste kjøring` og kontroller eventuelle mangelkoder.
6. Bygg hurtigarkivet én gang som grunnpakke. Neste eksport skal vise uendrede rapportreferanser og bare pakke nytt/endret innhold.

Tilbakerulling til RC16.18 endrer ikke eller sletter lagrede replaypakker. Produksjonsterskler er uendret.
