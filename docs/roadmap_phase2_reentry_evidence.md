# Fase 2 – gjenkjøp etter tap

Kilde: lesekontroll av `autonomous_portfolio/trades.json` på Render. Observasjoner er registrerte handler, ikke konklusjoner om gjeldende kode på historisk handelstidspunkt.

- VTURA.OL: kjøpt 14. september 2026, solgt med stop-loss 22. september (−1 484,74), kjøpt på nytt 23. september kl. 06:08 UTC og solgt samme dag kl. 12:07 UTC (−1 597,80). Registrerte tap til sammen −3 082,54.
- AKER.OL: kjøpt 15. september kl. 06:22 UTC, solgt med stop-loss kl. 07:21 UTC (−783,73).
- CMBTO.OL: tapsutgang 25. september, gjenkjøpt 12. oktober, ny stop-loss 14. oktober (−304,82).

`autonomous_portfolio.py` inneholder per revisjonsdato `_reentry_cooldown()`, med stop-loss-sperre på minst 5 børsdager, 15 ved gjentatte stop-loss og krav om `fresh_post_stop_confirmation` etter karantene. Både ordinære kjøp og læringskjøp har egne kall til sperren. Undersøk historisk deploy-versjon før noen hevder at nåværende sperre feilet i september.

Neste kontroll: historisk kodeversjon og kjøpslogg, prisens tidsstempel, score, og om lignende tap skjer med gjeldende sperre. Ikke endre stop-loss eller produksjonsparametere ut fra disse tre historiske eksemplene alene.
