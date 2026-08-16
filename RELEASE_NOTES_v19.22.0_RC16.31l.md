# RC16.31l - Decision Chain Integrity

Denne utgaven reparerer feil som ble dokumentert med full replay av rapport `MI-20260814-220503`. Produksjonsterskelen er fortsatt 73,0.

## Reparert

- Alle beslutningslag bruker én kanonisk, fail-closed kursresolver. `raw.last_price` er nå et gyldig produksjonsfelt.
- Porteføljelag, beslutningstrakt og handelsmotor bruker samme justerte inngangsscore.
- Legacy evidensbudsjett oppgraderes til global Top 20-garanti. Lokal Top 20 søkes i hvert marked før global sammenslåing, slik at global Top 20 aldri kan falle utenfor evidens på grunn av markedskvote.
- Positive aksjetall uten eksplisitt transaksjonstype kan ikke lenger fabrikkere sekundære insiderkjøp.
- Fullført SEC Form 4-kontroll deltar i den offisielle evidensstatusen. Eldre insidercache invalideres med nytt cache-skjema.
- Teknisk `HOLD`, `WAIT` og `NEUTRAL` kan ikke gi positivt scorebidrag.
- A- og B-aksjer for samme utsteder deler porteføljeidentitet, blant annet `INVE-A.ST` og `INVE-B.ST`.

## Replayresultat

Med identiske 22:05-data og uendrede produksjonsgrenser:

- 60 av 60 kandidater får gyldig kurs.
- `PRICE_INVALID` reduseres fra 60 til 0.
- SSAB-A.ST går fra blokkert til `BUY` og består endelig kjøpsautorisasjon.
- Manglende kurs stopper fortsatt fail-closed.
- INVE-B.ST gjenkjennes som samme utsteder som eksisterende INVE-A.ST.

## Uendret

- Produksjonsterskel 73,0 og maksimal risiko 65,0.
- Scheduler 08:00 og 22:00 Europe/Oslo.
- Fail-closed produksjonshandel, porteføljepersistens, Paper Trading, Pushover-regler, navigasjon og øvrige beskyttede funksjoner.

Pakken er ikke live produksjonsverifisert før Render-kontrollene i akseptansedokumentet er bestått.
