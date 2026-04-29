# Steg 1–2: 24/7 scanner + paper trading

## Nye filer
- `scanner_worker.py` - kjøres av Render Cron Job eller Background Worker
- `paper_trading.py` - fiktiv portefølje, kjøp/salg og handelslogg
- `app.py` - ny fane: Paper Trading

## Render Cron Job
Lag en ny Cron Job i Render som bruker samme GitHub repo.

Command:

```bash
python scanner_worker.py
```

Schedule eksempel:

```text
*/5 * * * *
```

Dette scanner hvert 5. minutt.

## Environment Variables
Legg inn på Cron Job også:

```text
FINNHUB_API_KEY
PUSHOVER_APP_TOKEN
PUSHOVER_USER_KEY
PAPER_START_CASH=100000
PAPER_POSITION_SIZE=10000
PAPER_TRADING_ENABLED=true
SCANNER_MARKET=ALL
SCANNER_MAX_TICKERS=30
SCANNER_MIN_CONFIDENCE=70
```

## Viktig
Dette er paper trading, ikke ekte penger.
For ekte 24/7 må Cron Job kjøre selv om webappen sover.
