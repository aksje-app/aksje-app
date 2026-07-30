# Deploy v19.14.4 – rask driftgjenoppretting

## Testmiljø

Behold `DATABASE_URL` tom for å hindre tilgang til produksjonsdata.

### Alternativ A – separat autentiseringsdatabase

```text
APP_ENVIRONMENT=test
AUTH_STORAGE_MODE=postgres
AUTH_DATABASE_URL=<Internal Database URL for separat testdatabase>
AUTH_REQUIRE_PERSISTENT=true
DATABASE_URL=
PAPER_TRADING_ENABLED=false
```

### Alternativ B – Render persistent disk

Monter disk, for eksempel på `/var/data`, og bruk:

```text
APP_ENVIRONMENT=test
APP_RUNTIME_ROOT=/var/data/app_runtime
APP_RUNTIME_PERSISTENT=true
AUTH_STORAGE_MODE=local
AUTH_STORAGE_ROOT=/var/data/auth
AUTH_STORAGE_PERSISTENT=true
AUTH_REQUIRE_PERSISTENT=true
DATABASE_URL=
PAPER_TRADING_ENABLED=false
```

Alternativ B gir også varig lokal Paper-portefølje og er derfor korteste vei til kontrollert Paper Buy-test.

## Rekkefølge

1. Deploy med Paper Trading AV.
2. Opprett admin én gang.
3. Bekreft Husk meg etter redeploy.
4. Kjør full utkastanalyse og test menybevaring.
5. Bekreft JSON/PDF-integritet.
6. Aktiver manuell Paper Buy kun i testmiljø med:

```text
PAPER_TRADING_ENABLED=true
ALLOW_PAPER_TRADING_IN_TEST=true
```

Scheduler, bakgrunn og Pushover skal fortsatt være AV under første kjøp/salg-test.
