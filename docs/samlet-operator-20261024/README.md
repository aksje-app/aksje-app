[Last ned hele ZIP-pakken](aksje-samlet-operator.zip) (velg Download raw file i GitHub).

Hvis `Completed preflight` allerede er vist og neste overføring feilet, kopier hele [fortsettelsesfilen](FORTSETT-ETTER-FORHANDSKONTROLL.txt) inn i samme PowerShell-vindu. Den gjenbruker eksisterende jobb, nøkkel og resultat; de tidligere utpakkede Python-/installasjonsfilene er uendret. Ikke start en ny jobb for dette nettbruddet.

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
Windows/Render-kjøringen er **ikke gjennomført eller ende-til-ende-verifisert** av
Codex. PostgreSQL 18-installasjon, SSH/SCP, kapasitet, locale/utvidelser og faktiske
produksjonsdata kontrolleres først ved denne operatørkjøringen; et miljøavvik gir
stopp, ikke et fabrikkert bestått-resultat. Produksjonsoppstarten er ikke fullført.

ZIP SHA256: `ba07df0ea7d3ed6c03de33d4476a84a837c27b7c1d31e84c1afd837616d9f6e1`
