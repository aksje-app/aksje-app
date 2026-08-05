# Kildegrunnlag og baseline-revisjon v19.15.0

## Kilde

Revisjonen er utført mot ZIP-en som ble lastet ned fra den faktisk deployede stabiliseringsgrenen etter v19.14.6. Ingen tidligere fullpakke er brukt som erstatning for denne kilden.

## Baseline før rettinger

- ZIP-integritet: bestått.
- Testresultat: 557 tester bestått, 4 deltester bestått og 1 test feilet.
- Feilen var at `RELEASE_NOTES_v19.14.6.md` manglet i den deployede grenen.
- GitHub-kilden inneholdt 88 mutable filer under `.app_runtime`, selv om `.gitignore` forbød dem.
- En ufullstendig, ikke-aktiv `streamlit_patch_snippet.py` importerte en modul som ikke fantes.
- To varslingsbaner importerte `notification_service` fra feil plassering, og flere kodeveier kunne tolke notifierens `(False, årsak)`-tuple som sann.

## Rapporten som utløste systemrevisjonen

Morgenrapporten `MI-20260730-082306` dokumenterte følgende semantiske avvik:

- Jobbnavnet sa Kjernemarkeder, mens seks markeder faktisk ble kjørt.
- Kandidat-, detalj- og beslutningskontrakt brukte konkurrerende konfidensverdier.
- Evidensdekning var koblet til markedsdatakvalitet.
- Kandidatens porteføljebegrunnelse motsa porteføljestatus og tilgjengelig kapital.
- AAPL-grunnlaget inneholdt fem irrelevante nyhetssaker.
- Sekundære strukturerte insiderdata ble presentert som primærverifiserte.
- Den gamle integritetsporten godkjente rapporten uten feil eller advarsler.

## Revisjonsprinsipp

v19.15.0 kan bare betegnes som produksjonsgodkjent etter ren Render-deploy og dokumentert ende-til-ende-test. Offline tester alene gir statusen offline-verifisert testkandidat.
