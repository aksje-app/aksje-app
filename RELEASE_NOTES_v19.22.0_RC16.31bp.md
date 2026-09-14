# RC16.31bp - Durable Topbar Status Closure

Denne versjonen retter de tre globale statusfeltene som fortsatt kunne vise `Regime ikke oppdatert`, `Makro ikke oppdatert` og `Learning: 0` etter Streamlit-rerun eller nettleseroppdatering.

## Endringer

- Markedsregime lagres nå som et varig status-snapshot og gjenopprettes når Streamlit-session mangler.
- Makro/renter/breadth lagres på samme måte.
- Begge feltene viser siste registrerte oppdateringstid i toppbaren.
- Learning-feltet bruker nå den kontrollerte learning-observation-motorens varige daily-state som primærkilde i stedet for bare forecast-learning-statistikken.
- Learning viser status, aktive observasjoner, eventuelt antall oppdaterte observasjoner og siste fullførte tidspunkt.
- Forecast learning brukes kun som kompatibilitetsfallback dersom den kontrollerte learning-state ikke finnes.
- Ingen kjøps-, risiko-, portefølje-, Fresh Trend- eller handelsregler er endret.
