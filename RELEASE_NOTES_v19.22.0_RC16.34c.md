# v19.22.0-rc16.34c – hard posisjonsgrense og forståelige varsler

## Sikkerhetsretting
- Super Portfolio sin `max_position_pct=15` håndheves nå som en hard grense.
- Målvekter normaliseres ikke lenger tilbake over 15 % når få kandidater består kjøpsportene.
- Ubrukt kapital blir stående som kontanter.
- Eksisterende posisjoner over 15 % reduseres automatisk til 15 % ved neste Super Portfolio-evaluering, også uten ordinær ukentlig rebalansering.
- Reduksjonen logges med `reason_code=HARD_POSITION_CAP`.

## Varsler
- Daglig Paper/læring viser RESULTAT, RISIKO, LÆRING, TESTER, NESTE STEG og HANDLING.
- Misvisende milepælformat som 216/15 erstattes med hvor mye som faktisk gjenstår, eller at grunnkravene allerede er oppfylt.
- Porteføljekontroll forklarer hva som skjedde, hvorfor kontanter beholdes og om brukerhandling kreves.
- Stop-varsler forklarer status i vanlig språk og flytter tekniske detaljer ned i prioritet.
