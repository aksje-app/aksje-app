# v19.22.0 RC16.31ar – aktiv testkontrakt uten xfail-gjeld

RC16.31ar bygger direkte på RC16.31aq. Anbefalingsreglene er uendret, men den
harde avstemmingen mellom JSON, TXT, hoved-PDF, teknisk PDF og Pushover er
rettet og verifisert mot den faktiske problemkjøringen med 64 kandidater.

Rettet:

- Menneskelig beslutningstekst sammenlignes ikke lenger med intern maskinkode.
- TXT bruker anbefalingsrang 1–N, identisk med kanal-kontrakten.
- Kort hoved-PDF avvises ikke fordi tekniske læringsdetaljer ligger i vedlegget.
- Teknisk/full PDF må fortsatt inneholde eksakte læringshandler og priser.
- Rapport-ZIP inneholder igjen `candidate_scores.json`.
- Portefølje-only-posisjoner registreres ikke som manglende analysescore.
- Den faste 14:00-kjøringen beholdes for mulige nye opplysninger før nordiske
  børser stenger. Den omgår seks-timerscachen og krever et nytt live-forsøk.
- 65 utgåtte release-, rapport- og UI-kontrakter er flyttet ut av aktiv
  akseptansekjøring som historisk evidens; de rapporteres ikke lenger som xfail.
- Seks gjeldende kontrakttester erstatter de gamle versjonsliteralene og
  kontrollerer scheduler, 14:00-ferskhet, handelssperre, norsk rapport og
  avstemming mellom JSON, tekst, hoved-PDF og teknisk PDF.
- Minnemyk kontroll kan ikke lenger låse skanneren ved ticker 1/30. Minst én
  ticker ferdigstilles per cron før et nytt kontrollpunkt kan opprettes.
- Kontrollpunktet lagrer neste indeks etter faktisk fremdrift, slik at senere
  cron fortsetter ved neste ticker uten å redusere skanneuniverset.
- En delvis skanning rapporteres som PARTIAL_CHECKPOINT, ikke COMPLETED.
- Eksakt like Pushover-payloads dedupliseres varig i ti minutter.
- Fondsnavn og andre ugyldige tickerverdier filtreres før markedsoppslag.
- Stengte UI-kandidater prioriteres ikke foran kandidater i åpne markeder.
- Render cron er avstemt med programinnstillingen til hvert 15. minutt.
- FULL og DELTA bygges fra samme verifiserte kildegrunnlag.
- Ren distribusjon er verifisert fra nyutpakket FULL-pakke.

Moderate recommendations require valid market data, mission eligibility,
completed evidence control, risk at or below 65, score no more than six points
below the strict threshold, no critical negative source signal, no source
conflict, no technical wait state and no existing position.
