# Samlet fortsettelse med direkte kolonnelesing

Bruk **[FORTSETT-MED-NATIVE-ARKIV-WINDOWS.txt](FORTSETT-MED-NATIVE-ARKIV-WINDOWS.txt)**.
Kopier hele filen til samme Windows PowerShell-vindu og trykk Enter.
Den fortsetter kun `nok-job-20261024T165039Z`, med eksisterende lokal sertifikatmappe,
SSH-identitet, kildeattestasjon og installerte PostgreSQL-18-verktøy. Ny ZIP-utpakking,
nøkkelregistrering, tjenestestart og betalt ressurs er ikke nødvendig. Hold app-faner
lukket og scheduler/andre skrivere stanset slik tidligere bekreftet.

Filen kjører gjennom kryptert fullarkiv, uavhengig Windows-kopi med faktisk lokal
dekryptering, fysisk restore på egen privat Unix-socket på eksisterende web-arbeidsplass,
og opprettelse/avstemming av tre INAKTIVE DRAFT-kontoer. Tidligere saldoer, historikk,
læring og strategier bevares. Kontoene aktiveres ikke, ingen route velges og B er ikke klar.
Før en eventuell senere aktivering må også dens kildeverifikasjon bruke den validerte
native-adapteren. Deployet gammel `row_to_json` må fortsatt ikke kjøres på disse dataene.
Bare en midlertidig kopi av arkivnøkkelen overføres; originalen på PC-en beholdes og
operatørsigneringsnøkkelen leses ikke. Del bare sluttstatus `final-result.json`.

`Start-AksjeNativeArchive` og `render_native_batch.py` er separate, kontrollerte
innganger. Alle eldre start-/fortsettelsesfiler og `render_batch.py` beholder sperrene.
Startfunksjonen krever akkurat denne eksisterende jobben og innebygd worker med riktig
SHA256. Uforseglede, tomme feilkataloger bevares; forseglet arkiv eller senere/ukjent
kontostatus gir stopp fremfor repetisjon. Ved avbrudd må status avklares før ny kjøring.

Den nye workerens fingeravtrykk bruker samme eksporterte snapshot som pg_dump og samme
kanoniske JSON-/multisetthash som originalkoden. TEXT hentes direkte som UTF-8-bytes,
JSON-escapes inkrementelt i små biter på klienten og bygges aldri til komplett
`row_to_json` på kildeserveren. En enkelt astral Unicode-verdi utløser dermed heller
ikke en ekstra komplett UCS4-streng i klientminnet. Både kilde-, restore- og endelig
kildekontroll bruker den samme adapteren. Ingen `row_to_json`-orakelprøver utføres på
produksjonen. Snapshot erstattes ikke med en senere tilkobling ved feil.

Ferske katalog-/lengdemetadata, PG18/UTF8, alle deklarerte databasekilder og fravær av
andre aktive/åpne transaksjoner kontrolleres før arkivering. Hver tabell må fortsatt
passe innenfor grensen på 160 MiB samlet innfødt radstørrelse; ukjente ikke-TEXT-varlena
med verdier avvises. Bare deklarerte kildeendepunkter eller denne jobbens private
`nok_restore_<nummer>`-socket tillates; andre kilder og endrede TLS-parametere avvises.
Web-containerens minnegrense må være minst 2 GB og anslått tilgjengelig ramme minst
1280 MiB, inkludert rapportert inaktiv filcache som kan gjenvinnes. Fingeravtrykksbarnet
har 768 MiB adressegrense; øvrig worker og isolert restore arver 1152 MiB.
Dette er konservative kontroller, ikke en måling eller garanti for produksjonens topp-RSS.
Kjøringen skriver en livstegnmelding hvert 30. sekund mens et steg arbeider.

Verifikasjon utført før publisering:

- Brukerens PG18.6-kopi på PC: 12 tabeller, 22 avgrensede originalkodeprøver,
  68 sekunder. Største TEXT-verdi 162212873 byte. Dette var den tidligere native
  strengvarianten; den nye bytevarianten er i tillegg prøvd isolert nedenfor.
- Brukerens PG18.4-kilde: kapasitetsmetadata bestod, shared_buffers 268435456 byte,
  øvre radstørrelse 162213017 byte, null andre aktive/åpne transaksjoner og null
  ukjente variable kolonner. Lengdelikhet alene dokumenterer ikke likt innhold.
