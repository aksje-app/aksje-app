# RC16.31ci – utvidet bil- og forhandlersøk

Jeep Commander 2.2-modulen søker fortsatt hvert 15. minutt via eksisterende Render Cron. Webmotors, OLX og Mobiauto er hovedkildene. Et valgfritt forhandlernettverk supplerer nå med Localiza Seminovos og Seminovos.com.br.

Treff merkes som privatannonse, vanlig forhandler eller autorisert Jeep-forhandler når kilden uttrykkelig dokumenterer dette. Manglende informasjon vises som ukjent og blir ikke gjettet.

Samme bil på flere nettsteder samles konservativt når modellår, kilometer, sted og variant stemmer og prisene er rimelig like. Billigste annonse åpnes først, mens de øvrige kildene og prisene vises. Et nytt nettsted for en kjent bil kan varsles uten at brukeren får en duplikatflom.

Hver kilde har egen helsestatus. Blokkering, HTTP-feil eller et endret sideformat vises som en ufullstendig kontroll, ikke som null biler.

## Deploy

Pakk ut den rene deltaen over eksisterende programfiler og sett `EXPECTED_APP_VERSION` til `v19.22.0-rc16.31ci`. Web og scheduler må bruke samme versjon. Første manuelle søk etter deploy skal kontrollere faktisk kildehelse og lage en stille referanse.

