# v19.22.0-rc16.34b – Super Portfolio E2E Repair

## Formål
Lukke den gjentatte feilen der Super Portfolio-knapper endret intern navigasjonstilstand uten å vise selve porteføljen.

## Rettet
- Super Portfolio er nå en førstklasses arbeidsflate under **Marked og signaler**.
- Direkte åpning rendrer Super Portfolio før legacy-dashboardet og stopper der.
- Den aktive kontrollsenterimplementasjonen registrerer faktisk Super Portfolio-rendereren.
- Startsiden viser aktive posisjoner med vekt, verdi, P/L, stop-avstand og status.
- Startsideknappen «Åpne hele Super Portfolio» bruker samme dedikerte rute.
- Det kompakte Super Portfolio-kortet viser separate, lesbare statusmeldinger i stedet for stablet råtekst.
- Shell-alias for Super Portfolio peker til Marked, ikke Autonomi.
- Eksisterende porteføljestate, historikk og læring endres ikke.
