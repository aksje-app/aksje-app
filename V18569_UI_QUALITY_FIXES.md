# v18.5.69 UI Quality Fixes

Samlet kvalitetsrunde basert på brukerens skjermbilder og GO.

## Rettet

- Global oppdatering er gjort tydeligere og flyttet til mer stabil topp-plassering.
- Global oppdatering-knapp har høyere kontrast og mer lesbar tekst.
- Busy/status-chip i toppbar har eksplisitt spinner når reell jobb kjører.
- Stop/Stopp-kontroller har fått mer topp-padding og skal ikke kuttes visuelt.
- Vanlige UI-endringer skal ikke dimme/tona ned arbeidsflaten.
- Normal og Full har nå tydeligere forskjell i CSS/layout.
- AI Kontrollsenter har større hovedtekst og mindre undertekst/chips.
- Sidebar/admin er strammet inn for å unngå rar linjebryting nederst.
- Aksjer og fond får global displayregel: `TICKER — Fullt navn` der navn finnes.
- Fondkostnad og tilsvarende lister viser fondnavn sammen med ticker.
- Ranking-data får fallback-navn for sentrale aksjer der datasource bare returnerer ticker.

## Test

`pytest -q` kjørt lokalt: 181 passed.
