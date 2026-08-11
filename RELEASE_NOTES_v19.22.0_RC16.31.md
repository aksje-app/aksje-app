# v19.22.0-rc16.31 – Report Delivery Closure

## 4/4-produksjonsfunn, jobbidentitet og tidspunkt - 11.08.2026

- Flytter den faste ettermiddagsrapporten fra eldre 16:30 / midlertidig 15:00 til 14:00 Europe/Oslo, slik at rapporten kan vurderes før samme handelsdag er over.
- Gir automatisk rapporttest egen stabil jobb-ID og navn; testen kan ikke lenger bokføres som obligatorisk morgen-, ettermiddags- eller kveldsrapport.
- Deaktiverer kjente eldre faste dublettprofiler når de tre obligatoriske profilene er etablert, uten å endre brukerens egendefinerte profiler.
- Leveringsregnskapet ignorerer testhistorikk selv om eldre data feilaktig brukte en produksjonsjobb-ID.
- Pushover viser planlagt tidspunkt i jobbens lokale tidssone i stedet for rå UTC.
- Terminalvarsel skiller 4/4-resultatet fra antall kjøringsforsøk og retry/feilede forsøk.
- Paper-status bruker nyeste varige scanner-heartbeat og merkes `SCAN FORELDET` når aktiv bryter ikke støttes av fersk scannerstatus.
- Diagnosen er dokumentert i `RC16.31_4AV4_TIDSLINJE_OG_JOBBIDENTITET_DIAGNOSE_2026-08-11.md`.

## Obligatoriske rapporter og lagring - 11.08.2026

- Oppretter og reparerer tre separate faste hverdagsrapporter kl. 08:00, 14:00 og 22:00 Europe/Oslo.
- Gjør kanonisk resultatlagring atomisk i Postgres og fjerner den sårbare separate read-before-write-kontrollen.
- Bruker tre avgrensede forsøk ved midlertidig lagringsfeil, med lokal fil kun som diagnostisk speil.
- En reparerbar resultatindeks kan ikke lenger gjøre et allerede lagret resultat ugyldig.
- Rapportsenteret viser dagens tre leveranser med PDF-, lagrings- og Pushover-status.
- Manglende obligatorisk rapport gir et uavhengig driftsvarsel etter 30 minutter.
- En lagret rapport kan prøve PDF/Pushover på nytt uten ny markedsskanning, Autonomi- eller læringskjøring.
- Rapporttesten venter når en ordinær rapport kreves i samme scheduler-syklus.
- Ingen analyse-, score-, risiko-, portefølje-, handels- eller læringsterskler er endret.

## Faste rapporter og Pushover - 11.08.2026

- Retter at en gyldig, lagret PDF ikke ble varslet når bare den teoretiske beslutningsdelen feilet.
- Ordinære planlagte rapporter leveres i dette tilfellet med tydelig «BEGRENSET RAPPORT – IKKE BESLUTNINGSKLAR» og kan ikke fremstilles som kjøpssignal.
- Automatiske akseptansetester forblir fail-closed og teller ikke en rapport med `THEORETICAL_DECISIONS`-feil som bestått.
- En feilet fast jobb stopper ikke lenger andre forfalte jobber i samme scheduler-syklus.
- Schedulerstatus skiller mellom vellykkede og feilede jobber og beholder feildetaljen per jobb.
- Ingen markedsdata-, score-, risiko-, kjøps-, salgs-, portefølje- eller læringsterskler er endret.

## Report Final - 10.08.2026

