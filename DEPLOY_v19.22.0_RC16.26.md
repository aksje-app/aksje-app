# Deploy v19.22.0-rc16.26

1. Ta sikkerhetskopi av gjeldende repository og vedvarende runtime-data.
2. Kopier FULL-pakken, eller bruk DELTA-pakken mot v19.22.0-rc16.25.
3. Commit og push alle kildefiler, inkludert `assets/` når mappen finnes i FULL-pakken.
4. La Render bygge både webtjenesten og `aksje-app-report-scheduler` fra samme commit.
5. Kontroller at versjonen viser `v19.22.0-rc16.26`.
6. Kjør én ordinær Autonomi-syklus med minst én kandidat som har score 63–65, risiko høyst 75 og gyldige markedsdata.
7. Bekreft at handelen vises kun i `autonomy_learning`, med verdi inntil 15 000 og produksjonsblokkere lagret.
8. Bekreft at `autonomy_main` er uendret og at ingen ekte handel er mulig.
9. Kontroller neste syklus for HOLD/SELL, resultatmåling og Pushover for simulerte læringshandler.

Ved avvik: rull tilbake applikasjonscommit. Vedvarende læringsdata skal ikke slettes automatisk.
