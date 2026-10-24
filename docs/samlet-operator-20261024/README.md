# KJØRING SPERRET – produksjonens arkivkontroll må ikke gjentas

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

## Eneste nye kjøreinstruks: skrivebeskyttet lokal kopikontroll

Bruk [KONTROLLER-LOKAL-KOPI-WINDOWS.txt](KONTROLLER-LOKAL-KOPI-WINDOWS.txt) på
Windows-PC-en. Kopier hele filen inn i PowerShell og trykk Enter. Den bruker
`127.0.0.1:5432`, bruker `postgres` og den eksplisitte kopien `aksje_restore_test`.
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

Pakkens ZIP SHA256 (kun kildekode og dokumentasjon): `3f8a8b19351a85984b343270585884bdb55ad505aac6b9c061c30dc33df07bb4`
