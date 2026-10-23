Kontrollert NOK-produksjonsstart for Paper Trading, Autonomi og Superporteføljen

Eksisterende handelsmotorer og scheduler kan nå bruke eksplisitt valgte NOK-perioder med én autoritativ journal. Aktivering krever signert operatørgodkjenning av installasjon, konto, periode, kapital, uendret strategikonfigurasjon, fullstendig kryptert arkiv og fysisk verifisert gjenoppretting. Merge/deploy/startup velger ingen konto automatisk.

Ny kapital er 100 000 / 500 000 / 1 000 000 NOK, alle uten aksjer. Gamle beholdninger, negative resultater, læring og rapporter beholdes separat; ingen fiktive historiske salg. Streng PostgreSQL-lagring, append-only journal, atomiske jobbkvitteringer, pause/gjenopptakelse, økonomiske hendelser og produksjonstørrkjøring følger samme regnskapsvei. Superfonds native økonomi er uendret.

Validering: 2 563 tester og fire deltester besto etter siste kodeendring (521,76 s), uten feil eller skips. Inkluderer 97 nettleserforløp, 77 PostgreSQL-forløp og alle opprinnelige 99 regresjonstilfeller. Separat kombinasjon med #166: 154 beståtte. Nøyaktige sluttall: docs/produksjonsklargjoring-20261023/testresultater.json og sluttkjoring.txt. Full rapport og eksakt operatørprosedyre: rapport.md og DRIFT.md i samme mappe. Kompatibilitet med #166 testes kun i separat testkopi.

Live Yahoo er IKKE VERIFISERT: eksternt CONNECT-proxy gir HTTP 403. Ingen faktiske Render-data, arkiver eller aktiveringer er behandlet. Før produksjonsoppstart må operatøren verifisere alle faktiske datakilder og uavhengig sikkerhetskopi, gjennomføre restore og live leverandør-/tørrkjøringskontroll og signere hver konto eksplisitt. Ingen merge eller deploy er utført.
