# v19.22.0-rc16.34e – Autonomy Parameter & Learning UX

## Formål
Gjøre Autonomi-produksjonsparametere synlige og forståelige på mobil, samt gjøre læringsforslag eksplisitt godkjennbare uten automatisk produksjonsendring.

## Endringer
- Produksjonsparametere flyttes høyt opp på Autonom portefølje, rett etter persistent parameterstatus.
- «Parameterlås» omformuleres til tydelig permanent parameterlagring.
- Maks posisjon og øvrige produksjonsgrenser viser hva de påvirker og hva de ikke påvirker.
- Læringsforslag om risikoreduksjon får Godkjenn / Avvis nå / Utsett / Ikke foreslå igjen.
- Godkjent forslag lagres automatisk som produksjonsparameter etter eksplisitt bekreftelse.
- Avviste/utsatte forslag kan først komme tilbake etter ny evidens eller cooldown; permanent blokkering er et eget valg.
- Paper-statistikk og produksjon/læring-statistikk skilles tydelig i rapport og UI.
- Parameterendringer får historikk og manuell rollback.
- Aktiveringsanalysens blokkeringer og scoregrenser stables for bedre mobilvisning.
- Super Portfolio, Paper, autonomy_learning og eksisterende historikk påvirkes ikke av en Autonomi-produksjonsparameter med mindre det uttrykkelig står slik.

## Sikkerhetskontrakt
Ingen læringsmotor kan endre beskyttede produksjonsparametere automatisk. Endring krever eksplisitt brukerbeslutning og bekreftelse.
