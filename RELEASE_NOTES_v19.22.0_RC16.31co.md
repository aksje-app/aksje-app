# RC16.31co – to timers bilsøk og forbedret kildetreff

- Standardintervall er 120 minutter.
- Standard nattpause er 00:00–07:00 Fortaleza-tid.
- Standard månedsgrense er USD 12.
- Estimert reserve før hvert DataForSEO-kall er korrigert fra USD 0,004 til observerte USD 0,020.
- Separat testtak økes fra USD 0,10 til USD 0,15, slik at én ny kontroll av begge kildene kan fullføres etter tidligere bruk på USD 0,104.
- Tidligere standardkonfigurasjon migreres automatisk én gang; uttrykkelige avvikende brukervalg beholdes.
- Webmotors-søket målrettes mot `/comprar/jeep/commander`.
- OLX-søket målrettes mot bilområdet og inkluderer pris/km-signaler.
- OLX-lenker med vanlig beskrivende slug og lang numerisk annonse-ID godkjennes som enkeltannonser.
- Diagnosevisning og sikker diagnose-ZIP beholdes.

Ved ni kjøringer per døgn og to API-kall per kjøring er estimatet ca. USD 10,80 per 30 dager, basert på observert kostnad USD 0,020 per kall.
