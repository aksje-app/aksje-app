# RC16.31br – Complete Norway Exchange Universe

Bygger på RC16.31bq.

## Hovedendring
Norge-universet er ikke lenger begrenset til den pakkede kontrollisten på 82 symboler. Programmet har nå én sentral, dynamisk Norge-master basert på Euronexts offisielle aksjeliste for:

- Oslo Børs (`XOSL`)
- Euronext Growth Oslo (`MERK`)
- Euronext Expand Oslo (`XOAS`)

Masteren lagrer ticker, Euronext-symbol, ISIN, selskapsnavn, valuta, børs/markedssegment, MIC, noteringsstatus, første observasjon og siste verifisering.

## Dekning og robusthet
- Offisiell Euronext-master oppdateres automatisk og lagres som durable last-known-good.
- En midlertidig nettverksfeil kan ikke stille og rolig redusere et tidligere verifisert univers.
- Dersom ingen verifisert Euronext-master finnes, kan den gamle pakkede Norge-listen brukes som nød-fallback, men status blir eksplisitt `FALLBACK_UNVERIFIED` og rapporten får dekningsfeil. Fallback kan aldri presenteres som komplett Oslo-dekning.
- Universrapporten viser total, skannet og manglende per børs/markedssegment.

## Fresh Trend før analyseutvalg
Alle aksjer i Norge-masteren får rask teknisk/Fresh Trend-screening før utvalget til dyrere utvidet analyse. Dermed kan en liten eller ny Growth/Expand-aksje med fersk akselerasjon reservere en plass i den dypere analysen i stedet for å bli filtrert bort før trendmotoren ser den.

Fresh Trend-poolen lagres kompakt for å beskytte minneforbedringen fra RC16.31bq.

## Paper Trade
Paper Trade bruker samme sentrale Norge-master. For å unngå at én 15-minutters cron kjører rundt 300 tunge analyser, beholdes hard per-cycle-grense. Norge-universet roteres deterministisk og cursor lagres først etter vellykket sluttbehandling. Åpne posisjoner prioriteres. Over flere sykluser dekkes hele den offisielle listen.

Paper-kandidater bærer samme børsidentitet: exchange name, market segment, MIC, Euronext-symbol og ISIN.

## Rapporter og UI
- Børs/markedssegment vises i universdekningen.
- Fresh Trend-tabeller viser børs.
- Top 10 og sentrale kandidat-/anbefalingstabeller viser børs der instrumentmetadata finnes.
- Hver aksje kan spores til Oslo Børs, Euronext Growth Oslo eller Euronext Expand Oslo.

## Ikke endret
Ingen kjøpsgrense, risikogrense, porteføljeregel, likviditetsterskel, handelsmyndighet eller automatisk transaksjonsregel er endret.
