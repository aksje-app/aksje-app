# Acceptance - v19.22.0-rc16.31k

## Lokal status

- ZIP-integritet for RC16.31j-kilden: bestått.
- Python-kompilering av hele kildetreet: bestått.
- Kandidatgjenfinningens målrettede tester: bestått.
- Eksisterende beslutningstrakt- og reduksjonstester: 5 av 5 bestått.
- Syntetisk univers: 413 skannet, 413 fullscoret, 0 forkastet i hurtigfilteret: bestått.
- Produksjonsterskel forblir 73,0: bestått.
- Skygg terskler endrer ikke produksjon: bestått.

## Må fortsatt verifiseres live

- Faktisk kandidatrekkefølge for DNB, Storebrand, BlueNord, Aker og øvrige markedsledere.
- Kjøretid, minnebruk, watchdog og kildebudsjett på Render.
- PDF, JSON, logger, scheduler 08:00/22:00 Europe/Oslo og Pushover.
- Modne utfall for tersklene 65, 68, 70 og 73 før eventuell produksjonsendring.

Pakken er lokaltestet, men skal ikke betegnes som produksjonsverifisert før livepunktene er bestått.
