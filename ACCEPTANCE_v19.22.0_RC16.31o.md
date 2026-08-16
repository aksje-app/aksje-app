# Akseptanse RC16.31o

Utgivelsen kan bare godkjennes når:

1. Alle Python-filer kompilerer.
2. Exit-scenariene STOP_LOSS, TRAILING_STOP, TAKE_PROFIT_PARTIAL, SCORE_EXIT, RSI_EXIT, CAPITAL_STAGNATION og CAPITAL_REPLACEMENT består.
3. Delvis gevinstsikring selger 25 % og etterlater 75 % uten avstemmingsfeil.
4. Rapporten navngir en erstatningskandidat bare når den er evidensklar og minst seks poeng bedre.
5. Replay-hovedrapporten er maksimalt åtte A4-sider.
6. Teknisk vedlegg kan bygges separat og er semantisk gyldig.
7. Hovedrapporten viser aktiv exitprofil og avstemte porteføljetall.
8. Visuell kontroll viser ingen klipping, overlapping eller uleselige tabeller.
9. Distribusjonsarkivene inneholder ingen runtime-data, hemmeligheter eller genererte rapporter.
10. Live-verifikasjon utføres etter deploy før versjonen omtales som produksjonsbekreftet.
