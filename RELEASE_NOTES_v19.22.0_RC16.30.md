# v19.22.0-rc16.30 – instrumentert Autonomi-testkandidat

RC16.30 retter fremdriftsblindsonen dokumentert i
`MBJ-20260809-104534-BF4F84`.

- Intern Autonomi-fremdrift publiseres fra ti reelle delsteg.
- Hvert delsteg fungerer også som kontrollpunkt for tilbakekalt workerlease.
- Autonomi har 900 sekunders maksimal stillhet, mot tidligere 300 sekunder.
- Den tidligere RC16.29-rettelsen for `action`/`side`-normalisering beholdes.
- Diagnosepakker skiller `CURRENT_RUN` fra `PREVIOUS_RUN`-aksept.
- Produksjonsporter og virkelige handler er uendret.

Versjonen er en testkandidat til Stabilisering og er ikke livegodkjent før en
full rapportkjede ender `COMPLETED` med PDF og Pushover.
