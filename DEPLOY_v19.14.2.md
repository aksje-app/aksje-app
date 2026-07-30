# Deploy v19.14.2

## Test først

Deploy bare til den isolerte Render-tjenesten fra en egen stabiliseringsgren. Produksjonstjenesten skal fortsette på `main` til akseptansen er bestått.

## Obligatoriske testvariabler

```text
APP_ENVIRONMENT=test
PAPER_TRADING_ENABLED=false
ALLOW_PAPER_TRADING_IN_TEST=false
RUNTIME_BACKGROUND_ENABLED=false
REPORT_SCHEDULER_ENABLED=false
ALLOW_BACKGROUND_IN_TEST=false
ALLOW_SCHEDULER_IN_TEST=false
ALLOW_NOTIFICATIONS_IN_TEST=false
ALLOW_DATABASE_IN_TEST=false
```

Ikke legg inn `DATABASE_URL`, Pushover-nøkler eller produksjonsnøkler i første testfase.

## Render-kommandoer

```text
Build Command: pip install -r requirements.txt
Start Command: streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Kontroll etter deploy

1. Kontroller gren og commit i testbanneret.
2. Kontroller at Paper Trading, scheduler, bakgrunn og varsling står AV.
3. Åpne `/` og `/_stcore/health`.
4. Utfør akseptanselisten uten produksjonsdata.
5. Merge til `main` er forbudt før alle obligatoriske punkter er dokumentert.

## Produksjon

Produksjon krever eksplisitt vurdering av hver sikkerhetsvariabel. `PAPER_TRADING_ENABLED=true` skal aldri settes som en indirekte standard; aktivering skal være en bevisst miljøendring etter godkjent test.
