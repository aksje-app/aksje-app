# RC16.31m - Capital Allocation Integrity

## Resultat

Denne versjonen bygger videre på RC16.31l uten å endre produksjonsterskel 73, risiko-, posisjons-, reserve- eller exitgrenser.

## Rettet

- SEC ticker-CIK-registeret hentes én gang og caches i 24 timer i stedet for per ticker.
- Positive rangeringsbidrag fra uverifiserte eller feilende evidensområder fjernes før beslutningsscore.
- Evidensporten er strategiavhengig: obligatorisk evidens forblir fail-closed; irrelevant innsiderevidens er nøytral.
- Eksisterende posisjoner får `EXISTING_POSITION_ADDITIONS_DISABLED` og tydelig HOLD-forklaring.
- Replay- og rapporteksport bruker porteføljebeslutningen som autoritativ sluttbeslutning.
- Teknisk HOLD/WAIT merkes `NEUTRAL_NON_BLOCKING` når det ikke er en inngangsblokkering; 100 prosent ensartet HOLD/WAIT gir systemvarsel.
- Global Top 60 garanterer minst ti kandidater per valgt kjernemarked når markedets tilgjengelige univers tillater det, samt minst én kandidat fra hver tilgjengelig sektor.

## Ny rapportinformasjon

- Åpne posisjoner og kapasitetsbruk.
- `ALLEREDE I PORTEFØLJEN` for hver eid aksje.
- Kjøpsdato/eiertid, antall, inngangskurs, markedskurs, urealisert resultat og scoreutvikling.
- Kapital­effektivitetsvarsel og kontrollert utskiftingsvurdering.
- Samlet rangering av eide og ikke-eide kandidater.
- Observasjonskø for score 68-73, eksplisitt merket som ikke kjøpsanbefaling.
- Automatisk systemvakt for felles evidensfeil og uniforme tekniske signaler.

## Replay-resultat MI-20260815-080526

- SSAB-A.ST består fortsatt den reparerte kjøpskjeden og vises etter kjøpet som eksisterende posisjon.
- HWM: rå justert score 75,83; 3,45 uverifiserte poeng fjernes; effektiv score 72,38.
- EXPD: rå 73,26; effektiv 69,81.
- XOM: rå 73,15; effektiv 69,70.
- Citigroup: effektiv score 73,99, men korrekt blokkert av finanssektorgrensen.
- Ingen kandidat får kjøpsautorisasjon på grunnlag av positivt bidrag fra en kildefeil.

## Avgrensninger

- Dynamisk produksjonsterskel er ikke aktivert; 65/68/70/73 forblir skyggemålinger.
- Sidelengsdeteksjon er et varsel, ikke automatisk salg.
- Indeksrelativ avkastning og faktisk kurskorrelasjon krever komplette benchmark-/historikkserier; eksisterende proxy beholdes og merkes.
- Live Render-verifikasjon kreves før produksjonsklar status.

