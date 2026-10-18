# Shadow samlet markedstemperatur: krav før aktivering

Status: **IKKE VALIDERT**. Denne teksten fastsetter krav, ikke vekter eller handelssignaler.

## Hva måleren skal si
- Tallet 0–100 skal uttrykke en dokumentert, relativ *markedsrisiko*, ikke sannsynlighet for børsfall eller forventet avkastning.
- Farge og forklaring må angi hva som driver utslaget, og oppgi dato og dekningsgrad.
- Udaterte eller manglende kritiske data gir «Ikke beregnet» i stedet for et konstruert estimat.
- Måleren er informativ og får ingen kobling til kjøp/salg.

## Historisk datagrunnlag
- Samle punkt-i-tid data, med publiseringsdato, kilde, måleenhet og revisjonshistorikk.
- S&P500-markedsbredde skal beregnes fra historiske indeksmedlemmer, ikke bare dagens aksjeunivers (unngå survivorship bias).
- Før datakilden brukes i modelltilpasning må den ha dokumentert dekningsgrad, handelsdager og justerte kurser.
- Sammenstill daglige og månedlige/årlige målinger uten fremtidslekkasje; årlige tall gjelder først fra dato for faktisk tilgjengeliggjøring.
- Rapporter hull i hver serie, start- og sluttdato, minste antall observasjoner og faktisk dekningsgrad. Ett datapunkt er ikke historikk.

## Kalibrering
1. Del historikken kronologisk i trening, validering og låst testperiode.
2. Fastsett eksplisitt hvilken risiko som måles (eksempelvis fremtidige fall, volatilitet og stress). Ikke optimaliser før målet er fastsatt.
3. Test robuste normaliseringer og identifiser overlapp (USA-renter; dollar/EURUSD; olje/gass og inflasjon).
4. Velg vekter bare etter forhåndsdefinerte kriterier; dokumenter bidrag fra hvert område.
5. Bruk walk-forward-testing uten å revidere modellvalg ut fra testperioden.
6. Oppgi falske alarmer, tapte hendelser, sensitivitet overfor datamangler og resultater per markedsregime.
7. Vis scenarioer for 2008, 2020 og 2022 bare med ekte, tilgjengelige kilder fra disse periodene. Manglende kilder betyr «ikke testbart».

## Godkjenningskrav
En separat, eksplisitt godkjenningsprosess må dokumentere datasettversjon, metodeversjon, kildegrunnlag, vektvalg, tester og beslutning. Ingen automatisk omsetting av «14 av 14 nå» til «modell validert».
