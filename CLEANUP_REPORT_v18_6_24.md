# Cleanup report v18.6.24

Utført trygg opprydding uten .env/secrets.

## Endringer
- Fjernet UTF-8 BOM fra Python-/testfiler. Dette gjør AST-verktøy, pytest-innsamling og statiske sjekker mer robuste.
- Ryddet `alpha_radar_engine.py`: fjernet en gammel/overstyrt `_insider_evidence` + `_evidence_items`-implementasjon som returnerte feil antall evidence-bøtter sammenlignet med aktiv kode. Den aktive 4-bøtte-implementasjonen er beholdt.
- Kjørte `python -m compileall -q .` etter endring: OK.

## Teststatus i dette miljøet
- `pytest -q` stopper fordi miljøet mangler runtime-pakker (`streamlit`, `yfinance`). Dette er ikke en kodefeil i prosjektet, men manglende installerte avhengigheter i sandboxen.
- `requirements.txt` inneholder disse pakkene, så test bør kjøres på PC-en din etter `pip install -r requirements.txt`.

## Videre anbefalt rydding
- `app.py` er svært stor og bør på sikt deles i moduler, men jeg har ikke gjort stor refaktor i denne pakken for å unngå regresjoner.
- Det finnes fortsatt noen bevisste/kompatible duplikat-aliaser i `insider.py`, `paper_store.py` og `workspace_layout.py`. De bør bare fjernes etter en full lokal test med alle avhengigheter.
