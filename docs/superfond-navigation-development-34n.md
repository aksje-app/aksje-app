# RC16.34n – kursutvikling og gjenopprettet navigasjon

Superfond manglet i allowlisten for URL-gjenoppretting. En ny mobiløkt med aa_nav=superfund fikk derfor ingen aktiv rute, og Start ble vist. Native knapper behandlet dessuten klikk etter oppstart av skriptet og en konsumert rutelease kunne la gamle panelvalg bli stående.

Superfond er nå tillatt på fersk økt. Native hoved- og Mer-knapper bruker callbacks som køer ønsket side før skriptoppstart. Den eksplisitte ruten påføres før bootstrap og før navigasjonswidgets. URL-feltene skrives samlet uten gamle panel-/tab-felt. Brukerrevisjonen økes slik at bakgrunnsarbeid ikke kan gjenopprette et eldre klikk. Innloggingsdata videreføres ikke i URL.

Superfond har områdevelger med URL-lagret valgt seksjon. Valget gjenopprettes ved nettleseroppdatering; søket bevares i applikasjonseid økttilstand når man bytter sider. Tilfeldig manuelt åpning av andre expandere og scrollposisjon lagres ikke ved en helt ny nettleserøkt.

Ventende ordre viser kildens uke-/måneds-/kvartalstall, siste noteringskurs/valuta/dato, risiko, årlig kostnad og konkret ventestatus. Kjøpte posisjoner viser også modellresultat siden inngang. Topp 25 får tilsvarende hovedopplysninger. ISIN, registrerings-/forvalterland, innhentingstid, poeng og ordreopprettelse ligger under Flere detaljer.

Maks 60 eksisterende NOK-kursobservasjoner per toppfond og eid/ventende instrument følger det atomiske snapshotet. Grafer krever to faktiske datoer; det genereres ingen historikk fra periodetall og det gjøres ingen nye markedskall i visningen. Eldre tynne fondsidentiteter suppleres fra allerede lagrede kandidater. Manglende grunnlag står som ikke oppgitt frem til en komplett batch.

Brasil merkes fra eksplisitt MSCI/FTSE Brazil-indeksnavn med kildeforklaring; dette er ikke bekreftelse av faktiske beholdninger. Kildens brede eksponeringsetiketter og ukjent registreringsland er tilgjengelige i detaljene. Kategorikoder gjengis lesbart. Topplisten beholder score/utvalg og viser fortsatt konsentrasjon i kategori. Handelsregler, kapitalkrav, kjørelås og batchgrenser er ikke endret.

Validering: faktiske router-funksjoner kjøres uten tung app-import; fersk økt, første klikk, gamle panelvalg, alle shell-lenker og bounded kurshistorikk testes. Chromium tester 375/430/1280 px og første trykk, reload og valgt seksjon ved 375/430 px. Fysisk iPhone/Safari og produksjonsdeploy må kontrolleres etter deploy.
