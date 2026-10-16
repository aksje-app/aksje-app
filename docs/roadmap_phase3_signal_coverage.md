# Roadmap fase 3 – dekningskontroll før testing av teknisk inngang

Lesekontroll av Render `autonomous_portfolio/trades.json`, 15.10.2026. Blant 39 registrerte BUY-hendelser har 22 `technical_signal_raw_decision=HOLD / WAIT`, mens 17 mangler feltet. Det er ikke registrert en observerbar gruppe med `BUY`-signal i disse dataene. 36 SELL-hendelser finnes.

Konsekvens: Ingen valid sammenligning mellom teknisk bekreftede kjøp og HOLD/WAIT-kjøp kan beregnes direkte fra denne loggen. Manglende signal er UKJENT, ikke BUY. All retrospektiv omklassifisering krever samtidige signaldata og dokumentert tidspunkt; ingen fremtidig informasjon må brukes.

Før endring: (1) finn fullstendige samtidige tekniske signaler for historiske innganger om lagret; (2) beregn parvis netto-utfall for samme utvalgsunivers og tidspunkt, med kostnader og avviste vinnere; (3) kontroller om HOLD/WAIT betyr nøytral teknisk vurdering eller eksplisitt ventekrav i faktisk produksjonslogikk; (4) avvis hypotese hvis datadekning er utilstrekkelig.

Dette er et datakvalitetsfunn, ikke grunnlag for ny hard produksjonssperre. Ingen produksjonsparameter er endret.
