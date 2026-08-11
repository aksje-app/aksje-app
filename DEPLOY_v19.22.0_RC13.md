# Deploy v19.22.0 Investor Edition RC13

## Grunnlag

Deploy RC13 FULL som ren kodeerstatning over RC12 Render-hotfix. Behold database, varig Render-disk, rapportarkiv, logger, cache, `.env` og hemmeligheter utenfor kildepakken.

RC13 FULL inneholder den nødvendige låsingen `starlette==1.3.1` sammen med `streamlit==1.57.0`.

## GitHub Desktop

1. Opprett branch `deploy/v19.22.0-rc13` fra siste `main` som kjører RC12.
2. Pakk ut RC13 FULL i en separat mappe.
3. Erstatt repository-koden samlet, men behold `.git`.
4. Kontroller at `requirements.txt` finnes i repositoryroten og inneholder `starlette==1.3.1`.
5. Kontroller at ingen database-, logg-, cache-, runtime- eller secret-filer er valgt.
6. Commit med teksten `Deploy v19.22.0-rc13 workspace and scheduler status fix`.
7. Push, kontroller pull request og merge til branchen Render bruker.
8. Bruk om nødvendig `Clear build cache & deploy` på Render.
9. Bekreft `v19.22.0-rc13` i Render-logg og app.

## Første live-test

1. Åpne Autonomi → Rapporter.
2. Bekreft at «Mistet» ikke inkluderer tidspunkt før nåværende serverprosess startet; disse skal eventuelt stå som «Ikke vurdert».
3. Trykk `Nytt utkast` én gang.
4. Bekreft at ingen feil omtaler `autonomy_core_workspace_v1880`.
5. Bekreft at en ny kjørings-ID opprettes og at jobbnavnet ikke er `Uten navn`.
6. Bekreft at siden forblir på Rapporter gjennom oppstart, refresh, fremdrift og terminalstatus.
7. Last ned ny ZIP/JSON/PDF og kontroller `app_version = v19.22.0-rc13`.
8. Kontroller logger, scheduler og Pushover.

## Tilbakerulling

Reverter RC13-commit og deploy siste fungerende RC12 Render-hotfix. Ikke overskriv varig disk eller database.
