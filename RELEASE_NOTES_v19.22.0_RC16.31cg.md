# v19.22.0 RC16.31cg – Whole-Chain Alert Integrity

Denne versjonen lukker varslings- og rapporthull som ble synlige ved replay av faktiske Fresh Trend-forløp.
Render leveres som ren distribusjon med bare de 14 endrede programfilene; `.env`, tester, dokumentasjon og runtime-data er ikke med.

## Endret

- Fresh Trend skiller nå tydelig mellom oppsettstatus og samlet retning nå.
- ROGS-/WWI-/DNO-forløp er dekket av produksjonsnære regresjonstester.
- Signalalder og breakout-hold kan ikke gå baklengs for samme signal-ID.
- RS kan ikke fremstilles som full markedssammenligning når bare den avgrensede 15-minutterskøen er målt.
- Pushover viser datadekning, ikke misvisende «sikkerhet».
- Kursutvikling vises i kroner og prosent for 15 minutter, 1, 3 og 5 dager når data finnes.
- Volum viser både faktisk volum, omsetning, forhold mot 20-dagerssnitt og om dagens bar er fullført/tidsjustert.
- Alle Pushover-meldinger går gjennom én felles lengde-, linje- og duplikatkontroll.
- Parallelle monitorsykluser blokkeres med lås, slik at samme snapshot ikke kan gi doble varsler.
- Børsdager beregnes med markedets kalender når den er tilgjengelig.
- Rapportgrafene har synlig kursskala, større høyde og mindre bredde. Fresh Trend og tidlige styrkesignaler får samme grafiske kontroll.
- Rapportnedlastinger er samlet under Utkast/pågående kjøring. De tre faste filene viser rapportens dato/tid og peker på siste versjon.
- Komplett rapportpakke inneholder standard-PDF, teknisk PDF, JSON, tekst og diagnose når diagnose finnes.
- Valutakurser vises med fire desimaler.
- Delvis salg kan ikke lenger feile på manglende scorevariabler.
- Automatisk sletting er nå eksplisitt opt-in når miljøvariabelen mangler.

## Uendret sikkerhetsgrense

- Ingen ekte handel aktiveres av denne versjonen.
- En stagnert posisjon foreslås ikke byttet uten en navngitt, kontrollert og bedre kandidat.
- 294/294-grovscan beholdes; den avgrensede Fresh Trend-oppfølgingen erstatter ikke fullscannet.
