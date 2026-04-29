# Pro risk + dashboard-pakke

Nytt:
- Kun topp 3 trading-kandidater per run
- Maks trades per dag via `MAX_TRADES_PER_DAY`
- Stop-loss i paper trading
- Trailing stop i paper trading
- Performance dashboard i appen
- Klar struktur for ekte trading senere med `broker_adapter.py`
- Live trading er IKKE aktivert

Anbefalte Environment Variables:
```text
MAX_TRADES_PER_DAY=3
PAPER_STOP_LOSS_PCT=0.06
PAPER_TRAILING_STOP_PCT=0.08
PAPER_POSITION_SIZE=10000
SCANNER_MIN_CONFIDENCE=70
```

Dette er fortsatt paper trading og analysehjelp, ikke investeringsråd.
