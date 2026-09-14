# Deploy RC16.31cm

1. Pakk ut den rene RC16.31cm-deltaen over RC16.31cl.
2. Deploy samme kilde/commit til web og scheduler.
3. Du trenger ikke endre `EXPECTED_APP_VERSION`; en gammel verdi ignoreres normalt.
4. Kontroller at `ENFORCE_EXPECTED_APP_VERSION` ikke er `true`, med mindre du bevisst ønsker nød-/deploylås.
5. Behold `REQUIRE_CLUSTER_ALIGNMENT=true` på scheduler. Den kontrollerer fortsatt web-versjon og commit.
6. Behold `DATAFORSEO_LOGIN` og `DATAFORSEO_PASSWORD` som hemmelige variabler.
7. Åpne Jeep Commander 2.2 og trykk «Test DataForSEO uten varsler» én gang.
8. Kontroller at både OLX og Webmotors blir grønne før DataForSEO-bryteren aktiveres.

Testen sender null Pushover. Hvis bare én kilde blir grønn, les feilen i den andre statusboksen; den vellykkede kilden skal ikke lenger bli overskrevet av den mislykkede.
