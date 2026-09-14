# Deploy RC16.31ck

1. Pakk ut Render-deltaen over eksisterende RC16.31cj-programfiler.
2. Sett `EXPECTED_APP_VERSION=v19.22.0-rc16.31ck` for både web og scheduler.
3. Legg `DATAFORSEO_LOGIN` og `DATAFORSEO_PASSWORD` inn som hemmelige miljøvariabler for både webtjenesten og scheduler-tjenesten. Bruk API-passordet fra DataForSEO, ikke kontopassordet.
4. Deploy begge tjenestene og bekreft at de viser samme versjon.
5. Åpne **Jeep Commander 2.2** og trykk **Test DataForSEO uten varsler**. Ikke aktiver automatisk API-søk før både OLX og Webmotors viser individuelle treff.
6. Når testen er grønn, velg 60 minutter, behold ønsket månedsgrense og aktiver **Bruk DataForSEO for OLX og Webmotors**. Lagre søkevalgene.
7. Første automatiske API-kjøring skal vise stille baseline og null sendte varsler.

Hvis testen feiler, behold DataForSEO avslått. Kontroller API Access, saldo, feilmeldingen per kilde og at hemmelighetene finnes på webtjenesten. Hemmeligheter skal aldri limes inn i chat eller logg.
