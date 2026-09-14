# Deploy RC16.31cl

1. Pakk ut den rene RC16.31cl-deltaen over RC16.31ck.
2. Sett `EXPECTED_APP_VERSION=v19.22.0-rc16.31cl` på både web og scheduler.
3. Behold `DATAFORSEO_LOGIN` og `DATAFORSEO_PASSWORD` som hemmelige variabler på begge tjenestene.
4. Deploy web og scheduler og kontroller at begge viser RC16.31cl.
5. Åpne Jeep Commander 2.2. Kontroller at driftstilstand er Aktiv og nattpause 01–06.
6. Trykk «Test DataForSEO uten varsler». Se fremdriften og kontroller de fire statusboksene etter automatisk oppdatering.
7. Aktiver DataForSEO bare dersom både OLX og Webmotors er grønne.
8. Kontroller System/admin etter en stengt børsperiode: status, neste åpning og spart teller skal vises. Rapporter og valuta skal fortsatt være aktive.

Ved feil: pause bilmodulen, behold historikken og les den permanente røde statusboksen. Ikke fjern kostnadssperren og ikke legg API-hemmeligheter i logg eller chat.
