# Reproduserbare, isolerte kontroller

Kjør fra repositoryroten med installerte prosjektavhengigheter. Ikke bruk produksjonsdatabase. Kjøringene benyttet Python 3.12, Streamlit 1.57, pytest og Chromium. Playwright og pypdf/openpyxl kreves for nedlastingskontrollene.

Felles testmiljø (sett før kommandoene):

```sh
export APP_RUNTIME_ROOT=/tmp/aksje-revisjon-repro
export STORAGE_MODE=local
export DATABASE_URL=''
export AUTH_DATABASE_URL=''
export ALLOW_LOCAL_STORAGE_FALLBACK=true
export RUNTIME_BACKGROUND_ENABLED=false
export REPORT_SCHEDULER_ENABLED=false
export PAPER_TRADING_ENABLED=true
export PYTHONPATH=.
```

Sammenlignbar full pakke:

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_superportfolio_live_ohlc_acceptance.py
```

Samme kommando ble kjørt fra en separat, uendret worktree av basecommit f0ef5b491219c2a1232bff30cc9b37eed58bc479, med et annet APP_RUNTIME_ROOT. De to live-OHLC-testene krever ekstern Yahoo-tilgang og er utenfor begge sammenlignbare pakker. Den første brede kjøringen inkluderte dem og observerte manglende leverandørdata. Ingen test er endret for å skjule dette.

Aktiv pakke:

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider --ignore-glob='tests/test_rc*.py' --ignore-glob='tests/test_v*.py' --ignore=tests/test_superportfolio_live_ohlc_acceptance.py
```

Nye programmeringsregresjoner:

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_system_revision_20261022.py
```

Kvalitetspakken og de 24 releasekontraktene bruker filene/kommandoene i henholdsvis `Quality regression suite` og `Release contracts` i `.github/workflows/quality_release_gate.yml`. De ble kjørt med miljøet over, med `.venv/bin/python -m pytest -q -p no:cacheprovider` som pytest-kommando og `.venv/bin/python` for kontraktskriptene.

Faktisk nettleser (system-Chromium var tilgjengelig):

```sh
SYSTEM_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_system_revision_browser.py
SF_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_superfund_browser.py
```

Hver hele-app-fixture oppretter egen midlertidig runtime, erstatter innlogging med en testbruker og blokkerer eksterne HTTP-/socket-kall. Autonomi er aktivert som en eksplisitt fixtureinnstilling for å vise arbeidsflatene; bakgrunnsjobber og Paper-utførelse er av. Dette er ikke en test av ekte innlogging, eksterne varsler eller produksjonsaktivering.

Øvrige kontroller:

```sh
PYTHONPYCACHEPREFIX=/tmp/aksje-revisjon-syntax .venv/bin/python -m compileall -q -x '(^|/)(\.git|\.venv|venv|dist)/' .
node scripts/verify_report_share.mjs
git diff --check
```

Databaseintegrasjonstestene er ikke kjørt lokalt: ingen isolert PostgreSQL-server var tilgjengelig. Workflowens eksisterende PostgreSQL-jobb er beholdt. Et grønt resultat i andre pakker erstatter ikke dette beviset.
