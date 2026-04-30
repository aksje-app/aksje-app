# Cron Indentation Fix

Fikser:
`IndentationError: expected an indented block after 'if' statement`

Endring:
- `scanner_worker.py` er skrevet om til en ren, trygg versjon
- ingen gamle direkte signalvarsler
- varsel sendes bare når en faktisk paper trade skjer
- DB schema migration kjøres ved oppstart

Etter deploy:
1. Deploy Web Service
2. Deploy Cron Job
3. Trigger Run
