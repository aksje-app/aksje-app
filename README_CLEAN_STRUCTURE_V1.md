# Clean Structure v1

Dette er samme fungerende app som stabil app13-base, men dokumentert og ryddet for videre utvikling.

## Viktige filer

- `app.py`  
  UI / Streamlit-app. App13-design beholdt. RSI-boks/styling beholdt.

- `trading_engine.py`  
  BUY/SELL, stop-loss, take-profit, trailing stop og kompatible UI-funksjoner.

- `paper_store.py`  
  Database / Postgres / lokal fallback. Har `force_schema_migration()` for Cron-kompatibilitet.

- `notifier.py`  
  Pushover-varsler. Varsler kun ved faktisk BUY/SELL.

- `scanner_worker.py`  
  Cron/auto trading. Skal ikke inneholde UI.

- `technical.py`  
  RSI, MACD, Bollinger og teknisk analyse.

- `requirements.txt`  
  Render-avhengigheter.

## Viktig prinsipp

Ingen ny tradinglogikk er lagt til her. Målet er samme funksjon, men bedre struktur og mindre risiko for import-feil.

## Etter deploy

1. Deploy Web Service
2. Deploy Cron Job
3. Trigger Run
4. Sjekk at appen starter
5. Sjekk at Cron ikke får import-feil