- Isolert PG16.2: nøyaktig originalhash for datatyper/NULL/Unicode/duplikater,
  chunkgrenser og utelatelse av kun egen nye periode. Opprinnelig eksportert snapshot
  beholdes også ved en senere, samtidig innsatt testrad.
- Isolert PG16.2: én 160 MiB TEXT-verdi med anførselstegn, bakstrek, kontrolltegn og
  astral Unicode. Kilde-lesing og full custom pg_dump bestod med 256 MiB shared_buffers
  og arvet 1 GiB server-adressegrense. Byte-klienten bestod under 768 MiB adressegrense,
  med omtrent 500 MiB målt topp-RSS. PostgreSQL-backendens RSS ble ikke målt.
- Den store fixture-restoren feilet kontrollert ved 1 GiB adressegrense. Med
  restore-konfigurasjonens 32 MiB shared_buffers og 1152 MiB arvet adressegrense bestod
  fysisk restore og nøyaktig byte-fingeravtrykk. Ingen server-SIGKILL i sluttesten.
- Separat isolert kryptering/dekryptering, fysisk restore til privat socket, uendrede
  runtime-filer og full kildeverifikasjon bestod gjennom de eksisterende core-funksjonene.
- Offisiell PowerShell-parser, faktisk kjøring av innebygd SHA256-kontroll og avvisning av
  feil/manglende jobb før fil-/SSH-handlinger bestod. Alle åtte core-kilder er uendret.

Ingen produksjonsarkivering eller DRAFT-opprettelse er utført fra Codex ved publisering.
Faktisk Windows/Render-kjøring av den nye samlede filen gjenstår. PG16-fixtures erstatter
ikke produksjonsbevis fra PG18. Scheduler er bekreftet suspendert via Render API.

## Bakgrunn og sperrer i eldre verktøy

PostgreSQL-logg har bekreftet at databaseprosesser ble drept med SIGKILL mens
arkivets navngitte cursor ble lest, etterfulgt av full reinitialisering og recovery.
Det skjedde også med `FETCH FORWARD 1`. Loggen dokumenterer prosessavslutning og
recovery; selve OOM-/kernelårsaken er ikke bekreftet i denne pakken.

**Ikke kjør eldre versjoner av Windows-/fortsettelsesfilene eller kildeavtrykket
manuelt i produksjon.** Nåværende Windows-startfunksjon stopper før SSH eller
lokale/eksterne jobbsteg. Python-workerens `archive` og `archive-checkpoint` er
også sperret før applikasjonsimport, kildetilkobling og nye arkivartefakter.
Det finnes ingen miljøvariabel eller `APP_ENVIRONMENT=test`-omgåelse.

Fingeravtrykksadapteren avviser produksjonskilden før eksport av snapshot. Bare
konto-uavhengige `nok_restore_<nummer>`-databaser på jobbens egen private Unix-
socket er tillatt. Hostaddr/TCP, andre databasenavn og lenkede/åpne socketmapper
avvises. Deployet applikasjon og dens strategier er ikke endret av denne sperren.

Videre validering skal skje mot en separat, gjenopprettet kopi. Eksisterende
porteføljer, læring og Superfond skal bevares. Ingen ny konto er aktivert eller
godkjenning B klargjort. Pakken er ikke en ferdig produksjonsoppstart.

De tidligere testene med 512 MiB samlede testdata og små enkeltrader dokumenterte
klientens minnebruk og hashkompatibilitet. De dokumenterte ikke serverens
minnebruk ved svært store produksjonsrader. De skal ikke brukes som klarsignal
for et nytt produksjonsforsøk. Ingen produksjonslogger, databasedata eller nøkler
er inkludert her.

## Etter lokal gjennomgang: bare produksjonens lengde- og kapasitetsmetadata

Bruk [KONTROLLER-RENDER-KAPASITET-WINDOWS.txt](KONTROLLER-RENDER-KAPASITET-WINDOWS.txt)
for en avgrenset, skrivebeskyttet kontroll via eksisterende Render-SSH-identitet.
Kopier hele filen inn i samme Windows PowerShell-vindu og trykk Enter. Den finner
forrige private jobb og avleder den offentlige nøkkelen fra den tilhørende egne
SSH-identiteten. Ingen ny nøkkel, registrering, konto eller fjernjobb opprettes. Den gamle
`Start-AksjeOperator`-funksjonen sperres også i den aktuelle PowerShell-økten.
Vertsverifikasjon beholdes. Ingen arkiv-/operatørsigneringsnøkkel overføres.