- Kandidatavstemmingen inkluderer nå kjøp, automatisk overvåking, manuell vurdering og automatisk avvisning, med hard integritetssperre ved avvik.
- Analytisk kjøpssignal er tydelig skilt fra kjøpsgodkjent og gjennomførbar handel.
- Norsk desimalformat er konsekvent i PDF og tekst, mens datoer, versjoner, ID-er og URL-er bevares.
- Interne historikkoder, engelske seksjonstitler, dupliserte jobbnavn og maskinlinjen `INTEGRITY-CANDIDATES` er fjernet fra investorvisningen.
- Beslutningsdelen hopper over tomme diff- og hendelsesseksjoner. Referanserapporten er redusert fra 7 til 6 sider.
- PDF-semantikk validerer den lesbare kandidatavstemmingen mot kanonisk JSON før rapporten kan publiseres.
- Pushover viser nå programversjon, rapport-ID, lokal rapporttid og datastatus fra samme rapportmodell som PDF/JSON.
- Testvarsler skiller mellom deltest 1/4-4/4 og kjøringsforsøk/retry.
- Testjobben og varslene fjerner gjentatte jobbnavn.
- Læringsrapporten bruker norsk prosentformat og viser rapport-ID og programversjon.
- Rapportsenteret forklarer 0/4 med fase, schedulerstatus og forventet resultattid for en aktiv fullkjede.

## Automatisk rapporttest og leveransekontroll

- Retter at en 30-minutters cron kunne bli vurdert noen sekunder for tidlig og dermed forskyves til 60 minutter.
- Lagrer eksplisitt neste hele/halve time før den tunge rapportkjøringen starter.
- Gir hver automatisk serie stabil testserie-ID og hvert varsel tydelig `AUTOMATISK 1/4`–`4/4`.
- Merker umiddelbar test som `TESTVARSEL · MANUELL TEST`; den teller aldri i automatisk 1/4–4/4.
- Teller bare dokumentert sendt Pushover som vellykket deltest.
- Sender terminalt sammendrag ved 4/4 bestått, tre feil eller utløpt sikkerhetsvindu.
- Viser neste forsøk, antall forsøk, feil og komplett testtidslinje i Rapportsenteret.
- Prøver varig teststatuslagring tre ganger og beholder opprinnelig rapportfeil separat fra lagringsfeil.
- Legger til rask systemkontroll for database, rapportlås, PDF-motor, offentlig lenke og Pushover uten markedsskann eller portefølje-/læringshandling.
- Diagnosepakken inkluderer testtidslinje, siste systemkontroll og avgrenset Pushover-audit.
- Ingen kjøps-, salgs-, score-, risiko-, portefølje- eller læringsterskler er endret.

## Runtime Safety Gate

- Normaliserer nullverdier i vedvarende Autonomi-porteføljestatus før numeriske sammenligninger.
- Retter livekrasjet der `MARKET_SCAN` sendte manglende fremdriftstellere og `max(1, None)` ga TypeError.
- Normaliserer alle callback-tellere og krever eksplisitte tellere fra Autonomi-stage-hendelser.
- Bevarer konkret Autonomi-stage, feiltype og traceback ved runtimefeil.
- Bevarer `run_id`, kjedestatus og Full Autonomy-receipt i feildiagnostikk.
- Blokkerer ordinær beslutningsklar Pushover når Autonomi-forutsetningene ikke består; en validert fast rapport kan bare leveres med eksplisitt begrensningsmerking når eneste feil er `THEORETICAL_DECISIONS`.
- Marker ikke `COMPLETE` eller alle steg fullført før sluttkontrakten er godkjent.
- Produksjonsgrenser, teoretisk separasjon og handelsregler er uendret.

## Report Closure

- Gjør ferdig lærings-fill til autoritativt sluttresultat og beholder tidligere SKIP/OBSERVE kun som diagnostisk forsøk.
- Fjerner dobbel læringsevaluering: etablert læringsportefølje synkroniseres én gang til felles konto og ordre-/fillspor.
- Lagrer identisk porteføljekontekst på toppnivå og eksporterer `portfolio_snapshot.json` for beslutningsreplay.
- Utvider Report Consistency Audit til læringsticker, handling, antall og pris på tvers av JSON, TXT og PDF.
- Skiller rapportvarsling og teoretisk læringsvarsling i rapporten.
- Viser alle læringshandler med ticker, resultat, antall, pris, score og produksjonsblokkering.
- Beholder alle resultatetiketter, men reduserer tallstørrelse og celleluft og bruker norsk desimalformat.
- FULL_REPLAY er verifisert i isolert faktisk autonomikjøring med den virkelige kandidatstrukturen fra `MI-20260809-141334`.
