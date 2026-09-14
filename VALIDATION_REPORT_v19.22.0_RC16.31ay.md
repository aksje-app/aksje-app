# Valideringsrapport – v19.22.0 RC16.31ay

## Resultat

- Komplett regresjon i kildekatalog: 1105 bestått, 0 feilet, 4 deltester bestått.
- Komplett regresjon fra nyutpakket FULL: 1105 bestått, 0 feilet, 4 deltester bestått.
- Målrettet handelssikkerhet og kapitalrotasjon: bestått.
- AX-til-AY DELTA-overlegg: 7 relevante eldre tester bestått og FRO.OL-scenariet eksplisitt blokkert.
- Python-kompilering: bestått for alle endrede runtimefiler.
- Fullsystemaudit: PASS, 0 feil, 0 varsler og 0 mutable runtimefiler.
- Navigasjons-/rerunaudit: PASS for 330 Python-filer.
- FULL-distribusjonsvalidering: PASS, 586 filer.
- DELTA-distribusjonsvalidering: PASS, 8 filer; 5 runtimefiler kopieres.

## Reprodusert og lukket avvik

FRO.OL ble i RC16.31ax solgt 2. september 2026 kl. 09:02 til 411,50 etter ordinært SELL-signal og kjøpt automatisk tilbake kl. 11:12 til 416,20. Årsaken var at gjenkjøpsvernet bare omfattet stop-loss, mens beskyttelsen mot motstridende handlinger var avgrenset til samme prosess og kjørings-ID.

AY blokkerer samme forløp med fem dagers karantene etter ordinært salg. Stop-loss og trailing-stop gir ti dagers karantene. Automatisk FORCE_ALLOW kan ikke omgå sperren.

## Ytterligere vern

- Automatisk BUY krever gyldig `market_data_at` som er høyst 120 minutter gammelt.
- Automatisk gjentatt kjøp eller tilleggskjøp i samme ticker blokkeres i 24 timer.
- Gjenkjøp mer enn 0,5 % dyrere enn et nylig salg blokkeres i den utvidede kontrollperioden uten dokumentert regimeskifte.
- Kjørings-, scanner-, beslutnings- og datatidspunkt følger handelsobjektet for revisjon.
- Kontant-/rotasjonsrapporten markerer svak eller sidelengs kapital etter 40 dager og opptil 1 % avkastning når scoren samtidig er svekket.
- En god erstatning er ikke lenger nødvendig for å foreslå salg til kontanter.
- Lønnsomme posisjoner tvangsselges ikke av den nye kontantregelen.

## Aktivering

Kapitalrotasjonen er beslutningsstøtte/shadow i denne versjonen. Eksisterende portefølje massejusteres ikke ved deploy. Automatisk gjennomføring skal først vurderes etter én komplett live shadow-dag og uttrykkelig godkjenning.

## Gjenstående liveakseptanse

Lokal pakke er en produksjonskandidat, ikke endelig produksjonsgodkjent. Godkjenning krever AY og identisk commit på Render web/scheduler, en reell 08:00/14:00/22:00-sekvens, ferske automatiske handelsdata, synlig karantene, korrekte Pushover-varsler og fravær av doble eller motstridende handler.

## Pakker

- FULL SHA-256: oppdateres av endelig bygg.
- DELTA SHA-256: oppdateres av endelig bygg.