Kontrollen leser kun PostgreSQL-kataloger, `octet_length(TEXT)` og `pg_column_size`.
TOAST-lengde-/lagringsmetadata brukes uten å hente modellverdier eller bygge store
JSON-rader. Transaksjonen er READ ONLY / REPEATABLE READ med tidsgrenser,
parallelle lesearbeidere og JIT deaktivert kun for denne sesjonen. Ingen global
innstilling, portefølje, historikk, læring, strategi eller scheduler endres.
Aktuelle databasekilder må alle finnes i forrige gjennomgåtte inventar.

Resultatet viser logiske feltstørrelser, delt bufferstørrelse, øvrige åpne/aktive
transaksjoner og en konservativ, uttrykkelig foreløpig minnescreening. Regelen
bruker en konservativ nominell ramme for tidligere oppgitt Basic-1GB, ikke en
måling av faktisk ledig serverminne eller topp-RSS. Ukjente variable ikke-TEXT-typer,
store rader og overskredet budsjett flagges. Et positivt screeningresultat er heller
ikke en produksjonsgodkjenning. Arkiv- og aktiveringssperrene oppheves ikke.

Bare metadata lagres i `%LOCALAPPDATA%\AksjeNokOperator\source-header-check-...\source-header-result.json`.
Ingen produksjonsdata, nøkler eller slike resultatfiler legges i GitHub.
Katalog-/lengde-SQL er testet i isolert PostgreSQL 16.2 med en stor TEXT-verdi;
innhold ble ikke hentet eller endret. Innebygd kode, hash, PowerShell-parser og
matching av eksisterende SSH-identitet er kontrollert. Brukeren har senere bekreftet at Render-kontrollen på PG18 bestod;
resultatet gir alene ikke godkjenning for arkiv eller kontoaktivering.

## Neste kontroll: direkte kolonnelesing på lokal kopi

Kopier hele [KJOR-LOKAL-FINGERAVTRYKK-WINDOWS.txt](KJOR-LOKAL-FINGERAVTRYKK-WINDOWS.txt)
inn i Windows PowerShell og trykk Enter. Den er selvstendig; ny ZIP-utpakking er ikke
nødvendig. Databasen er låst til `aksje_restore_test` på `127.0.0.1:5433`, PostgreSQL
18, i REPEATABLE READ / READ ONLY. Feil mål, versjon eller skrivbar transaksjon
stopper før tabellkontrollen. Eventuell lokal autentisering skjer i terminalen,
uten passord i kode, kommandolinje, rapport eller chat.

Full gjennomgang leser TEXT-kolonner direkte. De store tekstene JSON-escapes i
små biter på klienten før hashing, i stedet for PostgreSQL `row_to_json` av hele
raden. Ikke-TEXT-felt bruker PostgreSQLs JSON-representasjon per felt, slik at
numerikk, datoer, bytea og øvrige typer beholder eksisterende kanonisering.
Små, størrelsesfiltrerte eksempler sammenlignes med original `row_to_json`-algoritme
på **kopien** før tabellen leses. Dataverdier vises ikke. Kontrollformat og
multisett-SHA256 er uendret; ingen data, tap eller tidligere perioder utelates.

Kontrollen laster ved behov egne verktøy til kontrollmappen, ikke globalt:
CPython 3.13.17 fra Python Software Foundations NuGet-pakke og psycopg2-binary
2.9.13 fra PyPI. Pakker, Python-binær og innlimt kontrollkode har fast SHA256.
Ingen pip-kommando, administratorinstallasjon eller endring av ExecutionPolicy.
Både fremdrift og lokal sluttkvittering ligger under `%LOCALAPPDATA%\AksjeNokOperator`.
Kontrollen endrer ingen porteføljedata og kontakter ikke Render. Store tekstfelts
logiske størrelser og tilgjengelig PC-minne kontrolleres før lesing.

Send bare `local-native-result.json` som resultat. Den inneholder tabellvise
radantall, kontrollavtrykk, størrelser og teststatus, ikke handler eller payload.
Det er et resultat fra den lokale testkopien, ikke et nytt produksjonsarkiv eller
bevis på at kopien og dagens produksjon har identisk innhold. Kontoene aktiveres
ikke, og produksjonssperren oppheves ikke automatisk.

