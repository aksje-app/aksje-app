# Deploy v19.14.5

## Render testmiljø

Behold:

```text
STORAGE_MODE=local
APP_RUNTIME_ROOT=/var/data/app_runtime
APP_RUNTIME_PERSISTENT=true
ALLOW_LOCAL_STORAGE_FALLBACK=true
PAPER_TRADING_ENABLED=false
REPORT_SCHEDULER_ENABLED=false
RUNTIME_BACKGROUND_ENABLED=false
```

Persistent disk skal være montert på `/var/data`.

Slett miljøvariabelen `STREAMLIT_SERVER_USE_STARLETTE` dersom den fortsatt finnes.
`DATABASE_URL` skal ikke opprettes i dette isolerte lokale testmiljøet.

Etter deploy skal én kort REPORT-smoketest kjøres før en full UTKAST-kjøring.
