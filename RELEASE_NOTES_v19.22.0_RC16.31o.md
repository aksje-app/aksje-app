# RC16.31o – Portfolio Exit and Compact Reporting

## Endret

- Én ren og replaybar exitkontrakt brukes som autoritativ standard for Autonomi og Paper Trading.
- Stop-loss 5 %, trailing stop 7 %, delvis gevinstsikring ved +14 %, score-exit under 55 og RSI 75/fall vises eksplisitt.
- Første gevinstmål realiserer 25 %; restposisjonen beholdes og beskyttes av trailing stop.
- Kapitalstagnasjon gir vurdering. Utskifting krever navngitt, evidensklar kandidat og minst seks scorepoeng fordel.
- Hovedrapporten bygges uten det detaljerte tekniske vedlegget. Full teknisk PDF lagres separat.
- Aktiv exitprofil, porteføljesummer og kapitalstatus vises i hovedrapporten.
- Rapportarkivet tilbyr separat nedlasting av teknisk vedlegg når filen finnes.

## Uendret

- Produksjonsterskel for kjøp er 73.
- Tilleggskjøp er deaktivert.
- Porteføljen er teoretisk og bruker simulert kontoenhet.
- Produksjonsparametere endres ikke automatisk av læring.

## Sikkerhet

- Hard stop-loss, trailing stop og score-exit selger hele posisjonen.
- Delvis salg må etterlate og bokføre restposisjonen; integritetsporten kontrollerer dette.
- Manglende eller ugyldig pris gir HOLD, aldri et konstruert salg.
