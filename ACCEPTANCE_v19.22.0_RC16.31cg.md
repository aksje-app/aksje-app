# Akseptanse – RC16.31cg

## Godkjent funksjonell kontroll

- [x] ROGS: fallende score kan ikke samtidig varsles som AKSELERERER.
- [x] WWI: én enkelt bedring kan ikke omgå hysterese og gi et nytt positivt varsel.
- [x] DNO: oppsettstatus, retning nå og datadekning er separate felt.
- [x] Signalalder og breakout-hold er monotone for samme signal.
- [x] En eksplisitt ny signal-ID kan starte ny alder.
- [x] Uendret snapshot er deterministisk og stille.
- [x] Delvis RS-kø kan ikke brukes som full markedsrangering eller positiv beslutningsstøtte.
- [x] Fullscan-RS bevares gjennom den avgrensede 15-minuttersoppdateringen.
- [x] Uferdig dagsvolum vises, men straffes ikke som ferdig dagsvolum.
- [x] Scorebane og siste endring bruker samme presisjon.
- [x] Lange Pushover-meldinger forkortes mellom hele linjer og får én datafot.
- [x] Alle Pushover-produsenter bruker den sentrale senderen.
- [x] Parallell monitorjobb avsluttes uten duplikatvarsel.
- [x] Komplett rapportpakke inneholder PDF, teknisk PDF, JSON, tekst og diagnose når tilgjengelig.
- [x] Stagnasjon blir ikke «bytt ut» uten navngitt og kontrollert alternativ.
- [x] Delvis salg beholder restposisjonen og avstemmes korrekt.
- [x] Retention/sletting er eksplisitt opt-in.

## Regresjonsstatus

Den brede historiske testsamlingen består av tester fra mange tidligere RC-kontrakter. Endelig kjøring for RC16.31cg ga 1206 beståtte, 70 feil og 4 beståtte deltester. De gjenværende feilene omfatter kontrakter som uttrykkelig krever tidligere versjonsnavn, tre valutadesimaler, gamle dupliserte nedlastingsknapper, tidligere markedsscope eller en eldre og mindre sikker exit-/retentionregel. De brukes derfor ikke som bevis på RC16.31cg-kontrakten. Gjeldende RC16.31cg-akseptansesuite er 16/16 grønn, fullsystemrevisjonen er grønn og PDF-ene er visuelt kontrollert.
