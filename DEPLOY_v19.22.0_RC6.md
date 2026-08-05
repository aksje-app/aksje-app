# Deploy v19.22.0 RC6

## Base

Deploy FULL-pakken for v19.22.0 RC6. Ikke kombiner kildefiler fra eldre pakker.

## Formaal

RC6 er en avgrenset navigasjonsretting for Valutavarsler. Valutakurslogikken og Render Cron-oppsettet fra RC5 beholdes uendret.

## Live kontroll

Etter deploy:

1. Aapne Valutavarsler fra menyen.
2. Trykk «Hent kurs naa» og bekreft at Valutavarsler fortsatt er aktiv side etter oppdateringen.
3. Trykk «Sjekk valutagrense naa» og bekreft at siden ikke hopper til Oversikt i Autonomi.
4. Trykk «Send Pushover-test med fersk kurs» og bekreft samme side, fersk kurs og korrekt status.
5. Kjoer «Test hele varselkjeden» og bekreft at Valutavarsler fortsatt er aktiv side.
6. Lagre varseloppsettet og bekreft at Valutavarsler fortsatt er aktiv side.
7. Gjenta kontrollene paa mobil og desktop.
8. Bekreft at direkte menyvalg, nettleseroppdatering og tilbakekomst etter innlogging fortsatt aapner riktig side.

## Uendret drift

- Render Cron kjører fortsatt hvert femte minutt.
- Morgenrapport 08:00 og kveldsrapport 22:00 Europe/Oslo er uendret.
- `final_score`, kandidatvalg og handelsregler er uendret.

RC6 er ikke produksjonsgodkjent foer kontrollene over er dokumentert paa Render.
