# Final DB schema fix

Fikser feilen:
`column "take_profit" of relation "paper_positions" does not exist`

Denne versjonen:
- kjører database-migrering automatisk ved oppstart
- legger til manglende kolonner i eksisterende Postgres
- krever ikke sletting av databasen

Etter deploy:
1. Deploy Web Service
2. Deploy Cron Job
3. Trigger Run på Cron Job
4. Hvis appen fortsatt viser gammel feil: trykk "Kjør DB schema fix" i sidepanelet.
