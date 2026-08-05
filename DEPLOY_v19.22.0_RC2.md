# Deploy v19.22.0 Investor Edition RC2

1. Bruk FULL-pakken som komplett kilde, eller legg DELTA-pakken over v19.22.0 RC1.
2. Commit til korrekt deploy-gren.
3. I Render: velg **Manual Deploy -> Clear build cache & deploy**.
4. Bekreft at appen viser `v19.22.0-rc2`.
5. Test innlogging og utlogging uten å endre autentiseringsoppsettet.
6. Test alle hovedmenyer, spesielt `Oversikt -> Rapporter`, Driftssenter og AI Kontrollsenter.
7. På Rapporter-siden, test `Kjør nytt utkast`, morgenrapport, kveldsrapport og `Åpne siste rapport`.
8. Generer en rapport og sammenlign UI, JSON og PDF for samme Top 3, `final_score` og beslutning.
9. Kontroller Investor Edition, rapport-ID, analyse-ID, genereringstid, rapportskjema og kontrollsum i PDF.
10. Kontroller scheduler og Pushover ved 08:00 og 22:00 Europe/Oslo uten at et manuelt utkast kjøres først.
11. Kontroller at endret minste varsel-score gjelder fra neste nye manuelle og planlagte kjøring.
12. Ikke marker versjonen produksjonsklar før alle livepunkter er dokumentert bestått.
