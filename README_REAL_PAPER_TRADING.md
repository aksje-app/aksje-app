# Ekte paper trading med felles lagring

Viktig:
Cron Job og Web App deler ikke automatisk samme lokale filsystem.
For at kjøp gjort av Cron Job skal vises i webappen, bruk `DATABASE_URL`.

Nytt:
- `paper_store.py`: felles database-lagring
- `paper_trading.py`: ekte simulert kjøp/salg med posisjoner, cash og trade history
- støtter Postgres via `DATABASE_URL`
- fallback til lokal SQLite hvis `DATABASE_URL` mangler
- varsler viser priser med 2 desimaler

Legg `DATABASE_URL` inn på både:
- Web Service
- Cron Job

Dette er fortsatt paper trading, ikke ekte handel.
