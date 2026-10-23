# Reproduserbare kontroller

Utgangspunkt: `43c756095dcf9b72e3171c87ec798b10b173d837`.
Alle databaseprøver bruker disponibel localhost-PostgreSQL; ingen Render-URL.
Produksjonsfixture setter APP_ENVIRONMENT=production og krever virkelig signert
aktivering og faktisk gjenoppretting. Øvrige isolerte tester bruker testmiljø.

```sh
source /workspace/.cloud/aksje-app-env.sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium \
APP_ENVIRONMENT=test APP_RUNTIME_ROOT=/workspace/.audit-167/production-verification-final \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --junitxml=/workspace/.audit-167/production-verification-final.xml
```

Bruk egen disponibel testdatabase og korrekt Chromium-sti i andre miljøer.
De to live Yahoo-testene forsøkes separat; de skjules ikke som bestått eller skips.
Kjør også alle 24 releasekontrakter fra workflowen, runtime- og avhengighets-
verifikatorene og Node-kontrollen for rapportdeling.

PR #166-kontroll: separat detached testkopi med siste applikasjonsfiler fra #167,
kun #166-endringen i superfund_presentation.py og en ekstra AppTest som tegner
samme fond i to chart_scope-er. Kjør alle tests/test_superfund_*.py med browser
og PostgreSQL aktivert, pluss AppTest-en. Ingen #166-kode merges inn i #167.
Native fondsprobe sammenligner NOK/USD/EUR ved opprettelse, kjøp, 40 % delsalg
og fullt salg. Alle tolv økonomiske projeksjoner sammenlignes med main.

Tre manuelle, ekstra operative testprober ligger dokumentert i
[operativ-regresjon.md](operativ-regresjon.md). De er supplerende kontroller,
ikke nye, skjulte tall i fullpakkens antall. Alle bruker de samme isolerte
produksjonsfixture-ene fra tests/test_production_restart.py.

Kildekontrakten for læringsbroen i test_v1980_shared_execution_accounts_export.py
verifiserer nå faktisk AST-kall/argumenter fremfor et bestemt linjeinnrykk.
Det innebærer ingen svekkelse av regnskaps-/atferdstestene. Original upstream-
og læringsprobe-policy er sammenlignet strukturelt med utgangspunktet; se
strategibevaring.json. Siste kjørings tall og kildefingeravtrykk ligger i
testresultater.json og sluttkjoring.txt.
