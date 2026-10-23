# Sikker overgang til separate NOK-perioder

Arbeidsgren: `fix/systemrevisjon-20261022`. Eksisterende PR: #167.
Ingen produksjonskonto er opprettet, aktivert, nullstilt eller overført i denne revisjonen.
Produksjonsdata er ikke koblet til testmiljøet. Testbeløp er syntetiske og skal aldri importeres.

## Én regnskapsmotor, tre adskilte kontoer

`services/portfolio_accounting.py` bruker eksisterende `economic_ledger.execute`
for Paper Trading (`paper`), Autonomi (`autonomy`) og Superporteføljen
(`super_portfolio`). Kontoene lagres under hver sin `economic_accounts/*.json`.
Gamle Paper-, Autonomi- og Superportefølje-nøkler skrives ikke av denne tjenesten.
Superfond skal ikke opprettes her; familien avvises fordi fondet beholder sitt
native regnskap.

`prepare` krever dokumentert åpningsgrunnlag og oppretter bare DRAFT. Et identisk
gjenforsøk er tillatt; et annet åpningsdokument kan ikke overskrive kontoen.
`approve` er et operatør-API, uten knapp eller automatisk kall fra app/scheduler.
Det krever navngitt godkjenner, godkjenningsreferanse, familie, startdato,
godkjenningstid, miljøomfang og SHA256 av nøyaktig åpningsdokument. Produksjon er
sperret som standard og krever i tillegg eksplisitt operatørkonfigurasjon.
Testgodkjenning kan ikke brukes til produksjonsbokføring. Ingen slik
produksjonskonfigurasjon eller godkjenning er opprettet her.

`record_documented_nok_fill` i `paper_store.py`, `autonomous_portfolio.py` og
`services/super_portfolio_store.py` er eksplisitte adaptere til samme tjeneste.
De tar dokumenterte aksjeutførelser, aldri gamle modellandeler eller vekter.
De ordinære strategimotorenes historiske utførelsesbaner er ikke automatisk
byttet over. Før overgang må den konkrete utførelseskilden levere hele
fill-kontrakten, kontrolleres i isolert prøve og kobles inn som eneste skriver
for den nye perioden. Dette hindrer at én ordre bokføres i to operative regnskaper.

## Data som må fremskaffes per aksjeportefølje

1. Valgt starttid med tidssone, kilde og signert/godkjent avstemmingsgrunnlag.
2. Faktisk kontantbeholdning i NOK ved samme tidspunkt; reserver, uoppgjorte
   handler, innskudd og uttak må avklares uten å telle dem dobbelt.
3. Faktisk aksjeantall, entydig instrument/ticker og instrumentvaluta for hver
   posisjon. Modellvekter, modellandeler og nominelle NOK-allokeringer er ikke
   aksjeantall.
4. Dokumentert gjenværende historisk kostpris i NOK, inkludert allerede påløpte
   kostnader. Kostpris kan ikke utledes av dagens kurs eller dagens valuta.
5. Dokumentert åpningskurs og relevant NOK-kurs med kilde og datostempel.
6. Tilgjengelig originaljournal med gebyrer og valutakostnader, samt en konkret
   mangelliste for hull. Manglende historikk rekonstrueres ikke.
7. Kildekontrakt for nye utførelser: stabil handels-ID, side, faktiske aksjer,
   utført lokal kurs, instrumentvaluta, handels-/kurs-/valutatid, datakilder,
   NOK-kostnader fordelt på kurtasje, valutakostnad og øvrige kostnader.

Ingen produksjonsuttrekk i dette miljøet dokumenterer disse opplysningene
fullstendig. Vi kan derfor ikke angi korrekte produksjonsåpningsbeløp eller
hevde at porteføljene allerede er migrert. Mangellisten vises også i appens
NOK-panel når et grunnlag ikke er forberedt. En kildehenvisning i JSON er
sporbarhet, ikke en automatisk bekreftelse på at vedlegget er korrekt; operatøren
må kontrollere originalbeviset før godkjenning.

## Regnskapskontrakt

Åpningsdokumentet har eksplisitt `at`, `base_currency="NOK"`, `cash_nok`,
`source_ref` og `positions` (også tom beholdning må angis eksplisitt). Hver
posisjon krever `quantity`, `currency`, `cost_basis_nok`, `source_ref`,
`cost_basis_source_ref`, `price`, `price_observed_at`, `price_source` og,
for utenlandsk valuta, `fx_quote` med valuta, basisvaluta, NOK per valutaenhet,
observasjonstid og kilde. Ingen standardkostpris eller antatt FX finnes.

Åpnings-NAV er dokumenterte kontanter pluss markedsverdier i NOK.
Historisk kostpris beholdes separat. Eksempel fra syntetisk test: medbrakt
urealisert tap på NOK 2 000 og en etterfølgende kostnad på NOK 20 gir samlet
realisert tap NOK 2 020, mens den nye periodens resultat er minus NOK 20.
Tapet på NOK 2 000 forsvinner ikke; det merkes som medbrakt ved åpning.

