# Gjenta isolert kontroll

Bruk Python 3.12.13 med repositoryets låste avhengigheter og testavhengigheter,
OpenSSL, Chromium, PostgreSQL 16 og kompatible PostgreSQL-klienter.
Produksjonsdatabase eller produksjonsruntime skal aldri brukes.

Testmiljøet i denne kjøringen bruker lokal PostgreSQL på port 55432. De eksisterende
PostgreSQL-fixturene avviser vertsnavn som ikke er localhost/127.0.0.1 og oppretter
separate skjemaer. Arkivtesten gjenoppretter bare til en ny midlertidig testdatabase.
`TEST_POSTGRES_URL` er en isolert testforbindelse, ikke produksjonens DATABASE_URL.

```sh
source /workspace/.cloud/aksje-app-env.sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium \
APP_ENVIRONMENT=test APP_RUNTIME_ROOT=/workspace/.audit-167/trading-final \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --junitxml=/workspace/.audit-167/trading-final.xml
```

Yahoo-testene forsøkes separat, slik at leverandørfeil ikke telles som bestått:

```sh
APP_ENVIRONMENT=test APP_RUNTIME_ROOT=/workspace/.audit-167/engine-live \
DATABASE_URL='' AUTH_DATABASE_URL='' \
python -m pytest tests/test_superportfolio_live_ohlc_acceptance.py \
  -q --tb=short -p no:cacheprovider
```

Kjør alle de 24 verifikasjonskommandoene i «Release contracts» i
`.github/workflows/quality_release_gate.yml`, deretter:

```sh
python tools/verify_dependency_lock.py
python tools/verify_runtime_v19142.py
node scripts/verify_report_share.mjs
```

## Hva de nye testene prøver

| Område | Faktisk prøve |
|---|---|
| Paper | Ordinær automatisk kjøpsport med to kursobservasjoner, NOK-sizing av USD-aksje, take-profit, tilleggskjøp, delsalg, full exit, siste-kjøp-karantene |
| Autonomi | Ordinære porter, bevart signal til neste sesjon, kjøp, tillegg innen totalgrense, delvis gevinstsikring, sperret umiddelbart gjenkjøp og stop-loss |
| Superporteføljen | Ordinær rangering, verifisert neste sesjon, kjøp, ADD/REDUCE fra ordinær rebalansering, FX-endring og stop-loss |
| Felles hendelser | Paper-perioden testes med innskudd, uttak, utbytte og splitt gjennom samme familieadapter og NOK-journal; eksisterende motorregresjoner dekker hendelsesreglene |
| Jobbsikkerhet | Atomisk avbrudd, samtidig levering, tapt commit-svar, konfliktende ID, eksakt kontobinding, manglende bevis, utkast og miljøsperre |
| PostgreSQL | Ekte full arkivdump/gjenoppretting, samtidig ordinær Paper-jobb, DB-avbrudd etter beregning, rollback og kontrollert gjenforsøk |
| Nettleser | Alle tre kontoer ved 1280/375 px: tall/graf og innhold i PDF, CSV, Excel og ZIP; øvrige eksisterende nettleserregresjoner inkluderes |
| Bevaring | Syntetisk gammel økonomi, tap, beslutninger, modeller og observasjoner; gamle lesere/skrivere/synkroniseringer sperres i isolasjonsprøven |

Kun syntetiske data brukes. Nettleserfixturen substituerer autentisering og blokkerer
eksterne nettverkstjenester. Testgodkjenninger aktiverer bare isolerte testkontoer.
Se produksjonsprosedyren for separat godkjenning; aldri bruk testflagget i produksjon.
