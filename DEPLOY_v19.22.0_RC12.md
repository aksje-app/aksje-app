# Deploy v19.22.0 Investor Edition RC12

## Grunnlag

Deploy RC12 FULL som ren kodeerstatning over RC11. Behold database, varig Render-disk, rapportarkiv, logger, cache, `.env` og hemmeligheter utenfor kildepakken.

## GitHub Desktop

1. Opprett branch `deploy/v19.22.0-rc12` fra siste produksjonsbranch.
2. Pakk ut RC12 FULL i en separat mappe.
3. Erstatt repository-koden samlet, men behold `.git`.
4. Kontroller at ingen database-, logg-, cache-, runtime- eller secret-filer er valgt.
5. Commit med teksten `Deploy v19.22.0-rc12 report job lifecycle fix`.
6. Push, kontroller pull request og merge til branchen Render bruker.
7. Bekreft `v19.22.0-rc12` i Render-logg og app.

## Første live-test

1. Åpne Autonomi → Rapporter.
2. Noter eventuell tidligere terminal kjørings-ID.
3. Trykk `Nytt utkast` én gang.
4. Bekreft at en ny kjørings-ID opprettes og at jobbnavnet ikke er `Uten navn`.
5. Bekreft at arbeidsflaten forblir Rapporter gjennom oppstart, fremdrift og terminalstatus.
6. Bekreft at en vanlig refresh ikke markerer kjøringen som serverrestart.
7. Last ned ny ZIP/JSON/PDF og kontroller ny run-ID og `app_version = v19.22.0-rc12`.
8. Kontroller schedulerstatus og bekreft at gamle jobbkontrakter er migrert uten endring i tider eller tidssone.

## Tilbakerulling

Reverter RC12-commit i GitHub Desktop og deploy siste fungerende RC11-commit. Ikke overskriv varig disk eller database.
