# Akseptanse RC16.31p

RC16.31p kan bare godkjennes for deploy når:

1. Kildegrunnlaget er RC16.31o FULL med SHA-256 `bd295703cc24778fee74b378dd8a298d33835ab03720de19e0e9a27feed6c583`.
2. Alle Python-filer kompilerer.
3. Kandidatdatakontrakten skiller kritiske, viktige og valgfrie mangler.
4. Sterke delvis belyste kandidater går til synlig rescue-kø; manglende valgfrie data blir aldri nullscore.
5. Global kortliste er deterministisk ved stokket input og har markedsminimum uten hardt markedsmaksimum.
6. Shortvolum/momentum kan aldri bli rapportert eller scoret som shortinteresse.
7. Shortdata rangeres bare som verifisert når kilde, dato, status og rapportert verdi finnes.
8. Kandidater, læringsutfall og porteføljeposisjoner får shortstatus; mangler vises `UKJENT`.
9. Porteføljerapporten viser shortdekning, kapitalvektet shortandel og høy-short-eksponering uten å telle ukjent kapital som null.
10. Læringsrapporten inneholder reproduserbar kurve, drawdown og shortutfallsanalyse, men kan ikke endre produksjon.
11. Hovedrapporten for golden fixture er maksimalt åtte sider, avstemt og uten uleselige tabeller.
12. Replay-/service-ZIP inneholder egne kandidatdata- og shortfiler og består ZIP-integritetskontroll.
13. Produksjonsterskel 73, scheduler 08:00/22:00, exitprofil og fail-closed handel er uendret.
14. FULL/DELTA, deploynotat, validering, endringsoversikt og SHA-256 leveres.
15. Live Render-verifikasjon av UI, planlagt kjøring, PDF, JSON, logger og Pushover gjenstår etter deploy og må bestå før betegnelsen produksjonsbekreftet brukes.
16. Hele aktive testsamlingen skal ha 0 feil. Historiske kontrakter skal være navngitt i manifest og kjøres som `strict xfail`; ingen vilkårlig skip/ignore er tillatt.
