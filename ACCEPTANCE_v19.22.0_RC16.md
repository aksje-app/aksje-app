# Akseptanse – v19.22.0 RC16

RC16 aksepteres lokalt når:

1. Hele testlisten består i isolerte batcher.
2. DANSKE-lignende kandidat med score over lagret terskel og alle porter bestått får BUY i porteføljelaget.
3. Kandidat med manglende evidens, lav score/dataverdi, høy risiko eller teknisk vent får ikke BUY og får entydig blocker-kode.
4. Kandidat som stoppes av posisjonsgrense, kontantkrav eller annen porteføljeregel får denne konkrete regelen som første blocker.
5. Komplett replay-ZIP inneholder rapporter, runtimeutdrag, replayresultater, manifest og gyldige SHA-256.
6. Eksporten er skrivebeskyttet og kjører uten nettverk, Pushover eller handler.
7. Enkelt­rapport-ZIP inneholder PDF, TXT, JSON, input-snapshot, beslutningsspor, kildegrunnlag og replayresultat.
8. Eksisterende læringsnotional overskrives ikke automatisk; anbefalt profil på 15 000 aktiveres eksplisitt og gjelder bare LEARNING_ONLY.
9. Streamlit-fragmentene er modulnivå, slutt-CSS er siste injeksjon i appen, og UI-status kan leses uten fullside-overlay.
10. PDF/TXT skiller analytisk anbefaling, gjennomførbar handel og produksjonsgodkjenning, og kvalitetsmålene har entydige navn.
11. Kravfilen beholder Streamlit 1.57.0 og Starlette 1.3.1.
12. Beskyttede score-, scheduler-, Paper Trading-, login- og produksjonshandelskontrakter er verifisert.

Produksjonsgodkjenning krever deretter live Render-test av fremdrift, meny, rapportpakke, komplett eksport, scheduler, PDF-lenke og Pushover.
