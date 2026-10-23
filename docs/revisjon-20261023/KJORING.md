# Kontroll av PR #167 – 23. oktober 2026

Arbeidsgren: `fix/systemrevisjon-20261022`. Startpunkt:
`0803e414fb5421858b8bdc2386cebc750d5c569f`, kontrollert mot `refs/pull/167/head`.
Bruk eksisterende checkout og Python 3.12.13. Installer requirements-dev.txt,
PyYAML og Playwright. Nettleserkjøringen brukte /usr/bin/chromium.

Kjør fra repositoryroten. Bruk bare isolert testdatabase og runtime:

```sh
export APP_ENVIRONMENT=test
export APP_RUNTIME_ROOT=/tmp/aksje-pr167-tests
export STORAGE_MODE=local
export AUTH_STORAGE_MODE=local
export AUTH_REQUIRE_PERSISTENT=false
export ALLOW_LOCAL_STORAGE_FALLBACK=true
export RUNTIME_BACKGROUND_ENABLED=false
export REPORT_SCHEDULER_ENABLED=false
export DATABASE_URL=''
export AUTH_DATABASE_URL=''
export PAPER_TRADING_ENABLED=true
export PYTHONPATH=.
```

Den lokale PostgreSQL-instansen ble opprettet slik:

```sh
docker run -d --name aksje-pr167-postgres \
  -p 127.0.0.1:55432:5432 \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_USER=test -e POSTGRES_DB=entry_exit_test postgres:16
```

Dette er en midlertidig localhost-testdatabase. Trust-oppsettet skal ikke brukes
for produksjon. Databasefixturene avviser eksterne verter og bruker egne skjemaer.

Samlet sluttkjøring:

```sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 \
BROWSER_EXECUTABLE=/usr/bin/chromium \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
.venv/bin/python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --durations=10 --junitxml=/tmp/aksje-pr167-results.xml
```

De to eksplisitte live-OHLC-testene er utenfor den isolerte sluttkjøringen.
Ingen andre tester er ekskludert her. Nettleser- og databasekrav er aktivert;
utfallene deres skal ikke forveksles med hoppede tester.

Den utvidede nettleserfixturen erstatter innlogging og blokkerer eksterne kall.
Den starter virkelig app.py og venter på både serverkvittering, Streamlits
script_finished-melding og ferdig navigasjon i nettleseren. Kontroller som bare
finnes i inventaret er ikke dermed funksjonstestet. De nye innstillingsforløpene
bruker isolert lagring og sender ikke Pushover-varsler.

Øvrige kontroller:

```sh
.venv/bin/python tools/verify_dependency_lock.py
.venv/bin/python tools/check_runtime_dependencies.py
PYTHONPYCACHEPREFIX=/tmp/aksje-pr167-pycache .venv/bin/python -m compileall -q \
  -x '(^|/)(\.git|\.venv|venv|dist)/' .
node scripts/verify_report_share.mjs
git diff --check
```

Alle skriptene under «Release contracts» i quality_release_gate.yml ble også kjørt.
Samlede tall og avgrensninger finnes i rapport.md og testresultater.json.

Ved opprydding stoppes og fjernes bare testcontaineren opprettet for denne
kjøringen. Ingen produksjonsdatabase, Render-tjeneste, merge eller deploy brukes.
