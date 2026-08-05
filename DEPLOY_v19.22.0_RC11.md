# Deploy v19.22.0 Investor Edition RC11

## Grunnlag

Deploy RC11 FULL som ren kodeerstatning over RC10. Behold databaser, varig Render-disk, rapportarkiv, logger, cache, `.env` og hemmeligheter utenfor kildepakken.

## GitHub Desktop

1. Opprett branch `deploy/v19.22.0-rc11` fra siste produksjonsbranch.
2. Pakk ut RC11 FULL i en separat mappe.
3. Erstatt repository-koden samlet, men behold `.git`.
4. Kontroller at ingen database-, logg-, cache-, runtime- eller secret-filer er valgt.
5. Commit med teksten `Deploy v19.22.0-rc11 report navigation fix`.
6. Push, kontroller pull request og merge til branchen Render bruker.
7. Bekreft `v19.22.0-rc11` i Render-logg og app.

## Første live-test

1. Åpne Autonomi → Rapporter.
2. Trykk `Nytt utkast` én gang.
3. Bekreft at jobben starter og at siden blir på Rapporter.
4. Vent til terminal status uten å bytte side.
5. Bekreft at ingen StreamlitAPIException vises og at fremdriftspanelet ikke dupliseres.
6. Last ned ny ZIP/JSON/PDF og kontroller run-ID og appversjon.

## Tilbakerulling

Reverter RC11-commit i GitHub Desktop og deploy siste fungerende RC10-commit. Ikke overskriv varig disk eller database.
