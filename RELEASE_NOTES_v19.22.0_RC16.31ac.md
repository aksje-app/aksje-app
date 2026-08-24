# RC16.31ac release notes

RC16.31ac bygger direkte på RC16.31ab.

- Alle tre Render-tjenester får `autoDeployTrigger: commit`.
- Rapport-scheduler og Paper-scanner sammenligner automatisk faktisk `RENDER_GIT_COMMIT` med web før arbeid tillates.
- Manuell `EXPECTED_APP_VERSION` er ikke nødvendig i normal drift.
- Læringsmotoren beholder én aktiv, eldste kohort per ticker slik at observasjoner kan nå 20 og 60 markedsdager.
- Dupliserte åpne observasjoner merkes `SUPERSEDED` og telles ikke som aktive.
- Den kompakte hoved-PDF-en viser short og innsider for Topp 3, porteføljen og samlet markedsdekning.

Ingen score-, risiko-, portefølje- eller handelsregel er endret.
