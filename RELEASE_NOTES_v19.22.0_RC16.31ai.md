# v19.22.0 RC16.31ai – produksjonsstabilisering

Dette er en ren distribusjon bygget direkte på RC16.31ah.

- Short- og innsiderevidens har én kanonisk kontrakt fra kandidat til portefølje og PDF.
- Publisering stoppes dersom koden hevder at en kilde er kontrollert samtidig som resultatet vises som «ikke søkt» eller «ukjent».
- Åpne posisjoner utenfor den avgrensede kandidatlisten får en egen, avgrenset evidenskontroll.
- Paper-skanning holder ikke lenger rapportplanleggerlåsen; faste rapporter prioriteres ved 08:00, 14:00 og 22:00.
- Mobil rapportvisning har fast retur til programmet og separat PDF-knapp.
- Markedsfargene er låst med regressjonstest.
- Rapportmotor og Paper-scanner deler varig tickerkarantene. Etter gjentatte feil prøves ticker igjen etter 24 timer; etter seks feil går den til 30-dagers periodisk kontroll og merkes for gjennomgang, uten automatisk sletting av en eid posisjon.
- Kjente ufarlige Streamlit bare-mode-varsler filtreres i cron, mens reelle varsler beholdes.

Ingen score-, risiko-, portefølje-, handels- eller datakilderegel er redusert.
