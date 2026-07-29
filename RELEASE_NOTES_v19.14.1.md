# AI Aksje Analyzer Pro v19.14.1

## Decision Gate & Runtime Consistency Release

v19.14.1 retter avvikene som ble dokumentert i live-kjøringen av v19.14.0.

### Kritiske rettinger

- Ordrelaget har en hard kjøpssperre: ordinære teoretiske eller virkelige kjøp krever Autonomiutfall `KJØPSKANDIDAT`, kjøpshandling, beslutningsgyldige markedsdata, gyldig evidens og endelig kjøpsklar status.
- En ticker kan ikke kjøpes og selges i samme kjøring. Ordinære handler buffers og avstemmes atomisk før de lagres; ved integritetsfeil rulles kjøringen tilbake.
- PDF/JSON-generering blokkeres dersom handler, kjøpskandidater, beslutningsporter eller sluttposisjoner motsier hverandre.
- Beslutningstrakten synkroniseres med det endelige kanoniske Autonomiutfallet etter rapportkanonisering.

### Autonomi og brukergrensesnitt

- Enkel-modus bruker Norge, Sverige og USA som eksplisitt standardprofil.
- Utvidet Norden, Brasil og full seksmarkedsskanning er separate valg.
- Tidligere skjulte ekspertvalg arves ikke stille som markedsstandard; faktisk konfigurasjon vises før start.
- Prioritert vurderingsrekkefølge 1–3 er beholdt uten medaljer eller kjøpsanbefalingspreg.
- `REVIEW` vises som «Undersøk manuelt», og hver manuell oppgave forklarer hva, hvorfor, forsøkte kilder, stoppårsak, foreslått kilde og beslutningseffekt.

### Kilder og rapportintegritet

- Direkte, offisielle nordiske kildeadaptere er lagt inn for svenske FI-data, Nasdaq Nordic-meldinger og Euronext Oslo-meldinger, med fail-closed håndtering og sekundær kildeoppdagelse kun som reserve.
- Kildeutfall, beslutningsporter og interne statuser presenteres på norsk i PDF.
- Produksjonsterskelen er entydig. Skyggeterskler er kun utfordrersimuleringer og kan ikke utløse kjøp.
- Historiske `raw.raw`-kjeder flates ut og ikke-autoritative øyeblikksbilder begrenses, som reduserte kontroll-JSON-en med 58,76 %.

### Versjon

Program, Autonomi Core, Full Autonomy Execution, porteføljelag og beslutningstrakt bruker den sentrale appversjonen v19.14.1 i den aktive runtime-kontrakten.

### Verifikasjon

- 490 pytest-tester bestått, inkludert 4 deltester.
- 362 separate regresjonstester bestått.
- Den kjente v19.14.0-feilen med AAPL-kjøp/salg blokkeres av v19.14.1-rapportintegriteten.
- Korrigert PDF fra live-datagrunnlaget: 11 sider, rendret og visuelt kontrollert.
- Direkte kildeadaptere er parser- og policytestet offline. Tilgjengelighet i produksjonsmiljøet må fortsatt bekreftes i en ny live-kjøring.
