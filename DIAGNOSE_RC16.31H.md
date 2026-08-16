# Diagnose RC16.31h – Autonomi-presentasjon, parametre og valutadesimaler

## Observerte feil

1. `Total avkastning` i kroner beregnes mot `params.initial_cash`, mens prosentavkastningen beregnes mot `portfolio.initial_cash`. Når en lagret parameter er endret fra 500 000 til 2 000 000 uten porteføljereset, viser samme side omtrent +1 % og -1,5 millioner kroner samtidig.
2. Feltet `Startkapital` ser ut som en løpende strategiinnstilling, men får først faktisk virkning når porteføljen nullstilles. Dette forklares ikke i grensesnittet.
3. Aktiveringsanalysen viser resultatkolonner uten en kort forklaring av hensikt, lesemåte og konklusjon. `NO_ORDER_INTENT` blir teknisk og skjuler hvilket trinn som stoppet kandidatene.
4. Porteføljegrafen bruker absolutt porteføljeverdi og kategoriske datoetiketter. Små endringer rundt 500 000 blir derfor visuelt en nesten flat linje.
5. Flere Autonomi-tabeller viser uensartet antall desimaler. Valutavarsler viser fire eller to desimaler, mens ønsket presisjon er tre.
6. Den lagrede produksjonsprofilen i skjermbildet er mer aggressiv enn den anbefalte profilen på datakvalitet, reserve, stop-loss og antall åpne posisjoner. Lagrede brukerinnstillinger skal ikke overskrives stille av en programoppdatering.

## Korrigering

- Bruk alltid porteføljens uforanderlige `initial_cash` som avkastningsgrunnlag.
- Merk startkapital som reset-verdi og vis både faktisk avkastningsgrunnlag og valgt reset-verdi.
- Tilby en eksplisitt, godkjenningspliktig anbefalt produksjonsprofil. Ingen automatisk strategiendring.
- Vis forklaring og nåkonklusjon rundt aktiveringsfunnel, blokkeringer, simulering og strategikontoer.
- Vis normalisert prosentutvikling og kapitalfordeling med tidsakse.
- Formater Autonomi-tall med to desimaler og valutavarsler med tre.

## Sikkerhetsgrense

Endringen skal ikke nullstille porteføljen, omskrive handler eller historikk, senke harde kjøpsporter automatisk eller sende reelle ordre. Endring av produksjonsprofil krever teksten `GODKJENN` og lagres i eksisterende auditlogg.
