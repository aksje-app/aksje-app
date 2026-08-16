# RC16.31k - Candidate Recall Calibration

Denne utgaven retter kandidatgjenfinningen uten å senke produksjonsterskelen eller svekke handelsportene.

## Endret

- Alle faktisk hentede kandidater får samme lokale tekniske og fundamentale grunnscore før global avkorting.
- Eldre jobbprofiler med `deep_count=10` kan ikke lenger skape en skjult 4/3/3-kvote mellom Norge, Sverige og USA.
- Den globale kortlisten har et avgrenset minimum på 60 kandidater, eller alle kandidater når universet er mindre.
- Skyggemålinger inkluderer 65, 68, 70 og 73. De historiske utfordrerne 72, 74, 76 og 78 beholdes for kompatibilitet.
- Kjøringsobjektet dokumenterer kandidatvalgpolicy, tilgjengelig antall, valgt antall og at produksjonsterskelen ikke er endret.

## Uendret

- Produksjonsterskel: 73,0.
- Maksimal risikoscore: 65,0.
- Evidens-, data-, oppdrags-, portefølje- og handelssperrer.
- Fail-closed produksjonshandel, Paper Trading-persistens, scheduler 08:00/22:00 Europe/Oslo, navigasjon, Pushover-regler og eksisterende porteføljer.

## Kalibreringsregel

Ingen ny produksjonsterskel velges før reelle, modne utfall viser treffrate, avkastning og risiko for hver skygg terskel. RC16.31k forbedrer kandidatfangsten og samler sammenlignbart beslutningsgrunnlag; den foregriper ikke resultatet.