Kjøp reduserer NOK-kontanter med bruttoverdi og eksplisitte kostnader. De samme
kostnadene inngår i kostpris. Tilleggskjøp øker antall og kostpris. Delsalg
fordeler kostpris proporsjonalt. Realisert resultat er nettoproveny minus
fordelt kostpris. Urealisert resultat er markedsverdi minus gjenværende
historisk kostpris. NAV er kontanter pluss omregnede markedsverdier.
Kostnader trekkes ikke fra to ganger.

Periodens nettoresultat = NAV − åpnings-NAV.
Nettoavkastning = NAV / åpnings-NAV − 1, uten eksterne kapitalstrømmer.
Realisert + urealisert − medbrakt urealisert = periodens nettoresultat.
Utbytte, splitt, kapitalinn-/utbetalinger og andre selskapsbegivenheter er ikke
implementert som nye journaltyper. Slike hendelser må avklares før overgang;
de skal ikke skjules som handelsgevinst eller oppdiktede handler.

Aksjeutførelser krever kurs- og FX-bevis maksimalt 15 minutter gamle ved handel.
Åpnings-/NAV-markeringer tillater maksimalt fem kalenderdager. Fremtidige og
foreldede bevis avvises; uverifisert eller foreldet verdi vises uten verifisert
NAV/nettoavkastning. NOK/NOK = 1 er identitet, ikke en oppdiktet valutakurs.
Alle kostnadskomponenter må oppgis, også dokumentert null, med kostnadskilde.

## Journal, atomisitet og gjenoppretting

Åpning, godkjenning, handler og komplette markeringer ligger i én versjonert
hendelseskjede. Hver hendelse har sekvens og lenket SHA256. Hele kjeden spilles
på nytt gjennom samme motor og må samsvare med lagrede kontanter, aksjer,
kostpris, gebyrer og realisert resultat. Hashkjeden er en integritetskontroll,
ikke erstatning for tilgangsstyring, sikkerhetskopi eller eksterne bilag.

`StorageService.mutate_json` bruker fil-/prosesslås lokalt og transaksjon med
advisory lock i PostgreSQL. Journal og beholdning lagres sammen. Identisk
handels-ID og innhold gir ingen ny post; samme ID med annet innhold avvises.
Gjenforsøk fungerer også etter tapt commit-kvittering og senere NAV-markeringer.
Full JSON og CSV kan lastes ned; UI viser ikke bare et avkuttet handelsutdrag.

En stor journal beholdes fremfor å kuttes. Superfonds eksisterende dokumentgrense
på 4 MiB gjelder fortsatt og stanser publisering dersom den overskrides.
Før en slik grense nås må en separat, atomisk arkiverings-/lagringsløsning
kontrolleres; historikk skal ikke slettes for å omgå grensen.

## Superfond

Eksisterende `cash`, `quantity`, `cost_nok` og `last_nok` forblir operativ sannhet.
Nye native handler får antall, brutto NOK, kostnadsfordeling, kostnadsparametre,
lokal kurs, valutakilde, fixingdato og kontanter etter handel. Hele den bevarte
handelsjournalen og verdihistorikken beholdes. Eldre hull fylles ikke inn.
En dokumentert modellåpning registreres bare for en urørt, tom modell med
kjent konfigurert startkapital; dette er simulert modellkapital, ikke en
meglerbekreftet kontantbeholdning. Eksisterende ikke-tomme modeller får ingen
antatt åpningsbalanse.

`services/superfund_accounting.audit_native` avstemmer direkte mot native
journal, beholdning og kontanter. Den oppretter ikke en annen operativ konto.
Kurtasje og valutapåslag er modellens eksplisitte bps, ETF-spread er halv spread.
Løpende fondskostnader inngår i fonds-NAV og trekkes ikke på nytt. Native
beregninger uten kildebevis for eldre handler merkes IKKE VERIFISERT i skjerm,
PDF, CSV, Excel og diagnoseeksport. Ingen utvelgelses- eller salgsregler endres.

## Kontrollert fremdrift uten aktivering

1. Ta skrivebeskyttet eksport og sikkerhetskopi av hver gammel portefølje og
   hele tilgjengelige historikk. Registrer checksums og mangler. Behold
   historiske tap og modeller synlige som uverifisert historikk.
2. Fremskaff og kontroller åpningene ovenfor. Opprett kun utkast i isolert
   overgangsmiljø. Ikke kopier syntetiske testverdier.
3. Kjør dokumenterte faktiske fill-eksempler gjennom de eksplisitte adapterne;
   avstem hver journalpost og sluttbalanse. Kontroller dataflyten fra den
   ordinære utførelseskilden, duplikater og gjenoppretting.
4. Avklar eventuelle utbytter, aksjesplitter og eksterne kapitalstrømmer.
   Kjør leverandørakseptansetestene fra et miljø med fungerende nettverk.
5. Legg et konkret, datert åpningsdokument, mangelliste, avstemmingsrapport og
   operativ plan frem for uttrykkelig godkjenning. Ingen godkjenning er gitt her.
6. Først etter godkjenning: særskilt kontrollert kobling til én utførelseskilde,
   aktivering og overvåking. Stopp ny bokføring ved avvik; ikke slett perioder
   eller rull en commitert journal tilbake ved å overskrive beholdningen.

Status: klar for gjennomgang og isolert overgangsprøve. **Ikke klar for
produksjonsaktivering** uten åpningsbevis, kontrollert utførelseskobling,
leverandørkontroll og uttrykkelig godkjenning.
