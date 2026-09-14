# RC16.31bf - Norway Trend Discovery

## Formaal
Denne versjonen snevrer automatisk produksjonsstabilisering til Norge og legger inn et eget trendbevis uten aa endre kjopsgrenser, risikogrenser eller handelsautorisasjon.

## Endringer
- Faste 08:00/14:00/22:00-rapporter bruker midlertidig kun Norge.
- Automatisk Paper-skanner bruker midlertidig kun Norge.
- `PRODUCTION_NORWAY_ONLY=false` aapner eksisterende Norge/Sverige/USA-logikk igjen uten ny kodeendring.
- Manuelle markedsvalg beholdes.
- Markedsberikelsen lagrer faktiske 5/10/20/60-dagers avkastninger, SMA20/SMA50, volum mot 20-dagers snitt, avstand til 20/60-dagers topp og opptil 60 faktiske sluttkurser.
- Kandidater faar et `trend_receipt` med foerste kjente observasjon, rangendring, trendfase og tre viktigste trenddrivere.
- PDF viser mindre trendgraf og trendbevis for rang 1-3.
- UI viser klikkbare trenddetaljer for rang 4-10.
- `trend_discovery` lagrer Top 10, naer-kandidater og dekningsstatus som grunnlag for videre missed-winner-audit.

## Sikkerhet
Trendlaget er beskrivende. `production_scoring_changed=false`. Ingen scoreterskler, portefoljegrenser eller handelsregler er endret.
