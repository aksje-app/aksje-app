# Roadmap fase 2 – tekniske signaler ved tapskjøp

Kilde: Render `autonomous_portfolio/trades.json`, read-only, 15.10.2026.

Tre registrerte `THEORETICAL_ONLY`-kjøp, VTURA.OL 23.09, AKER.OL 15.09 og CMBTO.OL 12.10, hadde investeringsscore henholdsvis 73,77, 73,99 og 73,53, men samtidig `technical_signal_raw_decision=HOLD / WAIT` og `technical_timing=NEUTRAL`. Etterfølgende salg var stop-loss med −10,64 %, −5,22 % og −8,14 %. Feltene `technical_entry_wait=false`, `technical_contribution_points=0`, `technical_can_authorize_execution=false` er registrert ved alle tre kjøp.

Dette **beviser ikke** at teknisk HOLD var årsak til tapene, eller at teknisk BUY ville gitt lønnsomme handler. Det viser et testbart misforhold mellom teknisk vurdering og scorebasert kjøpsbeslutning. Den tekniske bidragsmodellen i `autonomous_portfolio.py` er laget for å la basismotoren fungere uavhengig av teknisk signal; `hard_gates_unchanged=true`.

**Testkandidat for fase 3:** Sammenlign eksisterende inngangsregler mot et ekstra krav om dokumentert positiv teknisk bekreftelse etter HOLD/WAIT. Bruk *alle* historiske kjøp, samme informasjon tilgjengelig ved kjøpstidspunkt, handelskostnader og eksponeringsbegrensninger; rapporter både tap unngått og vinnere som ville blitt blokkert. Ikke innfør hard teknisk sperre ut fra tre utvalgte tapshandler alene.

Kontroller videre tidsstempler og kjøpstidspunkt mot markedets åpningstid. Ikke tolke `holding_days=0` som prisfeil uten særskilt kursbevis. Ingen produksjonsparametere endres i denne revisjonen.
