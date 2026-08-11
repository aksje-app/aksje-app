# v19.22.0-rc16.13

- Startknappen og livestatusen for komplett rapport-, replay- og læringsarkiv ligger i samme statiske Streamlit-fragment.
- Knappetrykk starter eksportworkeren og viser den returnerte eksportstatusen direkte i fragmentet.
- Full `st.rerun()` er fjernet fra ZIP-oppstarten.
- Fragmentet poller fortsatt status, prosent, arbeidsenheter og heartbeat hvert tredje sekund.
- Den gamle terminalstatusen erstattes når en ny jobb faktisk startes.
- RC16.12-håndteringen av karantene, markedsrekkefølge og hard offentlig PDF/TXT/JSON-audit er beholdt.

Ingen analyse-, score-, scheduler-, portefølje- eller handelsregler er endret.
