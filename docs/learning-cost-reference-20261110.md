# Dokumentert kostnadsreferanse i eksisterende læring

Dette er videre arbeid med målegrunnlaget i punkt 2. Punkt 5, historisk strategitest, er ikke startet. Handelsregler, godkjenninger og porteføljer endres ikke.

Den nye referansen bruker den allerede godkjente kostnadsmodellen for Autonomi: 20 basispunkter per inngang/utgang og 25 ekstra ved hver valutakonvertering. Den er merket **Autonomis kostnadsreferanse i NOK**, ikke resultat for Autonomi eller Superporteføljen. Salgsregelforskningens separate kostnad på 30 basispunkter per testhandel beholdes.

Modellen regner på én normalisert totalavkastningsenhet. Både inngangs- og utgangskostnad trekkes med riktig kontantstrøm: utgangsverdi etter utgangskostnad deles på inngangsverdi inkludert inngangskostnad. Dette er en proporsjonal modell, ikke observerte meglerkostnader eller et bestemt antall aksjer.

Regneeksempler med uendret valuta, **ikke observerte aksjer eller testresultater**: NOK-avkastning på 0 % før kostnader gir omtrent −0,3992 % etter inngang/utgang; +2 % gir +1,5928 %. Ved to utenlandske valutakonverteringer brukes den dokumenterte ekstra kostnaden i begge ender. En eksisterende utenlandsk kontantbeholdning uten konvertering er et annet scenario og er ikke modellert her.

## Datakrav og bevaring

- Den økonomiske definisjonen lagres uforanderlig i autoritativ PostgreSQL. Etter at definisjonens transaksjon er ferdig, tas et faktisk klokkeslett og en separat uforanderlig publiseringskvittering. Kjøretidens starttid brukes ikke som bevis for når metoden var tilgjengelig. Referansen krever at dette beviset er fra før den modellerte inngangen.
- Kun gjeldende V2-observasjoner kan få referansen. De 41 nye observasjonene som var lagret ved utviklingsstart, har dokumentert NOK-valuta og ingen fullførte målinger. Gamle rader og de 78 karanteneradene skrives ikke om.
- NOK/NOK bruker identitet 1 og ingen valutakostnad. Utenlandsk valuta krever eksplisitte, kildebundne spotreferanser ved både inngang og utgang, med korrekt valutapar og høyst 15 minutters alder. Daglige indikative Norges Bank-kurser erstatter ikke disse. Ingen ny valutahenting eller ekstra skanning er opprettet.
- Opprinnelig brutto måling og nye kostnadsreferanser skilles. Frosne målinger overskrives ikke, heller ikke for å fylle inn et tidligere ukvalifisert kostnadsfelt. En revidert allerede kvalifisert valutareferanse stoppes som historikkrevisjon; forsvinner nye valutadata, beholdes den opprinnelige frosne referansen.
- Før et kostnadstall inngår i rapportens gjennomsnitt, regnes det på nytt fra det lagrede kildegrunnlaget og den uforanderlige definisjonen. Kontroller, eldre metoder og uriktige/ukvalifiserte kostnadsblokker inngår ikke. Positive og negative gyldige resultater inngår likt. Antall og manglende grunnlag vises.

Publisering skjer bare i eksisterende planlagt vedlikehold. Appvisning og rapportforhåndsvisning kan ikke opprette definisjonen. Det er ingen ny læringsprosess, arbeidstjeneste, tidsplan, ordre eller parameterendring.

## Hva referansen ikke godkjenner

Prisgrunnlaget er fortsatt leverandørens justerte totalavkastningsproxy. Modellen forutsetter reinvestering inne i denne enheten, uten mellomliggende reinvesteringskostnader, og er før skatt. Referansen er ikke dokumentert kontantutbyttebok, faktiske fyllinger eller netto porteføljeresultat. De eksisterende feltene for faktisk nettoresultat forblir null/false; dette gjelder også når en modellreferanse kan beregnes.

Denne publiseringsregelen gjelder fremoverskuende V2-observasjoner. En senere retrospektiv studie i punkt 5 må ha et eget forhåndsdefinert studie- og utvalgsgrunnlag. Den kan gjenbruke den godkjente økonomiske kalkulatoren, men skal ikke fremstille historiske simuleringer som om den nye metoden var registrert før historiske kjøp.

Uten dokumenterte utenlandske endpoint-kurser er modellverdien fortsatt utilgjengelig. Manglende historiske rapportkilder og første ikke-tomme ordinære signalregistrering følges fortsatt i sak 196. Denne endringen lukker ikke disse datakravene.

## Verifikasjon

110 fokuserte tester bestod med isolert PostgreSQL. Nye feiltilfeller ble gjenskapt før retting: kostnader og inngangsnevner, feil/manglende/daglig/fremtidig/foreldet valuta, kontrakt etter inngang, forsinket definisjonsskriving, uforanderlig publisering, faktisk innlasting i målemotoren, frosne valutarevisjoner, manglende ny valuta, tap i gjennomsnittet, manipulert kostnadsblokk og skrivefri rapportvisning.

Full lokal testkjøring: 2 710 bestått, 236 hoppet over og fire beståtte deltester. De samme fire tidligere påviste grunnfeilene består: `test_production_roots_and_complete_lock_are_exact_and_installed` (lokale avhengighetspins), `test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch` (eldre FakeCursor), `test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master` (live universkilde) og `test_new_breach_sends_pushover_after_configuration_change` (ekstra tidsavhengig valutavarsel). Uavhengig gjennomgang og Release Gate skal bestås før utrulling; produksjonsbevis registreres i PR og oppfølgingssaken.
