# Validering v19.22.0-rc16.23

- Python-kompilering: bestått.
- 23 målrettede tester for testmodus, sikkerhetsgrenser, cron, låser, varig PDF, offentlig tokenrute og modulstørrelse: bestått.
- Full regresjon: 762 bestått og 4 deltester bestått.
- 42 eldre tester forventer historiske versjoner, tidligere rapportsemantikk, femminutters cron, webstartet scheduler eller den nå erstattede lokale `/app/static/reports/`-lenken.

Status: `LOCAL_PASS_LIVE_REQUIRED` til en Pushover-test er åpnet på mobil uten aktiv innlogging.
