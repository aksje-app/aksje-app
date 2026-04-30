# DB migration fix

Fikser Render-feilen:
`psycopg2.errors.UndefinedColumn: column "take_profit" of relation "paper_positions" does not exist`

Årsak:
Databasen hadde en gammel versjon av tabellen `paper_positions`.

Løsning:
`paper_store.py` kjører nå automatisk schema migration:
- legger til `take_profit`
- sikrer `stop_loss`
- sikrer `highest_price`
- sikrer `reason` og `decision` på trades

Du trenger ikke slette databasen.
Last opp filene, deploy Web Service og Cron Job, og kjør Trigger Run igjen.
