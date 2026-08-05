# Deploy v19.22.0 Investor Edition RC3

1. Ta sikkerhetskopi av nåværende deploy og varig runtime-data.
2. Deploy RC3 FULL eller bruk RC3 DELTA mot nøyaktig v19.22.0 RC2.
3. Ikke overskriv `.app_runtime`, hemmeligheter, database eller varige rapportdata.
4. Bekreft at appen viser `v19.22.0-rc3`.
5. Åpne Rapporter-siden på desktop og mobil.
6. Bekreft rekkefølgen Status, Handlinger, Siste rapporter, Historikk og Planlegging/avansert.
7. Bekreft at avansert seksjon er lukket og at avkrysningsbokser ikke vises på hovedflaten.
8. Bekreft kompakte knapper for Nytt utkast, morgenanalyse, kveldsanalyse og nattanalyse.
9. Kontroller at manglende planlagt rapport kan kjøres fra statusområdet.
10. Kjør en ny rapport og sammenlign UI, JSON og PDF.
11. Kontroller scheduler og Pushover ved neste 08:00- eller 22:00-kjøring Europe/Oslo.
12. Rull tilbake dersom navigasjon, scheduler, rapportintegritet eller jobbprofil-lagring avviker.

## Beskyttede områder
RC3 endrer ikke innlogging, Husk meg, scheduleroppstart, bakgrunnstråder, final_score, kandidatvalg, Paper Trading eller handelsregler.
