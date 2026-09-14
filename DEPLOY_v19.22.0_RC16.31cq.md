# Deploy RC16.31cq

1. Last opp delta-ZIP-en til programroten, eller bruk fullpakken ved komplett erstatning.
2. Deploy web og scheduler fra samme kode.
3. Kontroller at begge viser `v19.22.0-rc16.31cq`.
4. Åpne Jeep Commander 2.2. Hovedsøket skal nå ha en egen Webmotors-knapp.
5. Fjern eventuelle søkeresultatsider fra feltet for individuelle annonser og lagre.
6. Trykk `Test DataForSEO uten varsler` én gang.
7. Bekreft at testen viser to utførte API-kall og ikke `kostnadssperre $0.15`.
8. Aktiver DataForSEO først når både OLX og Webmotors er grønne.

Månedsgrensen på USD 12 gjelder fortsatt. Direkte HTTP 403 fra Webmotors/OLX er forventet synlig; den vellykkede DataForSEO-testen må dokumentere minst én individuell annonse fra hver kilde.