Ny lokal PostgreSQL 16.2-fixturetest viser identiske kontrollavtrykk mot uendret
kjernemotor for TEXT, desimaler/flyttall, boolske verdier, dato/tid, bytea, arrays,
JSON/JSONB, char/varchar, NULL, uvanlige identifikatorer, tomme tabeller og ekskludering
av en eksplisitt ny periode. En 32 MiB tekstverdi med mye Unicode/escaping ga også
nøyaktig samme hash. Encoderens enkeltbiter er begrenset i størrelse. Feil lokal
vert, database, port, versjon eller transaksjonsmodus avvises uten tabellskann eller
sluttkvittering. PowerShell-parser og innebygd kodehash er kontrollert. Faktisk
Windows/PostgreSQL 18-kjøring av denne nye gjennomgangen gjenstår.

## Innledende skrivebeskyttet metadatakontroll av lokal kopi

Bruk [KONTROLLER-LOKAL-KOPI-WINDOWS.txt](KONTROLLER-LOKAL-KOPI-WINDOWS.txt) på
Windows-PC-en. Kopier hele filen inn i PowerShell og trykk Enter. Den bruker
`127.0.0.1:5433`, bruker `postgres` og den eksplisitte kopien `aksje_restore_test`.
Ingen Render-, SSH-, arkiv-, konto- eller strategioperasjon finnes i denne filen.
Eventuell autentisering håndteres bare av den lokale PostgreSQL-klienten.

Den starter en READ ONLY-transaksjon med tidsgrenser og krever riktig database,
loopback-server og PostgreSQL 18 før tabellmetadata hentes. Psql-startfiler er
slått av, og arvede PG-rutingvariabler ryddes midlertidig og gjenopprettes.
Tabellnummer fire undersøkes med systemmetadata og `pg_column_size`, uten
`row_to_json` eller serialisering av porteføljer, rapporter og modellpayload.

Kun metadata lagres i en privat kontrollmappe under `%LOCALAPPDATA%`, som
`local-copy-status.jsonl`. Ingen nøkkel-/sertifikatfil leses. PowerShell krever
både korrekt endepunkt og eksplisitt fullførtstatus før den melder suksess.
Porteføljer, historikk og læring endres ikke.

Parser er kontrollert med offisiell PowerShell. SQL-logikken er testet med lokale
PostgreSQL 16.2-fixtures; produksjonens PG18-versjonssperre avviser 16 før tabell-
lesing. For normal SQL-gren ble kun forventet majorversjon tilpasset i testkopien.
Feil databasenavn avvises, radverdier vises ikke, og fixtureinnhold forble uendret.
Windows/PostgreSQL 18-kjøring på den faktiske lokale kopien er ikke verifisert ennå.

Resten av dokumentet er historisk operatørbeskrivelse, **ikke en kjøreinstruks
for produksjon**. Den er beholdt for sporbarhet.

---

# Samlet operatørkjøring – arkiv, restore og inaktive kontoer

Dette er én sammenhengende kjøring fra Windows-PC-en, ikke flere enkeltkommandoer
i Render Shell. Den eksisterende arkiv-/regnskapsmotoren fra PR #167 gjenbrukes.
Ingen applikasjonskode, strategier eller læringsregler endres.

## Start

1. Pakk ut ZIP-filen i en lokal mappe.
2. Åpne `KJOR-SAMLET-WINDOWS.txt`, kopier hele innholdet, og lim det inn i et vanlig
   Windows PowerShell-vindu. Ingen endring av ExecutionPolicy er nødvendig.
3. Oppgi mappen der pakken ble pakket ut, og mappen med dine eksisterende
   `archive-certificate.pem`, `archive-key.pem` og `operator-certificate.pem`.
   Oppgi bare lokale stier i programmet; ikke send nøkkelinnhold i samtalen.

## Opprinnelig feil skal overleve opprydding

En `InterfaceError: connection already closed` under rollback kunne maskere feilen
som først brøt lesingen. Operatørkoden bevarer nå den opprinnelige feilen gjennom
feil ved rollback, cursor-lukking og tilkoblingslukking. En selvstendig
oppryddingsfeil stopper fortsatt kontrollen. Ingen suksesskvittering sendes før
oppryddingen er ferdig.

