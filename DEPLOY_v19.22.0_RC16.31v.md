# Deploy RC16.31v

1. Deploy FULL, eller DELTA over verifisert RC16.31u.
2. Restart Render-webtjenesten og kontroller `v19.22.0-rc16.31v`.
3. Åpne Autonomi → Rapporter.
4. Åpne alle tre rapportområdene og bekreft at ingen `NameError` vises.
5. Oppdater nettleseren og bekreft at valgt rapportområde gjenopprettes.
6. Last ned hovedrapport og komplett rapport med teknisk vedlegg.
7. Bygg komplett ZIP og verifiser scheduler, JSON, logger og Pushover.

Produksjonsklar status krever fullført live-verifikasjon på Render.
