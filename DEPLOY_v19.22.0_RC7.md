# Deploy v19.22.0 RC7

## Base

Deploy FULL-pakken for v19.22.0 RC7. Ikke kombiner kildefiler fra eldre pakker.

## Formaal

RC7 er en sentral navigasjons- og renderstabilisering. Den erstatter motstridende ytre og indre ruter med én kanonisk rute per synlig panel.

## Live kontroll paa Render

1. Aapne Autonomi -> Rapporter og bekreft at bare én Rapporter-visning rendres.
2. Oppdater nettleseren manuelt minst fem ganger og bekreft at Rapporter fortsatt er aktiv fane.
3. Bytt mellom Oversikt og Rapporter og bekreft at URL, valgt fane og synlig innhold alltid er enige.
4. Kontroller at innhold ikke blir stablet eller gjentatt nederst paa siden under rerun.
5. Gjenta kontrollen for alle Autonomi-arbeidsflater.
6. Aapne Valutavarsler og kjoer Hent kurs, Sjekk valutagrense og Pushover-test. Siden skal forbli Valutavarsler.
7. Aapne Paper Trading, bytt fane, oppdater nettleseren og bekreft samme fane.
8. Kontroller Analyse, Top Picks, Long Engine, System og generiske kontrollsenterpaneler etter refresh.
9. Kontroller tilbake/fram i nettleseren og direkte menylink.
10. Maal at en stabil side ikke gaar inn i gjentatt rerun eller kontinuerlig URL-endring.
11. Bekreft at innlogging, Husk meg, scheduler og Pushover fungerer uendret.

## Uendret drift

- Render Cron og valutakontroll er uendret fra RC6/RC5.
- Morgenrapport 08:00 og kveldsrapport 22:00 Europe/Oslo er uendret.
- `final_score`, kandidatvalg og handelsregler er uendret.

RC7 er ikke produksjonsgodkjent foer kontrollene over er dokumentert paa Render.

## Lokal teststatus

- 652 tester og 4 deltester bestått, 0 feil.
- 29 målrettede rute- og rendertester bestått.
- Full systemaudit: 0 feil og 0 advarsler.
- Lokal Streamlit-oppstartssmoke kunne ikke kjøres i testmiljøet fordi Streamlit-distribusjonen ikke var tilgjengelig. Render-oppstart er derfor et eksplisitt deploykrav.
