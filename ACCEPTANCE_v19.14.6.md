# Akseptanse v19.14.6

Versjonen kan godkjennes i testmiljøet når alle punktene under er dokumentert:

1. Render-build installerer `pypdf==5.9.0` fra `requirements.txt`.
2. `python tools/check_runtime_dependencies.py` returnerer `ok: true`.
3. Oppstartsloggen inneholder ingen `ModuleNotFoundError: pypdf`.
4. Ett nytt UTKAST fullfører REPORT-steget.
5. Den genererte PDF-en kan åpnes og den semantiske PDF/JSON-kontrollen består.
6. Rapporten arkiveres på persistent disk og er tilgjengelig etter sideoppdatering.
7. Paper Trading, scheduler og bakgrunn forblir i den avtalte teststatusen.

Versjonen skal avvises dersom deployen blir Live uten at avhengighetssmoken har bestått, eller dersom REPORT igjen stopper på manglende PDF-leser.