Ved ny feil vises `PRIMARY FAILURE` nederst i konsollen, med SQLSTATE, maskert
årsak og `READ-ONLY PROGRESS`: lesesteg, tabellnummer, antall hentede rader og
største rad målt i tegn. Selve radinnholdet tas ikke med. Feilen i underprosessen
beholdes som strukturert årsak, i stedet for en lang JSON-streng med escape-tegn.
Dette er en retting av diagnostikk og opprydding; den underliggende årsaken til
produksjonens brudd i underprosessen er fortsatt ikke dokumentert.

Lokal PostgreSQL 16.2-test terminerte en egen testtilkobling med vilje og verifiserte
at original `OperationalError` beholdes, at `InterfaceError` ikke erstatter den,
og at en mislykket kontroll ikke skriver en suksessmelding. Normal kontroll gir
fortsatt nøyaktig samme kanoniske kontrollavtrykk. Ingen produksjonstilgang ble brukt.

## Minnebegrenset kontrollavtrykk uten algoritmeendring

Ved `MemoryError` under `database_fingerprint` brukes den oppdaterte
`FORTSETT-ETTER-ARKIVSTOPP.txt`. Vent til en pågående eldre kjøring er avsluttet;
ikke kjør to operatører parallelt. Filen inkluderer rettet operatørkode og trenger
verken ny utpakking, ny nøkkel eller reinstallasjon av PostgreSQL-verktøyene.

Den uendrede kontrollavtrykksalgoritmen kjøres nå i en lett separat Python-prosess
med maksimalt 768 MiB adresseplass. Den leser én rad per databasehenting, i stedet
for å samle 1000 store JSON-rader i libpq. Forelderens åpne transaksjon eksporterer
snapshot; barnet importerer nøyaktig dette før lesing i REPEATABLE READ / READ ONLY.
Utgått/ugyldig snapshot eller feil gir stopp, aldri en ny skjult live-snapshot.
Kanonisering, hashsummer, radtelling og unntaket for den nye perioden er uendret.
Tilkoblingsdata går bare gjennom barnets stdin-rør, aldri kommandolinje eller rapport.

Adapteren brukes i operatørprosessen både ved arkivering, fysisk restore og
etterkontroll av uendret kilde. Deployet applikasjonskode, strategier og læring endres
ikke. Arkivformatet og kontrollavtrykkene er kompatible med eksisterende motor.

Avgrenset lokal PostgreSQL 16.2-test: gamle 1000-raders batch feilet med
`out of memory for query result` under 256 MiB adressegrense. Ny prosess kontrollerte
512 MiB testdata med omtrent 25–28 MiB topp-RSS og nøyaktig uavhengig forventet hash.
Testen verifiserte også Unicode/desimaler/duplikater/periodeunntak, eksportert
snapshot, kryptert arkiv, fysisk restore, alle radkontrollavtrykk, runtime-filer og
uendret kilde. Dette var isolerte testdata, ikke produksjonsdata eller en fullført
produksjonskjøring på PostgreSQL 18. Produksjonsresultatet må fortsatt hentes fra
faktisk operatørkjøring. Ingen gammel applikasjonstestpakke ble kjørt på nytt.

## Fortsett etter uforseglet arkivstopp

Etter bestått PG18-installasjon kan `FORTSETT-ETTER-ARKIVSTOPP.txt` brukes dersom
arkivsteget stoppet og ingen arkivkvittering eller DRAFT finnes. Filen inkluderer
oppdatert operatørkode, gjenbruker samme jobb, nøkkel og kildeattestasjon, og hopper
over installasjonen. Ingen ny utpakking eller endring av deployet appkode kreves.

En egen kontroll kjøres før arkivnøkkelen overføres: det må finnes en faktisk
STOPPED-kvittering fra arkivsteget, nøyaktig kildeattestasjon og ingen senere
arkiv-/restore-/kontoartefakter. Bare helt tomme mapper fra mislykkede arkivforsøk
aksepteres og bevares. Enhver kryptert fil, kvittering, ukjent eller ikke-tom mappe
stopper automatisk fortsettelse. Ingen eksisterende fil eller økonomisk historikk
slettes for å tillate gjenforsøk.

