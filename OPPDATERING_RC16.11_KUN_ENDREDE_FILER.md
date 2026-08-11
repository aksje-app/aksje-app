# Oppdatering til v19.22.0-rc16.11

Pakk innholdet over eksisterende RC16.10-installasjon og tillat overskriving. Start deretter applikasjonen på nytt.

Endrede kjernemoduler:

- `market_intelligence.py`
- `report_replay_export.py`
- `report_integrity.py` – må overskrives for å fjerne eldre full-rangeringsport i eksisterende installasjoner.
- `app_version.py`

Nye tester og RC16.11-dokumentasjon følger delta-pakken. `assets/fonts/` er uendret fra RC16.10 og trenger ikke lastes opp på nytt dersom mappen allerede finnes i GitHub.
