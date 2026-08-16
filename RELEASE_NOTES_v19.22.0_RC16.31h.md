# RC16.31h

Denne versjonen retter og forklarer Autonomi-visningen uten å blande produksjonskonto, læringskonto og teknisk benchmark.

- Avkastning i kroner beregnes mot aktiv porteføljes faktiske startverdi, ikke verdien i et senere redigert resetfelt.
- Utviklingsgrafen viser normalisert prosentutvikling; kapitalfordeling vises separat som porteføljeverdi, kontanter og investert kapital.
- Aktiveringsanalysen forklarer kandidat-, data-, risiko-, score-, ordreintensjons- og ordresteg, samt reell blokkårsak.
- Den kjente eldre produksjonsprofilen migreres én gang til score 73, datakvalitet 70, risiko 65, maks 3 % per posisjon, maks 20 posisjoner, 10 % reserve, stop-loss 5 %, trailing stop 7 % og gevinstmål 14 %.
- Andre egendefinerte profiler overskrives ikke. Læringskontoens parametere, kapital, posisjoner, handler og historikk endres ikke.
- Startkapital merkes som en verdi som først gjelder ved eksplisitt reset.
- Finansielle presentasjonstall bruker to desimaler. Valutakurser, valutagrenser og valutavarsler bruker tre desimaler.

Ingen virkelig handel aktiveres. Migreringen nullstiller ikke porteføljen.
