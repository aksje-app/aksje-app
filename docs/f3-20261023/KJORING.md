# Reproduserbar kontroll

Startpunkt var `6bc8b953a898e7090ca6d5d323d985e7b7681224` på
`fix/systemrevisjon-20261022`; både remote-arbeidsgren og PR #167 pekte dit.
Arbeidstreet var rent før oppfølgingen. Python 3.12.13, 70 låste avhengigheter,
Chromium og Docker/PostgreSQL ble kontrollert i skymiljøet.

Bruk oppsettet og den isolerte localhost-databasen beskrevet i
[første kjøreveiledning](../revisjon-20261023/KJORING.md). Ingen produksjons-URL,
produksjonskonto eller ekstern varslingsmottaker skal brukes i disse testene.
Alle nye godkjenninger i testene har `scope=test` og syntetiske bilag.

```sh
source /workspace/.cloud/aksje-app-env.sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 \
BROWSER_EXECUTABLE=/usr/bin/chromium \
AUDIT_CONTROL_OUTPUT=/workspace/.audit-167/f3-ui-controls-final \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
APP_RUNTIME_ROOT=/workspace/.audit-167/f3-final APP_ENVIRONMENT=test \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --durations=10 --junitxml=/workspace/.audit-167/f3-final.xml
```

Denne isolerte pakken omfatter alle tester unntatt de to live-leverandørtestene,
med nettleser- og PostgreSQL-krav aktivert. De to live-testene kjøres separat,
uten å erstatte nettverksfeil med mocks eller hopp:

```sh
python -m pytest -q tests/test_superportfolio_live_ohlc_acceptance.py \
  --tb=short -p no:cacheprovider
```

De feilet i dette miljøet med CONNECT-proxy HTTP 403 mot Yahoo Finance.
Det er en uavklart akseptansekontroll; de regnes ikke som bestått.

Kontroller i tillegg `tools/verify_dependency_lock.py`,
`tools/verify_runtime_v19142.py`, alle 24 kommandoer fra `Release contracts`
i `.github/workflows/quality_release_gate.yml` og
`node scripts/verify_report_share.mjs`.

Nettlesertestene kjører virkelig app.py i isolerte lokale runtime-mapper;
innlogging erstattes, eksterne HTTP-/socketkall blokkeres og bakgrunnsarbeidere
er avslått. Dette er ikke testing av innlogging eller reelle markedsleverandører.
Ruteinventaret viser synlige kontroller; det dokumenterer ikke at alle mulige
ordreknapper eller varslingsutsendelser er funksjonstestet. De eksplisitte
forløpene tester navigasjon, innstillingslagring, mobilmenyer og nedlastinger.

Nye økonomiforløp tester NOK-panel og JSON/CSV-eksport ved 1280 og 375 piksler
for alle tre aksjefamilier, og native Superfond-eksport ved begge bredder.
De forbereder bare syntetiske utkast i `/tmp/aksje-browser-*`; de aktiverer ikke
kontoer via brukergrensesnittet. Backend-testene prøver aktivering med eksplisitt
testgodkjenning, og avviser standard produksjonsaktivering og feil miljøomfang.

Se `testresultater.json`, `sluttkjoring.txt` og `ui-dekning.json` for sluttall.
Midlertidige lokale logger, JUnit-filer og skjermbilder ligger utenfor checkout
under `/workspace/.audit-167/` og er ikke nødvendige produksjonsfiler.
