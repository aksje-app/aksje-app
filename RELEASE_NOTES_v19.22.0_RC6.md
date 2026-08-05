# AI Aksje Analyzer Pro v19.22.0 Investor Edition RC6

## Formaal

RC6 retter at handlinger i Valutavarsler sendte brukeren tilbake til Oversikt i Autonomi etter Streamlit-rerun.

## Rettet

- «Hent kurs naa» beholder Valutavarsler som aktiv side.
- «Sjekk valutagrense naa» beholder Valutavarsler som aktiv side.
- «Send Pushover-test med fersk kurs» beholder Valutavarsler som aktiv side.
- Helkjedetest og lagring av varseloppsett bruker samme navigasjonssikring.
- En eksplisitt engangs-rutelaas synkroniserer hovedgruppe, aktivt panel og radioverdier foer kontrollsenteret rendres paa nytt.
- Valutavarsler er plassert stabilt under «Marked og signaler», ogsaa naar autonomisentrert applikasjonsmodus er aktiv.
- Hoved- og reservekopien av sidebarnavigasjonen bruker samme rute.

## Uendret

- Autoritativ valutakursinnhenting, grensestatus og Pushover-logikk fra RC5.
- Render Cron og kontrollintervall.
- `final_score`, kandidatrekkefølge og beslutningsregler.
- Rapporttidene 08:00 og 22:00 Europe/Oslo.
- Produksjonshandel og Paper Trading-regler.
