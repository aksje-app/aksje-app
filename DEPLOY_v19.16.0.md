# Deploy v19.16.0 til isolert Render-testmiljø

## Kilde

Deploy kun den godkjente Git-committen for v19.16.0. Program, ZIP, manifest og Render skal vise samme commit-ID.

## Build

```bash
pip install -r requirements.txt && python tools/check_runtime_dependencies.py
```

## Start

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Varig testlagring

Persistent disk monteres på `/var/data`.

```text
STORAGE_MODE=local
APP_RUNTIME_ROOT=/var/data/app_runtime
APP_RUNTIME_PERSISTENT=true
ALLOW_LOCAL_STORAGE_FALLBACK=true
AUTH_STORAGE_MODE=local
AUTH_STORAGE_ROOT=/var/data/auth
AUTH_STORAGE_PERSISTENT=true
AUTH_REQUIRE_PERSISTENT=true
AUTH_SESSION_RECHECK_SECONDS=60
```

## Skal stå AV under første ende-til-ende-test

```text
PAPER_TRADING_ENABLED=false
REPORT_SCHEDULER_ENABLED=false
RUNTIME_BACKGROUND_ENABLED=false
```

`DATABASE_URL` skal ikke settes i det lokale, isolerte testmiljøet. Produksjonsnøkler og produksjons-Pushover skal ikke kopieres inn.
