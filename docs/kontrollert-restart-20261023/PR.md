Bevar gammel historikk ved kontrollert ny start for Paper, Autonomi og Superporteføljen. Endringen forbereder tre isolerte NOK-perioder med null aksjer og ny modellkapital (100 000 / 500 000 / 1 000 000), uten fiktive salg eller endring av strategier og læring.

- Kryptert, separat arkiv av full database og deklarerte runtime-/rapport-/modellmapper; tidsstempler, SHA256, skrivebeskyttelse, kildeendringskontroll og kontrollert tilbakelesing.
- Atomiske, arkivavhengige kontoutkast; ingen automatisk aktivering eller bruk av gamle kontanter/posisjoner. Gamle destruktive reset-funksjoner og Papers ujournalførte kapitaloverskriving sperres.
- Lesepanel og JSON-eksport på alle tre sider skiller historisk læring, gamle muligens uverifiserte resultater og nytt NOK-nettoresultat. Superfond beholder eksisterende modell.

Validering: 2 459 tester + fire deltester besto i bred isolert pakke (85 nettleserforløp, 23 PostgreSQL-tester og alle opprinnelige 99 regresjonstilfeller). Etter siste avgrensede kapitalbinding besto 14 målrettede restarttester. Ekte PostgreSQL-dump/gjenoppretting er prøvd med syntetiske data. 24 releasekontrakter og fem Node-tester besto. To live-leverandørtester er IKKE VERIFISERT: CONNECT-proxy HTTP 403.

Faktisk produksjonsarkiv og produksjonsutkast er ikke opprettet: kilder, varig privat arkivmål og nøkkelforvaltning mangler i dette miljøet. Senere motoromkobling krever egen kontroll. Ingen nullstilling, læringsreset, produksjonsaktivering, merge eller deploy.

Detaljert rapport: docs/kontrollert-restart-20261023/rapport.md. Ingen produksjonsdata, databasekopier eller hemmeligheter inngår i endringen.
