# RC16.31ch – Jeep Commander 2.2

Denne versjonen legger til et midlertidig, isolert bruktbilsøk. Modulen påvirker ikke analyse, rapporter, læring, portefølje eller handelsregler.

## Søkevalg

- Modellår: 2025, 2026 eller begge samlet.
- Brasilianske årpar tolkes som fabrikasjonsår/modellår: `2025/2026` filtreres som modellår 2026, mens `2026/2027` ikke blandes inn i 2026-søket.
- Kilometer: inntil 20 000 eller inntil 35 000 km.
- Område: Fortaleza/Ceará, Nordøst-Brasil eller hele Brasil.
- Sort prioriteres, men rimeligere andre farger kan tas med.
- Automatisk kontroll hvert 15. minutt via eksisterende Render Cron.

## Varsler og drift

- Første vellykkede kjøring lager en stille referanse og sender ikke en varselflom.
- Pushover sendes for nye annonser, reelle prisfall og tydelig bedre tilbud.
- Mislykkede Pushover-leveringer beholdes og forsøkes igjen.
- Meldingen viser pris, kilometer, år, farge, sted/delstat, lokalitet eller omtrentlig delstatsavstand, pris mot median, kilde og direkte annonselenke.
- Kildeblokkering eller ukjent nettsidestruktur vises som kildefeil, aldri som falske null treff.
- Vanlige server-renderte bilkort fra OLX, Webmotors og Mobiauto leses også når siden ikke leverer JSON-LD/Next-data.
- Kildestatus viser antall leste annonser, og filterdiagnosen teller konkret hvorfor annonser ble avvist.
- Modulen utløper automatisk etter 90 dager hvis datoen ikke endres, og kan deaktiveres eller få egne data slettet manuelt.

## Deploy

Pakk ut den rene deltaen over eksisterende RC16.31cg-programfiler og oppdater `EXPECTED_APP_VERSION` på Render til `v19.22.0-rc16.31ch`. Web og scheduler må kjøre samme commit/versjon.

Etter deploy må første manuelle søk kontrolleres i modulen. Nettmarkedsplasser kan endre eller blokkere offentlig HTML; denne produksjonskontrollen kan ikke bevises lokalt.
