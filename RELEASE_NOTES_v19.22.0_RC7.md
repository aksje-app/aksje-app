# AI Aksje Analyzer Pro v19.22.0 Investor Edition RC7

## Formaal

RC7 retter en grunnleggende konflikt mellom ytre kontrollsenter-rute og indre arbeidsflater. Konflikten kunne gi ekstra Streamlit-reruns, feil side etter manuell oppdatering og midlertidig stablet eller gjentatt innhold.

## Rettet

- Hvert synlig hovedpanel har naa én kanonisk URL-rute.
- Autonomi-kontrollsenteret og Autonomi-fanene skriver ikke lenger vekselvis `control_center` og `autonomy`.
- Rapporter, Oversikt og andre Autonomi-arbeidsflater etablerer radiotilstanden foer innholdet rendres.
- En engangsforespoersel om `aa_tab=reports` forblir Rapporter etter neste rerun i stedet for aa falle tilbake til Oversikt.
- `aa_tab` gjenopprettes bare i arbeidsflaten som eier fanen. Autonomi, Paper Trading og AI Discovery forurenser ikke lenger hverandres fanetilstand.
- Paper Trading bruker `paper_trading` som kanonisk rute og veksler ikke mot `control_center`.
- Vedvarende UI-state lagrer fanen som tilhoerer det aktive panelet, ikke en gammel fane fra et annet panel.
- Valutavarsler beholder rutebeskyttelsen fra RC6.

## Uendret

- `final_score`, kandidatvalg, rangering og beslutningsregler.
- Valutakursinnhenting, valutagrenser, Pushover-logikk og Render Cron.
- Innlogging og Husk meg.
- Rapporttidene 08:00 og 22:00 Europe/Oslo.
- Paper Trading- og produksjonshandelsregler.

## Lokal validering

- 652 tester og 4 deltester bestått, 0 feil.
- 29 målrettede rute- og rendertester bestått.
- Python-kompilering bestått.
- Full systemaudit bestått med 0 feil og 0 advarsler.
- Lokal Streamlit-oppstartssmoke var blokkert fordi testmiljøet ikke hadde en tilgjengelig Streamlit-distribusjon. Faktisk oppstart må derfor kontrolleres på Render.
