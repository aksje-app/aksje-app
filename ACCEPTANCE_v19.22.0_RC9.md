# Akseptanse v19.22.0 Investor Edition RC9

Versjonen kan ikke produksjonsgodkjennes før alle punkter er dokumentert live på Render.

## Ren deploy

- Deploy hele RC9 FULL-pakken som ren erstatning for applikasjonskoden.
- Kontroller at `app.py` inneholder `special-watch-surface-v19220rc9` og ikke den gamle særskilt-bannerbanen med `ticker-tape-item`.
- Programmet viser v19.22.0-rc9.
- Runtime-data, hemmeligheter og varige rapporter beholdes utenfor kildepakken.

## Markedsvalg

- Alle samlevalg viser nøyaktig hvilke land som inngår.
- Eldre lagret «Utvidet Norden» vises som «Danmark + Finland».
- En nordisk firelandsjobb vises som «Norge + Sverige + Danmark + Finland».
- Før start vises landene som faktisk skal kjøres.
- Jobb, fremdrift, JSON og PDF viser samme landliste.
- PDF-side 1 viser planlagt og faktisk markedsdekning per land.

## Banner

Test alle fire kombinasjoner minst tre ganger, med manuell refresh mellom endringene:

1. Hovedbanner på / Særskilt overvåkning på
2. Hovedbanner på / Særskilt overvåkning av
3. Hovedbanner av / Særskilt overvåkning på
4. Begge av

Krav:

- Ingen stor tom hvit flate.
- Ingen minigrafer stablet langs venstresiden.
- Ingen rester etter deaktivert banner.
- Skjult komponent henter ikke data.
- Bannerlenke åpner detaljer uten å miste aktiv hovedside.
- Mobil, nettbrett og desktop kontrolleres.

## Rapportsenter og navigasjon

- Nytt utkast blir stående på Rapporter.
- Morgen-, kvelds- og nattanalyse blir stående på Rapporter.
- Fremdriftsoppdatering og terminalstatus blir stående på Rapporter.
- Testkjøring, lagring, aktivering, favoritt og sletting blir stående på Rapporter.
- Manuell refresh fem ganger beholder samme side og underfane.
- Ingen innholdsside rendres flere ganger under seg selv.
- Ingen handling hopper til AI Kandidattest eller Autonomi Oversikt.

## Beslutningskjede

- Rapport og JSON viser analytisk anbefaling separat fra handelsstatus.
- En analytisk anbefaling kan vises som blokkert av Autonomis primære simulerte portefølje uten å bli omtalt som analytisk avvist.
- Kandidater som ikke består score/evidens/data vises som ikke analytisk anbefalt, selv om porteføljen også er full.
- Autonomis simulerte portefølje og Paper Trading omtales som separate porteføljer.
- Ingen produksjonsterskel eller handelsregel er endret.

## Rapport

- Top 1–3 er på side 1.
- Planlagte og faktisk skannede land er på side 1.
- UI, JSON og PDF har samme Top 3, final_score og beslutning.
- Alle sider kontrolleres ved 200 DPI for klipping, overlapping og sidebrudd.

## Scheduler og varsling

- Morgenrapport starter 08:00 Europe/Oslo.
- Kveldsrapport starter 22:00 Europe/Oslo.
- Pushover leveres uten innlogget bruker.
