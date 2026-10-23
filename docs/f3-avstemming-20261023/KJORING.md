# Kjøring og kildegrenser

Bruk Python-miljøet og isolert localhost-PostgreSQL fra
[forrige kjøreveiledning](../f3-20261023/KJORING.md).

```sh
source /workspace/.cloud/aksje-app-env.sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium \
AUDIT_CONTROL_OUTPUT=/workspace/.audit-167/phase2-ui-final \
APP_RUNTIME_ROOT=/workspace/.audit-167/phase2-verified APP_ENVIRONMENT=test \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --durations=10 --junitxml=/workspace/.audit-167/phase2-verified.xml
```

Live-testene kjøres separat uten erstatningsdata:

```sh
python -m pytest -q tests/test_superportfolio_live_ohlc_acceptance.py --tb=short
```

Nye tester heter `tests/test_economic_events.py` og
`tests/test_production_reconciliation.py`; nettlesertestene ligger i
`tests/test_system_revision_browser.py`. Alle testdata der er syntetiske.
Databasefixturen avviser eksterne verter og bruker egne, midlertidige skjemaer.
Nettleserfixturen erstatter innlogging og blokkerer eksterne tjenester.

Et senere produksjonsuttrekk krever en allerede tilgjengelig skrivebeskyttet
forbindelse i `F3_READONLY_DATABASE_URL`. Ikke sett en syntetisk lokal database
som denne variabelen for å fremstille en produksjonskontroll. Legg ikke
forbindelsesstrengen i kommandoargumenter, logger, rapporter eller GitHub.

```sh
python scripts/f3_readonly_inventory.py \
  --output /workspace/.private-f3-phase2/readonly-export.json
```

For et originalt diagnosearkiv brukes `--archive` og en privat utfil utenfor
checkout. Verktøyet inspiserer arkivet, men normaliserer ikke gamle modellvekter
eller antar manglende økonomiske opplysninger. Lagre originalene uendret og
kontroller SHA256 og eksporttid. Verken utdata, arkiver, rapportvedlegg eller
uttrekksfiler skal legges til PR-en.

Først etter kildekontroll kan et dokumentert grunnlag gis til
`services.production_reconciliation.assess`. Ingen av disse verktøyene aktiverer
produksjonskontoer, kaller appens porteføljelastere eller kjører migreringer.

Kjør også avhengighets-/runtime-verifikasjon, de 24 releasekontraktene og
`node scripts/verify_report_share.mjs`. Lokal full råevidens ligger under
`/workspace/.audit-167/`; selve kilde-/avstemmingsstatusen uten produksjonsverdier
kan publiseres som dokumentasjon.
