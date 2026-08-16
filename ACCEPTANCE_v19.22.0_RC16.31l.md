# Acceptance - v19.22.0-rc16.31l

## Lokal akseptanse

- Python-kompilering av hele kildetreet: bestått.
- Ni målrettede beslutningskjede-tester: bestått.
- 22:05 full replay, 60 kandidater: ett ordinært BUY, SSAB-A.ST.
- Kurskonsistens: 60/60 gyldige, 0 `PRICE_INVALID`.
- Negativ kurstest: manglende kurs stopper med `PRICE_INVALID`.
- Sluttautorisasjon: SSAB-A.ST består portefølje-, utfalls- og produksjonsautorisasjon.
- Teknisk HOLD: 0 positive bidrag.
- Ukjent sekundær insidertransaksjon: klassifiseres `OTHER`, ikke BUY.
- A/B-aksjeklasse: én utstederidentitet og ingen omgåelse av tilleggskjøpsregelen.
- Global evidensgaranti: legacy 10 oppgraderes effektivt til Top 20.
- Produksjonsterskel: fortsatt 73,0; skyggemodus endrer ikke produksjon.

## Testmiljøbegrensning

Den komplette historiske pytest-suiten kan ikke kjøres i leveransemiljøet fordi tredjepakkene `pytest` og deler av runtime-avhengighetene ikke er installert og ingen lokal hjulpakke finnes. Dette er ikke skjult som bestått. Målrettede tester er derfor skrevet med standardbibliotekets `unittest`, og distribusjons-/kompileringskontroll kjøres separat.

## Obligatorisk live verifikasjon

- Ren Render-deploy uten gammel insidercacheeffekt.
- UI, PDF, JSON og logger viser `v19.22.0-rc16.31l`.
- Scheduler kjører 08:00 og 22:00 Europe/Oslo.
- Pushover skiller analytisk signal, evidensklar kandidat og kjøpsgodkjent handel.
- USA-kandidater viser ny SEC-kontroll og ikke gammel cache.
- Faktisk evidenssøkt antall og kildebruk overvåkes; Top 20 skal være garantert.
- Ingen ekte ordre eller produksjonsstatus uten eksplisitt godkjent driftsmodus.

Status før disse punktene: lokal release candidate, ikke live produksjonsverifisert.
