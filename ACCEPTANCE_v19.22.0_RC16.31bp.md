# Acceptance RC16.31bp

PASS krever:

- Web og scheduler kjører samme RC16.31bp commit.
- Regime-status overlever normal Streamlit-rerun/nettleserreload etter at status er beregnet.
- Makro-status overlever normal Streamlit-rerun/nettleserreload etter at status er beregnet.
- Toppbaren viser siste oppdateringstid for regime og makro når snapshot finnes.
- Learning viser controlled-learning daily-state (status/aktive/sist oppdatert) når denne finnes, og viser ikke feilaktig null kun fordi forecast-learning counter er tom.
- Ingen regresjon i markedsstatuschips, Fresh Trend, kort rapport eller beslutningsporter.
