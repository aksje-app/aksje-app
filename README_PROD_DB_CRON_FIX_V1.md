# Prod DB + Cron Fix v1

Fikser:
- Trading-regler ble lagret lokalt selv om DATABASE_URL var satt.
  Årsak: trading_settings.py importerte init_store(), men paper_store.py hadde bare init_db().
  Løsning: paper_store.py har nå init_store() alias.

- Cron-feil:
  scanner_worker.py importerte build_trading_decision fra signal_engine.
  Løsning: signal_engine.py har nå build_trading_decision() wrapper.

- check_db.py er lagt ved for Render Shell:
  python check_db.py

Etter deploy:
1. Deploy Web Service
2. Deploy Cron Job
3. Åpne appen og trykk Lagre trading-regler
4. Den skal vise "Lagret i database ✅"
5. Trigger Cron Run og sjekk at import-feilen er borte
