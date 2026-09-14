# v19.22.0 RC16.32f — Super Portfolio Broad Discovery

## Formål
Fjerne RC16.32e-begrensningen der Super Portfolio bare enrich-et et lite kandidatsett per marked før rangering. Målet er at alle aksjer i det tilgjengelige investerbare universet skal få en reell første-pass vurdering før shortlist.

## Ny seleksjonsflyt
1. **FULL AVAILABLE UNIVERSE** — hele tilgjengelige universet hentes per marked, opptil 500 symboler per marked i dagens underliggende markedsinfrastruktur.
2. **COARSE SHORTLIST** — hele universet får en billig, batch-basert grovscore basert på pris/momentum/volatilitet og eksisterende Smart-Universe/fundamental hints når de finnes.
3. **DEEP ANALYSIS** — de 50 sterkeste per marked går som standard videre til eksisterende full kandidat-enrichment og score.
4. **GLOBAL TOP** — de 15 beste per marked sendes til samlet rangering. Endelig Top-10 har ingen landkvoter.

Standardverdier:
- universe limit: 500 per marked
- coarse shortlist: 100 per marked
- deep analysis: 50 per marked
- finalists: 15 per marked
- markets: Norge, Sverige, Danmark, Finland, USA

## Viktig presisering
"Hele universet" betyr hele universet som de eksisterende kildene faktisk kan levere i aktuell kjøring, innenfor dagens 500-symbolers markedsgrense. I Norden dekker dette normalt hele de pakkede/lokale listene. For USA er live Smart Universe / S&P 500-kilden fortsatt den tilgjengelige basisen; RC16.32f påstår ikke å dekke alle amerikanske børsnoteringer.

## Ressurskontroll
- Den dyre candidate enrichment kjøres ikke på hele universet.
- Grovpasset bruker batch-prishistorikk og gjenbruker eksisterende hints når mulig.
- Dyp analyse begrenses til shortlisten.
- 12 timers market-feed cache fra RC16.32e beholdes.
- Ingen endring i autoritativ Norway-only produksjonskjede.

## Sikkerhet
Super Portfolio forblir SHADOW og sender ingen reelle handler.
