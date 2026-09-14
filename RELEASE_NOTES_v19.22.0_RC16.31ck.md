# RC16.31ck – kontrollert DataForSEO-bro for bilsøket

Jeep Commander 2.2-modulen kan nå bruke Google Organic Live via DataForSEO som en separat søkeindeks for individuelle OLX- og Webmotors-annonser. Direkte 403-feil skjules ikke, og søkeindeksen fremstilles ikke som komplett lagerdekning.

Integrasjonen er sperret inntil en stille test har funnet minst én individuell annonselenke fra begge markedsplassene. Testen sender aldri Pushover. Første automatiske API-kjøring lager også en stille baseline, slik at aktivering ikke gir varselflom.

API-bruk krever bare hemmelighetene `DATAFORSEO_LOGIN` og `DATAFORSEO_PASSWORD`. Hemmelighetene logges eller lagres ikke i modulens tilstand. Intervallet kan velges til 60 eller 30 minutter; standard er 60. En månedlig kostnadssperre og en separat testgrense stopper nye kall før grensen passeres.

Indeksresultater kan ikke alene utløse «annonsen borte/solgt». Manglende pris, kilometer, modellår eller sted vises i avvisningsoversikten og blir ikke gjort om til et gyldig biltreff.

## Produksjonsbevis som gjenstår

Lokale tester bruker realistiske, konstruerte API-svar. Etter deploy må knappen **Test DataForSEO uten varsler** kjøres med de virkelige Render-hemmelighetene. Automatisk API-søk skal først aktiveres når modulen viser godkjent test for både OLX og Webmotors.
