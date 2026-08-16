# Deploy RC16.31j

1. Bruk FULL-pakken som komplett kilde, eller legg DELTA-pakken over den deployede `v19.22.0-rc16.31f`-kilden.
2. Deploy én gang og vent til alle Render-tjenestene er `Live`.
3. Kontroller at app og Pushover viser `v19.22.0-rc16.31j`.
4. Kjør **Full systemkontroll**. Leveransekontrollen skal være grønn; eventuelle gule driftsvarsler skal ha en konkret forklaring.
5. Kontroller Paper-skannerens heartbeat og at siste vellykkede skann får et nytt tidspunkt i et åpent markedsvindu.
6. La én fast rapport kjøre. Kontroller evidensdekning/topp 3 og åpne PDF-en med **Last ned PDF** på mobil.
7. Kontroller Shadow-porten. `RED` betyr at ny kjede fortsatt er sperret og ikke skal gjøres autoritativ.

Ingen databaseendring eller sletting er nødvendig. Eksisterende produksjonsbinding og investeringsgrenser beholdes.