Deretter gjør den eksisterende arkivmotoren ett nytt arkivforsøk med nytt unikt
arkiv-ID og ny skrivebeskyttet snapshot. Inventar og skriverstans kontrolleres av
motoren på nytt. En tidligere skjult `OperationalError` er ikke alene en diagnose; den konkrete
`MemoryError` håndteres med den minnebegrensede adapteren beskrevet over. Ved ny feil vises SQLSTATE, maskert feilmelding og
kildekodeplassering. Tidligere STOPPED-kvitteringer bevares, og nye får unik ID.
Ingen produksjonsaktivering finnes i denne operatørkjøringen.

## Fortsett etter PG18-installasjonsfeil (Signed-By)

Hvis installasjonen stoppet med `Conflicting values set for option Signed-By`,
bruk `FORTSETT-ETTER-PG18-FEIL.txt`. Kopier hele filen inn i samme PowerShell-vindu
og trykk Enter. Den inneholder den korrigerte installasjonskoden; du trenger ikke
pakke ut ZIP-filen på nytt eller redigere Render-oppsettet.

Fortsettelsen gjenbruker jobb, SSH-identitet, forhåndskontroll og den faktiske
kildeattestasjonen. Lokal og ekstern jobb må fortsatt være før arkivering: ingen
arkivnøkkel, arkivmappe, bekreftet regnskapskonfigurasjon, restore-server, DRAFT-
forsøk eller sluttkvittering. Et senere eller usikkert steg gir stopp. Den tidligere
attestasjonen må være boolsk sann og vise til nøyaktig samme inventar. Hold fortsatt
scheduler og øvrige skrivere stanset; arkivmotoren kontrollerer transaksjoner på nytt.

Årsaken er at systemets PGDG-kilde og jobbens egen PGDG-kilde kan angi ulike
`Signed-By`. Rettelsen tar bare med én PGDG-kilde i jobbens private APT-oppsett.
Vanlige OS-kilder beholdes, både `.list` og deb822 `.sources` støttes, og kildene i
`/etc/apt` endres ikke. PGDG-nøkkelens fastsatte fingeravtrykk og APTs signatur-
kontroller beholdes. Uavklarte blandede URI-er gir stopp. Installerens private
kataloger kan gjenbrukes etter avbruddet, og begge utstrømmer lagres i
`pg18-install.log`. Ved ny feil forsøker Windows-filen å hente og vise loggen.
Ingen finansielle handlinger gjentas som del av installasjonsrettingen.

## Fortsett etter nettbrudd rett etter fullført forhåndskontroll

Hvis konsollen viste `Completed preflight`, men forbindelsen brøt da resultatet
skulle lastes ned, bruk `FORTSETT-ETTER-FORHANDSKONTROLL.txt` i stedet for å starte
en ny jobb. Kopier hele denne filen inn i samme PowerShell-vindu. Den finner den
eneste avbrutte jobben automatisk; finnes flere, spør den etter jobb-ID-en fra
feilmeldingen. Den bevarer samme lokale og eksterne jobbmappe og samme SSH-nøkkel.

Koden kontrollerer at jobben faktisk bare har en ferdig forhåndskontroll, og at
arkiv-/DRAFT-steg ikke har startet. Den henter det eksisterende resultatet og
fortsetter videre. Den kjører ikke forhåndskontrollen på nytt. Pakkemappe og
sertifikatmappe gjenbrukes fra lagret kontekst eller gjeldende mappe hvis de
nødvendige filene finnes der. Usikker eller mer avansert fjernstatus gir stopp,
ikke automatisk repetisjon av en mulig allerede utført handling.

Overføringer bruker færre SSH-forbindelser og korte pauser mellom forbindelsene.
Bare eksplisitte nettbrudd FØR nøkkelutveksling/innlogging forsøkes på nytt, med
samme identitet og jobb. Autentiseringsfeil, endret vertsnoekkel, applikasjonsfeil
og usikre brudd etter at en operasjon kan ha startet, gjentas ikke automatisk.
Delvise nedlastinger blir ikke godkjente kvitteringer eller overskrevet som om
de var komplette. Ingen oppryddingsadvarsel om en privat arkivnøkkel gis før
steget der en slik midlertidig nøkkel faktisk kan ha blitt lastet opp.

