# Akseptanse RC16.31ae

- [x] Alle direkte produksjonsavhengigheter har eksakte versjoner.
- [x] Hele installerte produksjonsgrafen er låst og maskinverifisert.
- [x] Alle tre Render-tjenester bruker identisk cache-fri byggekommando.
- [x] Alle tre Render-tjenester bruker Python 3.12.13 og `autoDeployTrigger: commit`.
- [x] FULL og DELTA krever låsefil og låseverifikator.
- [x] Ingen analysefunksjon, datakilde, datainnhenting, score-, risiko-, portefølje- eller handelsregel er endret.
- [x] Komplett lokal testsuite og audits er bestått: 981 bestått, 0 feilet, 66 dokumenterte historiske strict-xfail og 4 beståtte subtester.
- [x] FULL og DELTA er validert, og FULL er retestet fra ren utpakking med samme resultat: 981 bestått, 0 feilet, 66 strict-xfail og 4 subtester.
- [ ] Live Render-bygg er bestått på samme commit for alle tre tjenester.
- [ ] Live utkast, scanner og fast rapport er bestått uten OOM, datetime-feil eller versjonsavvik.
