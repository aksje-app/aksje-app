# Valideringsrapport - RC16.31k

## Problem

RC16.31j skannet 413 aksjer, men fordelte bare ti utvidede analyser som 4 Norge, 3 Sverige og 3 USA. Kandidater utenfor disse plassene fikk aldri sammenlignbar sluttscore.

## Reparasjon

- Full lokal grunnscore beregnes for alle kandidater som faktisk er hentet.
- Global avkorting skjer etter lik scoring.
- Global kortliste er minst 60 kandidater, avgrenset av tilgjengelig univers.
- Evidensbudsjett og produksjonsporter er ikke utvidet eller svekket.
- Produksjonsterskel 73,0 er uendret; 65/68/70/73 er diagnostiske skygg terskler.

## Testbevis

| Kontroll | Resultat |
| --- | --- |
| Kompilering av kildetre | Bestått |
| Nye kandidatgjenfinningstester | 3/3 bestått |
| Eksisterende målrettede beslutningstester | 5/5 bestått |
| Syntetisk fullunivers | 413/413 fullscoret |
| Forkastet før fullscore | 0/413 |
| Produksjonsterskel endret | Nei |

Den komplette historiske testsamlingen inneholder versjonslåste tester for eldre RC-utgaver og enkelte tester som krever `pytest`, som ikke var tilgjengelig i det isolerte miljøet. Relevante nye og kompatible beslutningstester ble kjørt direkte. Dette er oppført som en begrensning, ikke skjult som full grønn teststatus.

## Terskelbeslutning

Ingen ny produksjonsterskel er valgt. Kildepakken inneholder ikke modne historiske kandidatutfall som forsvarlig kan skille mellom 65, 68, 70 og 73. RC16.31k gjør datainnsamlingen sammenlignbar slik at terskelen senere kan velges etter treffrate, avkastning og risiko.

## Liveakseptanse

Render-verifikasjon av UI, PDF, JSON, logger, scheduler og Pushover gjenstår og er obligatorisk før produksjonsklar erklæring.
