# Deploy v19.22.0 Investor Edition RC15

## Grunnlag

Deploy RC15 FULL som ren kodeerstatning over RC14. Behold database, varig Render-disk, rapportarkiv, logger, cache, `.env` og hemmeligheter utenfor kildepakken.

RC15 beholder avhengighetslåsen:

```text
streamlit==1.57.0
starlette==1.3.1
```

## GitHub Desktop

1. Opprett branch `deploy/v19.22.0-rc15` fra siste `main` med RC14.
2. Pakk ut RC15 FULL i en separat mappe.
3. Erstatt repository-koden samlet, men behold `.git`.
4. Kontroller at `requirements.txt`, `requirements-dev.txt`, `runtime.txt` og `.python-version` finnes i repositoryroten.
5. Kontroller at ingen database-, logg-, cache-, runtime- eller secret-filer er valgt.
6. Commit med teksten `Deploy v19.22.0-rc15 background market data fix`.
7. Push, kontroller pull request og merge til branchen Render bruker.
8. Bruk `Clear build cache & deploy` bare dersom Render ikke bruker de låste avhengighetene.
9. Bekreft `v19.22.0-rc15` i Render-logg og app.

## Første live-test

1. Åpne Autonomi → Rapporter og start ett nytt utkast.
2. Noter kjørings-ID og kontroller at siden blir på Rapporter.
3. Kontroller at MARKET_DATA viser tickerfremdrift, siste fremdrift og worker-heartbeat.
4. Gjør én vanlig refresh etter at jobben har passert 5 %.
5. Søk Render-loggen etter kjørings-ID og bekreft at `manual-chain-*` ikke gir `missing ScriptRunContext`.
6. Kontroller at ugyldige ticker-symboler ikke stopper markedet.
7. Vent til jobben er terminal og last ned rapport-ZIP.
8. Kontroller JSON, PDF, logger, scheduler og Pushover.

## Tilbakerulling

Reverter RC15-commit og deploy siste fungerende RC14. Ikke overskriv varig disk eller database.

## Lokal valideringsstatus

RC15 har 707 beståtte tester, 4 beståtte deltester og 35 beståtte målrettede tester, med 0 feil. Dette erstatter ikke live Render-akseptansen.
