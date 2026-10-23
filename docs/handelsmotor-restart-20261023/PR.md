Tre ordinære handelsmotorer kan nå utføre simulerte handler mot en eksplisitt, separat NOK-restartperiode. Kontanter, antall aksjer, kostpris, valuta, kostnader og resultat bokføres i eksisterende NOK-motor; gammel økonomi og læring beholdes.

- Én atomisk jobbtransaksjon for verdsetting, handler, beslutnings-/parameter-/kursbevis, strategitilstand og gjenforsøkskvittering. Konto-, periode-, åpnings-, godkjennings- og miljøreferanse kontrolleres før handel; ingen gammel reservebane.
- Ordinære Paper-, Autonomi- og SP-regler gjenbrukes. NOK-sizing inkluderer gebyrer, Autonomi viderefører neste-sesjonssignaler, og feilaktig gjenkjøp etter delsalg sperres. Siste Paper-kjøp styrer tilleggskjøpskarantenen.
- Splitt justerer strategiankre uten å endre terskler. Eksisterende journal håndterer kapitalbevegelser og utbytte.
- Valgt ny NOK-periode får nøkkeltall, NAV-graf og PDF/CSV/Excel/diagnose-ZIP, med tydelig skille fra gammel historikk/læring.

Produksjonsaktivering forblir sperret. Faktisk produksjonsarkiv og kontoutkast er ikke opprettet. Schedulerens produksjonskobling, tørrkjøring og godkjennings-/aktiveringsvei krever separat kontroll. Ingen merge, deploy, nullstilling eller produksjonsendring er utført.

Rapport, testresultater og ti-trinns produksjons-/tilbakeføringsprosedyre ligger i `docs/handelsmotor-restart-20261023/`. Ingen produksjonsdata eller hemmeligheter følger endringen. Live Yahoo for MYCR.ST/MSFT er IKKE VERIFISERT: nettverksproxy returnerer HTTP 403. Sluttall fra den isolerte pakken føres i `testresultater.json`.

Validering etter siste kodeendring: **2 485 tester + fire deltester besto**, ingen feil eller skips (412,45 s). Inkluderer **91 nettleserforløp**, **24 PostgreSQL-tester** og alle **99 opprinnelige regresjonstilfeller**. 24 releasekontrakter, fem Node-forløp og avhengighets-/runtimekontroll besto.
