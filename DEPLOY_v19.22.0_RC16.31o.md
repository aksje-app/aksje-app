# Deploy RC16.31o

1. Ta sikkerhetskopi av persistent portefølje, parametere, handler og rapportarkiv.
2. Deploy FULL-pakken uten å nullstille persistent disk eller database.
3. Bekreft at appen viser `v19.22.0-rc16.31o`.
4. Kjør ett utkast før neste planlagte rapport.
5. Kontroller at hoved-PDF er kort og at teknisk vedlegg finnes separat.
6. Kontroller at aktiv profil viser 5 / 7 / 14 / 55 / RSI 75 og 25 % delrealisering.
7. Kjør en ikke-muterende replay av alle exit-scenarier.
8. Bekreft at en posisjon over +14 % gir `SELL_PARTIAL`, ikke totalsalg.
9. Bekreft at stagnasjon uten god erstatning ikke selger.
10. Ved avvik: rull tilbake til RC16.31n og behold persistent data uendret.