OpenSSH-varselet `client_global_hostkeys_prove_confirm` gjelder serverens forslag
om EKSTRA vertsnoekler etter innlogging. Jobben setter `UpdateHostKeys=no` for
denne forbindelsen, slik at slike forslag ikke automatisk legges til.
`StrictHostKeyChecking=yes` beholdes for jobbens SSH/SCP-forbindelser; eksisterende
known_hosts slettes eller endres ikke av skriptet. Bare en første, ukjent vert
kan vises for personlig fingeravtrykkskontroll før noen fjernjobb starter.
Dette slår ikke av verifikasjonen av den opprinnelig betrodde vertsnoekkelen.
Se [OpenSSH UpdateHostKeys](https://man.openbsd.org/ssh_config#UpdateHostKeys).

Kjøringen bruker Windows OpenSSH og OpenSSL. OpenSSL finnes ofte med Git for
Windows eller PostgreSQL; manglende lokale komponenter rapporteres samlet før
produksjonsarbeidet starter. Windows-PC-en må være på og ha nettverk under jobben.
Programmet ber Windows holde seg våken mens fjernjobben kjører, uten permanent
endring av strøm-/sikkerhetsinnstillinger. Ikke lukk konsollen eller slå av PC-en.

## To nødvendige opplysninger i starten

- Programmet gjenbruker den siste egne SSH-identiteten fra tidligere kjøringer.
  Bare hvis ingen finnes, opprettes en ny. Det avleder korrekt offentlig nøkkel
  fra identiteten og prøver skrivebeskyttet SSH først. Fungerer tilgangen, hoppes
  registreringen over. Ellers vises/kopieres **bare den offentlige SSH-nøkkelen**,
  og Render Account Settings åpnes. Registrer den under **SSH Keys**
  og trykk Enter i PowerShell. Dette er nødvendig fordi Codex API-tilgang ikke
  gir Shell-tilgang. Privat SSH-nøkkel blir på PC-en. Vanlig SSH-vertskontroll
  beholdes; verifiser Render-serverens fingeravtrykk ved første tilkobling.
- Etter samlet forhåndskontroll vises faktiske datakilder. Bekreft kildedekning og
  skriverstans bare hvis alle relevante Render-/gamle/eksterne lagre er inkludert,
  cron er suspendert og ingen manuelle/bakgrunnsjobber skriver. Hold app-faner
  lukket. Godkjenning A er allerede gitt; dette er en attestasjon av faktiske kilder,
  ikke en ny generell vedlikeholdsgodkjenning. Ved ukjente kilder skal du ikke bekrefte.

Deretter går de støttede operasjonene sammenhengende. Reelle feil stopper jobben
med en samlet fasekvittering; ingen feil omgås for å få grønt resultat.

## Hva jobben faktisk gjør

1. Kontrollerer deployet arkiv-/regnskapskode mot kjente kildefingeravtrykk, streng
   PostgreSQL-lagring, ingen valgt NOK-konto, kildeinventar, databaseversjon,
   lokal arbeidsplass og andre åpne transaksjoner. Den kopierer ingen saldo fra
   gamle porteføljer. Kildenes innhold og DB-passord skrives ikke til konsollen.
2. Legger PostgreSQL 18-verktøy i en privat arbeidsmappe på eksisterende web-instans.
   Offisielle, signerte pakkekilder og PGDG-nøkkelfingeravtrykk brukes. Ingen sudo,
   ny betalt Render-instans, produksjonsdatabase eller lagringsutvidelse opprettes.
3. Bruker eksisterende `create_archive` til fullt kryptert snapshot av deklarerte
   databaser og runtime-/config-/rapport-/modellkilder. Ingen gamle handler slettes.
4. Laster ned hele det krypterte arkivet til en ny privat mappe på Windows-PC-en,
   kontrollerer SHA-256 og faktisk dekryptering. Dette er den uavhengige kopien på
   en annen maskin enn Render. Nye modellkjøringer får ikke tilgang til PC-mappen.
   Backupen og PostgreSQL 18.6-gjenopprettingen fra før berøres ikke.
5. Starter en midlertidig PostgreSQL-instans **på web-instansens eksisterende
   arbeidsplass**, med eget datatre og privat Unix-socket, uten offentlig TCP-port.
   Den gjenoppretter til nye `nok_restore_*`-databaser med eksisterende
   `restore_drill`, og kontrollerer faktiske fil-/radfingeravtrykk.
6. Kontrollerer at kildehistorikken fortsatt er uendret, og bruker eksisterende
   `prepare` til tre separate **DRAFT**, uten ruter/aktivering: Paper 100 000,
   Autonomi 500 000 og Superporteføljen 1 000 000 NOK. Alle åpner med null aksjer.
   Kontanter, planlagt åpnings-NAV og null realisert/urealisert resultat avstemmes.
   Bare den nye periodens dokument legges til i produksjonsdatabasen.
7. Kontrollerer igjen at øvrig historikk er uendret, stopper den midlertidige
   restore-serveren, fjerner bare jobbens midlertidige arkivnøkkelkopi fra Render,
   og henter kvitteringene til PC-en. Originale nøkler på PC-en beholdes.

Den nye periodens planlagte start settes til 30 minutter etter klargjøringens
avsluttende kontroll og lagres med eksplisitt UTC-tidssone. Den aktiveres ikke
automatisk når dette tidspunktet passeres. Faktisk startdato/periode må inngå i B.

## Hva dette ikke godkjenner eller utfører

- Ingen konto aktiveres, ingen scheduler gjenopptas og ingen handelsordre utføres.
- Ingen redeploy/omstart av web bestilles. Den lagrede Render-konfigurasjonens
  sertifikatfiler kan derfor avvike fra gamle filer i den løpende instansen;
  operatørjobben bruker det gyldige lokale arkivsertifikatet som er overført sikkert.
- Ingen broker-/FX-kostnader, kandidater, kurser eller historiske handler gjettes.
- Ingen kopiert schedulering i databasen startes. Kilder med bakgrunnsutvidelser
  som pg_cron/timescaledb krever eksplisitt egnet isolasjon og stopper denne jobben.
- Den tidligere delte `operator-key.pem` åpnes eller brukes ikke. Programmet
  signerer ingen grants og ber ikke om godkjenning B på ufullstendig grunnlag.

## Etter kjøringen

Ved suksess ligger `final-result.json` og de faktiske arkiv-/restore-/DRAFT-
kvitteringene i `%LOCALAPPDATA%\AksjeNokOperator\nok-job-...`.
Send bare `final-result.json` som status. Ikke send arkivet, private nøkler eller
hele produksjonskonfigurasjonen. Behold den krypterte PC-kopien og original
arkivnøkkel sikkert; jobbens midlertidige Render-lagring er ikke varig sikkerhetskopi.

`approval_B_ready` blir **false**: det må fortsatt foreligge dokumenterte faktiske
kostnadsforutsetninger, ferdige strategiinnspill, gyldige live pris-/FX-bevis og
eksakte signerte aktiveringsdokumenter. Ingen verdier fylles inn automatisk for å
lage slike dokumenter. På en børsstengt dag er gamle observasjoner ikke ferske bevis.
Disse operatøropplysningene er ikke nye utviklingsoppgaver. En privat operatørnøkkel
som har vært delt i chat, skal erstattes før senere produksjonssignering.

Ved feil bevares delresultater i jobbens egne mapper. Programmet overskriver eller
nullstiller ikke en tidligere periode og gjør ingen automatisk ny start. En
`preparation-attempt.json` er kun et forsøk; bare faktisk bundle/kvittering bekrefter
opprettelsen. STOPPED-filer skal gjennomgås før eventuelt gjenforsøk.

## Verifikasjonsstatus for leveransen

Python-/Bash-syntaks, offisiell PowerShell-parser og avgrensede oppryddings-/
scope-kontroller er kjørt i Codex. Ingen tidligere applikasjonstestpakke er gjentatt.
Full Windows/Render-kjøring er **ikke ende-til-ende-verifisert** av Codex.
Brukerens konsoll viser bestått forhåndskontroll og senere stopp ved APT-kildekonflikt. PostgreSQL 18-installasjon, SSH/SCP, kapasitet, locale/utvidelser og faktiske
produksjonsdata kontrolleres først ved denne operatørkjøringen; et miljøavvik gir
stopp, ikke et fabrikkert bestått-resultat. Produksjonsoppstarten er ikke fullført.

Pakkens ZIP SHA256 (kun kildekode og dokumentasjon): `13151e7527d5f094683f48c98c4a82bfec93668dfdbb8a2ebb33200a6cba4f7a`
