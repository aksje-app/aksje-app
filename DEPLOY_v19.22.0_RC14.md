# Deploy v19.22.0 Investor Edition RC14

## Grunnlag

Deploy RC14 FULL som ren kodeerstatning over RC13. Behold database, varig Render-disk, rapportarkiv, logger, cache, `.env` og hemmeligheter utenfor kildepakken.

RC14 FULL beholder den fungerende avhengighetslåsen:

```text
streamlit==1.57.0
starlette==1.3.1
```

## GitHub Desktop

1. Opprett branch `deploy/v19.22.0-rc14` fra siste fungerende `main` med RC13.
2. Pakk ut RC14 FULL i en separat mappe.
3. Erstatt repository-koden samlet, men behold `.git`.
4. Kontroller at `requirements.txt`, `requirements-dev.txt`, `runtime.txt` og `.python-version` finnes i repositoryroten.
5. Kontroller at ingen database-, logg-, cache-, runtime- eller secret-filer er valgt.
6. Commit med teksten `Deploy v19.22.0-rc14 global navigation and rerun fix`.
7. Push, kontroller pull request og merge til branchen Render bruker.
8. Bruk `Clear build cache & deploy` dersom Render har beholdt gamle avhengigheter.
9. Bekreft `v19.22.0-rc14` i Render-logg og app.

## Første live-test

1. Åpne System → System/admin → Visning og tid.
2. Velg Europe/Oslo, lagre og bekreft at siden ikke hopper til Autonomi → Oversikt.
3. Gjør vanlig og hard refresh og bekreft at tidssonen fortsatt er valgt.
4. Åpne Autonomi → Rapporter og start ett nytt utkast.
5. Gjør refresh ved ca. 5 % og 50 %.
6. Bekreft at hele siden ikke gjentas når jobben avsluttes.
7. Kontroller én handling/lagring i hver hovedmeny uten rutehopp eller StreamlitAPIException.
8. Last ned ny rapport-ZIP og kontroller JSON, PDF, logger, scheduler og Pushover.

## Tilbakerulling

Reverter RC14-commit og deploy siste fungerende RC13. Ikke overskriv varig disk eller database.
