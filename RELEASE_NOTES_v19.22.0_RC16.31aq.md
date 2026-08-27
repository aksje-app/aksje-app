# v19.22.0 RC16.31aq – aktiv testkontrakt uten xfail-gjeld

RC16.31aq bygger direkte på RC16.31ap. Anbefalingsreglene er uendret, men den
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
- FULL og DELTA bygges fra samme verifiserte kildegrunnlag.
- Ren distribusjon er verifisert fra nyutpakket FULL-pakke.

Moderate recommendations require valid market data, mission eligibility,
completed evidence control, risk at or below 65, score no more than six points
below the strict threshold, no critical negative source signal, no source
conflict, no technical wait state and no existing position.
