# Deploy RC16.31cp

1. Last opp delta-ZIP-en til samme programrot som dagens Render-versjon, eller bruk full-ZIP-en ved komplett erstatning.
2. Deploy både webtjenesten og scheduler fra samme kode/commit.
3. Kontroller at begge viser `v19.22.0-rc16.31cp`.
4. Åpne `Marked og signaler → Jeep Commander 2.2`.
5. Velg Hele Brasil, 2025 og 2026, maks 35 000 km og lagre.
6. Kjør `Test DataForSEO uten varsler`.
7. Aktiver automatisk DataForSEO først når både OLX og Webmotors er grønne.
8. Kjør `Søk nå` og kontroller kildestatus, antall sider og individuelle annonser.

Webmotors kan fortsatt blokkere direkte servertrafikk. En rød direktekilde er derfor ikke skjult eller tolket som null annonser; DataForSEO-testen må fremdeles finne minst én individuell Webmotors-annonse før automatisk API-bruk kan aktiveres.
