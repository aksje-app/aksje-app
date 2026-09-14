# Deploy RC16.31cr

1. Bruk fullpakken dersom deploymetoden erstatter hele programtreet. `jeep_commander_monitor.py` er ikke med i fullpakken.
2. Ved vanlig delta-overlegg kopieres en ufarlig tombstone over den gamle modulfilen; den inneholder ingen nettverk, varsler eller lagring.
3. Deploy web og scheduler fra samme kode og kontroller `v19.22.0-rc16.31cr`.
4. Etter første scheduler-kjøring skal loggen vise `retired_module_cleanup: COMPLETED` eller `ALREADY_COMPLETED`.
5. Jeep Commander skal ikke finnes i menyen eller scheduler-sammendraget som en aktiv jobb.
6. Fjern `DATAFORSEO_LOGIN` og `DATAFORSEO_PASSWORD` fra både web og scheduler i Render når RC16.31cr er bekreftet.

Engangsoppryddingen sletter bare:

- `temporary/jeep_commander_22/config.json`
- `temporary/jeep_commander_22/state.json`

Ingen investeringsdata berøres.
