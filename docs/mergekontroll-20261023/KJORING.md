# Gjenta siste regresjonskontroll

Kontrollens main- og #166-SHA-er står i rapporten. Hent dem før sammenligning;
bruk separate detached worktrees, isolerte runtime-mapper og ingen produksjons-URL.
Ikke merge PR #166 inn i arbeidsgrenen for å gjenta kompatibilitetsprøven.

## Felles ordinære prober mot main

Kopier kun `tests/test_ordinary_pr167_regression.py` til main-testkopien.
Kjør fra main-kopiens arbeidsmappe med dens PYTHONPATH og eksplisitt forventet rot:

```sh
ORDINARY_EXPECTED_ROOT=<main-worktree> PYTHONPATH=<main-worktree> \
APP_ENVIRONMENT=test APP_RUNTIME_ROOT=<separat-test-runtime> \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
python -m pytest tests/test_ordinary_pr167_regression.py -k baseline -q
```

De 13 tilleggstilfellene gjelder rettet risikotilsyn og inngår ikke i felles
main-baseline. På arbeidsgrenen kjøres hele filen og `test_restart_startup_guards.py`.

## Kombinasjon med #166

Lag en separat kopi av gjeldende #167. Bruk `git diff main...<166-SHA> --
superfund_presentation.py` og `git apply --check` / `git apply` bare i testkopien.
Kjør alle `tests/test_superfund_*.py` med `SF_BROWSER_TEST=1`, Chromium og isolert
`TEST_POSTGRES_URL`. Kontrollens første kombinasjonskjøring manglet denne variabelen;
hele kombinasjonssuiten ble derfor kjørt på nytt med PostgreSQL aktivert.
Alle 154 tester besto uten skips.

Ekstra Streamlit-probe: kall `render_development_chart` to ganger på samme fond
med to daterte `price_history_nok`-punkter og chart_scope `portfolio` / `ranking`.
AppTest skal ha to selectbox-er, to plotly-grafer og ingen exception. Dette tester
den konkrete feilen som #166 retter. Endringen er ikke kopiert til #167.

Den differensielle fondsproben kjører native `cycle` med samme syntetiske fond i
NOK/USD/EUR ved priser 100/100/105/106 over fire dager, med 40 % delsalg og deretter
fullt salg. Sammenlign kontanter, beholdningsantall, cost_nok, last_nok, pris/PnL
per handel og NAV-historikk. Tilleggsfelter for journalproveniens sammenlignes ikke
som om de var endrede økonomiske resultater.

## Full isolert sluttkjøring

```sh
source /workspace/.cloud/aksje-app-env.sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium \
APP_ENVIRONMENT=test APP_RUNTIME_ROOT=/workspace/.audit-167/resume-final \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --junitxml=/workspace/.audit-167/resume-final.xml
```

Kjør også de 24 releasekontraktene fra release-workflowen, runtime- og
avhengighetskontroll samt `node scripts/verify_report_share.mjs`.
Leverandørtestene forsøkes separat, og HTTP 403 telles ikke som bestått.
