# Operatørforløp og testkjøring

Verktøy: `scripts/prepare_simulation_restart.py`.
Krever eksisterende Python-avhengigheter, OpenSSL og en `pg_dump`-klient som
støtter databaseserverens versjon. Operatørkonfigurasjonen holdes utenfor Git.

Konfigurasjonens databasefelt inneholder miljøvariabelnavn, aldri passord:

```json
{
  "archive_root": "/VARIG_PRIVAT_ARKIV",
  "certificate": "/OFFLINE_OFFENTLIG_SERTIFIKAT.pem",
  "runtime_roots": {"runtime": "/FAKTISK_RUNTIME"},
  "database_environment_variables": {"database": "MODEL_ARCHIVE_DATABASE_URL"},
  "coverage_confirmed": true,
  "coverage": {
    "portfolios": ["database", "runtime"],
    "trades": ["database", "runtime"],
    "decisions_and_signals": ["database", "runtime"],
    "reports": ["database", "runtime"],
    "nav_and_results": ["database", "runtime"],
    "learning_models_and_observations": ["database", "runtime"],
    "strategy_parameters": ["database", "runtime"],
    "audit_and_diagnostics": ["database", "runtime"]
  }
}
```

Dette er en strukturmal, ikke et kontrollert produksjonsinventar. Ta med alle
faktiske ekstra mapper/databaser/rapportlagre. Ikke sett inventaret bekreftet
før dette er gjennomgått. Arkivroten må ha privat 0700-tilgang og ligge utenfor
aktive runtime-trær og repositoryet. Sertifikat og privat nøkkel må beholdes
under separat nøkkelforvaltning; ingen nøkkel genereres eller publiseres automatisk.

Fremtidig operatørforløp:

1. Inventer og drainer/pause alle relevante skrivere ved et avsluttet
   modellcheckpoint. Ikke tøm observasjoner eller endre strategiparametere.
2. Kjør `archive --config <privat-fil> --sources-quiesced`. Databaser leses fra
   de oppgitte miljøvariablene; URL-er sendes ikke som prosessargumenter.
3. Kjør `review --config <privat-fil> --archive-id <ID> --private-key-file <offline-nøkkel>`.
   Verifiser også databasegjenoppretting i et separat miljø før operativ overgang.
   Verktøyet gjenoppretter aldri produksjonsdatabasen.
4. Kjør `plan` med `--period-id`, `--start-at` (tidssone påkrevd) og `--actor`.
5. Kjør `prepare` med de samme feltene, arkiv-ID og privat nøkkel. Alle tre
   kontoer blir inaktive utkast i egne nøkler. Gamle posisjoner selges ikke.
6. Gjennomgå kontoer, arkivbevis, kildebevaring og eksplisitt motoromkobling.
   Verktøyet inneholder ingen produksjonsaktivering eller reset-kommando.

Det er ikke gjennomført et slikt produksjonsforløp i dette miljøet.

Automatisk kontroll bruker utelukkende isolert testdatabase og testmapper:

```sh
source /workspace/.cloud/aksje-app-env.sh
SYSTEM_BROWSER_TEST=1 SF_BROWSER_TEST=1 BROWSER_EXECUTABLE=/usr/bin/chromium \
APP_ENVIRONMENT=test APP_RUNTIME_ROOT=/workspace/.audit-167/restart-verified \
DATABASE_URL='' AUTH_DATABASE_URL='' PAPER_TRADING_ENABLED=true \
TEST_POSTGRES_URL=postgresql://test@127.0.0.1:55432/entry_exit_test \
python -m pytest -q --tb=short -p no:cacheprovider \
  --ignore=tests/test_superportfolio_live_ohlc_acceptance.py \
  --junitxml=/workspace/.audit-167/restart-verified.xml
```

Nye tester: `tests/test_simulation_restart.py` og seks forløp i
`tests/test_system_revision_browser.py`. PostgreSQL-testen bruker installerte
klienter, eller klientene i containeren som faktisk betjener fixture-porten.
Den gjenoppretter bare til en ny, midlertidig localhost-testdatabase.

Eksterne Yahoo-tester holdes separat fra den isolerte pakken og skal ikke
regnes som bestått uten fungerende leverandørtilgang. Tidligere kilde- og
nettverksbegrensninger står fortsatt uavklart; dette er ikke grunnlag for å
rekonstruere data eller starte produksjonskontoer.
