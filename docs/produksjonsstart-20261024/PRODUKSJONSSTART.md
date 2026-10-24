# Aksjeappen – samlet operatørprosedyre for faktisk NOK-start

Dato: 24. oktober 2026, Europe/Oslo. Brukeren bekrefter at PR #167 er merget og
deployet til web og scheduler. Prosedyren gjenbruker denne produksjonsaktiveringen;
den endrer ingen handelsmotor, strategi, læringsmodell eller eksisterende konto.
Codex har ikke produksjonstilgang. Kommandoene nedenfor er derfor ikke kjørt i
Render. Ingen ny testkjøring er utført. Ingen konto er aktivert.

Leveransen består av dette dokumentet, `render_operator.py` (private operatørfiler
og skrivebeskyttede kontroller) og `install_pg18_userland.sh` (valgfri installasjon
av PostgreSQL-klient i privat operatørmappe). Ingen av hjelperne aktiverer en konto.
Ikke legg operatørfiler, arkiver, sertifikatnøkler, konfigurasjon eller rapporter i Git.

## 0. Det som allerede finnes, og hva som må bevises

Windows-backupen fra 24. oktober og gjenopprettingen i PostgreSQL 18.6 beholdes
urørt som ekstra sikkerhetskopi. Den er ikke automatisk et komplett sluttarkiv:
den mangler eventuelt senere DB-endringer, andre databaser og filer på web,
scheduler, arbeidere, gamle disker eller eksterne modell-/rapportlagre.
Aktiveringen krever en `restore-review.json` for akkurat det nye krypterte arkivet.
Ikke lag denne kvitteringen manuelt og ikke gjenbruk en kvittering fra en annen dump.

To personlige godkjenninger kreves: A før vedlikehold/stans og skriving av nye
DRAFT-kontoer; B etter gjennomgang av signerte forespørsler, før hver aktivering.
Lesebasert inventar og lokal nøkkelklargjøring kan gjøres før A. En shell-`export`
endrer bare dette shellet; den stopper aldri eksisterende arbeidere.
Alle Dashboard-endringer i punkt 2–3 omfattes også av A; les dem og klargjør
lokale filer først, men utfør dem først etter personlig vedlikeholdsgodkjenning.
Legg det faktiske sluttarkiv-/aktiveringsvinduet til relevant markedstid, slik
at en helg ikke krever flere dagers skriverstans for å vente på ferske kurser.

## 1. Windows PowerShell – privat mappe, nøkler og SSH

Pakk ut leveransen lokalt. Kjør PowerShell som din vanlige bruker. Velg en mappe
på en BitLocker-beskyttet disk uten OneDrive/Git-synkronisering. `Read-Host` her
etterspør bare stier og offentlig SSH-adresse, aldri passord/private nøkler.

```powershell
$ErrorActionPreference = 'Stop'
$Ops = Read-Host 'Ny privat operatørmappe, for eksempel C:\AksjeNokStart-20261024'
if (Test-Path -LiteralPath $Ops) { throw 'Velg en ny mappe; eksisterende filer overskrives ikke' }
New-Item -ItemType Directory -Path $Ops | Out-Null
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $Ops /inheritance:r /grant:r "${Identity}:(OI)(CI)F"
if ($LASTEXITCODE -ne 0) { throw 'Kunne ikke begrense mappetilgang' }
$Package = Read-Host 'Mappe der denne leveransen er pakket ut'
Copy-Item "$Package\render_operator.py","$Package\install_pg18_userland.sh" -Destination $Ops
$OpenSSL = (Get-Command openssl.exe -ErrorAction SilentlyContinue).Source
if (-not $OpenSSL) { $OpenSSL = 'C:\Program Files\Git\usr\bin\openssl.exe' }
if (-not (Test-Path $OpenSSL)) { throw 'OpenSSL må være installert fra godkjent kilde før nøkkelklargjøring' }
foreach ($Role in @('archive','operator')) {
    & $OpenSSL req -x509 -newkey rsa:4096 -sha256 -nodes -days 3650 `
      -subj "/CN=aksje-app-$Role-production" `
      -keyout "$Ops\$Role-key.pem" -out "$Ops\$Role-certificate.pem"
    if ($LASTEXITCODE -ne 0) { throw "Sertifikatoppretting feilet: $Role" }
}
$OperatorPin = (Get-FileHash "$Ops\operator-certificate.pem" -Algorithm SHA256).Hash.ToLowerInvariant()
$OperatorPin
$RenderSsh = Read-Host 'Web-tjenestens user@host fra Render Dashboard > Connect > SSH'
$RenderSsh | Set-Content "$Ops\render-ssh.txt"
```

Bruk din eksisterende SSH-tilgang. Hvis du bare har Web Shell, opprett en lokal
SSH-nøkkel med `ssh-keygen -t ed25519`, og registrer bare `.pub`-filen under
Render-kontoens SSH Keys. Bekreft serverfingeravtrykket via Render; ikke slå av
vertsverifisering. Kopier aldri privat SSH-nøkkel eller operatørsigneringsnøkkel til Render.
Sertifikatene som ble laget i Codex, tas ikke i bruk; disse nye nøklene forvaltes på PC-en.

Ta en privat sikkerhetskopi av nøklene på kryptert lagring. Arkivnøkkelen må kunne
gjenfinnes uavhengig av Render og PC-en. En tilfeldig mappe på samme PC er ikke en
uavhengig sikkerhetskopi. Operatørnøkkelen skal forbli lokal også under signering.

## 2. Dashboard og begge Render-tjenester – før sluttarkivet

Kontroller i Dashboard at siste **vellykkede** deploy på web og scheduler inkluderer
`5c82354c44f0e33c6a08bf0679e0b4dbf35a24b1`, og at ingen ny deploy venter.
Behold eksisterende database- og runtime-stier. Registrer følgende på både web,
scheduler og eventuelle andre handelsarbeidere, gjennom Dashboard:

| Navn | Verdi |
|---|---|
| APP_ENVIRONMENT | production |
| STORAGE_MODE | postgres |
| ALLOW_LOCAL_STORAGE_FALLBACK | false |
| NOK_DEPLOYMENT_ID | aksje-app-production-nok-v1 |
| NOK_APPROVAL_CERTIFICATE | /etc/secrets/nok-operator.pem |
| NOK_APPROVAL_CERT_SHA256 | `$OperatorPin` fra Windows, nøyaktig 64 heksadesimale tegn |

Opprett Secret File `nok-operator.pem` med **offentlig** operator-certificate.pem
på begge tjenester. Opprett Secret File `nok-archive.pem` med **offentlig**
archive-certificate.pem på web. Nøklene skal ikke være vanlige app-hemmeligheter.
La eventuelle redeployer fullføre før siste inventar/arkiv. Disse innstillingene
oppretter ingen konto eller rute. Ikke sett APP_ENVIRONMENT=test.

Kjør i Web Shell på hver tjeneste med shelltilgang:

```bash
set -euo pipefail
umask 077
test -f scripts/production_restart.py
test "$APP_ENVIRONMENT" = production
test "$NOK_DEPLOYMENT_ID" = aksje-app-production-nok-v1
test "$ALLOW_LOCAL_STORAGE_FALLBACK" = false
python - <<'PY'
import hashlib,os
from pathlib import Path
from services.storage_service import get_storage_service
from services.production_restart import require_backend
require_backend(get_storage_service())
assert hashlib.sha256(Path(os.environ['NOK_APPROVAL_CERTIFICATE']).read_bytes()).hexdigest()==os.environ['NOK_APPROVAL_CERT_SHA256']
print('PostgreSQL uten fallback og sertifikatpin kontrollert. Ingen konto aktivert.')
print('Deploy:',os.getenv('RENDER_GIT_COMMIT','ikke eksponert i shell'))
PY
```

På web opprettes den private arbeidsmappen. Den skal ligge utenfor Git og ALLE
runtime-/arkivkilder. `/tmp` er arbeidsplass, ikke varig eller uavhengig lagring.
Hold samme web-instans gjennom arkivering og aktivering; restart/deploy kan slette /tmp.

```bash
export NOK_WORK=/tmp/aksje-nok-start
mkdir -m 700 "$NOK_WORK"
mkdir -m 700 "$NOK_WORK/archives" "$NOK_WORK/staged"
printf '{"extra_roots":{}}\n' > "$NOK_WORK/bootstrap.json"
python scripts/production_restart.py inventory --config "$NOK_WORK/bootstrap.json" --output "$NOK_WORK/inventory-web-initial.json"
python scripts/production_restart.py account-config --config "$NOK_WORK/bootstrap.json" --output "$NOK_WORK/account-settings.json"
```

Fra Windows overføres bare hjelperne nå:

```powershell
& scp "$Ops\render_operator.py" "$Ops\install_pg18_userland.sh" "${RenderSsh}:/tmp/aksje-nok-start/"
if ($LASTEXITCODE -ne 0) { throw 'Overføring feilet; ikke fortsett' }
```

På web, etter overføringen:

```bash
python "$NOK_WORK/render_operator.py" source-identities --work "$NOK_WORK" --output "$NOK_WORK/source-identities-web.json"
```

For scheduler/andre tjenester: kjør samme `inventory` til en egen privat mappe
utenfor runtime. Last ned dette inventaret via tjenestens SSH-adresse og scp.
Ta med alle faktiske ikke-DB-kilder som ikke allerede finnes på web. Kopier/stage
disse **etter at skriverne er stanset i punkt 4**, med kontrollsummer som viser
identiske kildefiler og overførte filer. Ikke erstatt binære læringsfiler med JSON.
Registrer hvert tilgjengelig, separat tre under `extra_roots` i bootstrap.json,
for eksempel et kopiert tre under `$NOK_WORK/staged/scheduler` med kildenavn
`scheduler_files`. Bruk JSON-editor lokalt eller `python -m json.tool` til gjennomgang.
Et arkiv må ikke inneholde operatørmappen eller sine egne arkivfiler.

Kjør også `source-identities` på hver annen tjeneste etter at hjelperen og en
bootstrap.json er overført dit. Sammenlign DATABASE_URL-fingeravtrykkene privat:
web og scheduler som skal bruke samme nye kontoer må peke på samme database.
Samme variabelnavn er ikke bevis på samme database. Separat auth/andre reelle
kildedatabaser skal også med. Legg eventuelle ekstra forbindelser som private
miljøvariabler på web, og deklarer bare variabelnavn i bootstrap.json, f.eks.
`"extra_database_environment_variables":{"scheduler_extra":"NOK_SOURCE_SCHEDULER_URL"}`.
Da krever configure også et nytt mål i `NOK_RESTORE_NOK_SOURCE_SCHEDULER_URL`.
Ingen DSN-er skal inn i JSON-dokumenter, kommandohistorikk eller chat.

Ferdige stagingkommandoer for en separat tjeneste med SSH. Opprett i dens Shell:

```bash
umask 077
mkdir -m 700 /tmp/aksje-nok-stage
printf '{"extra_roots":{}}\n' > /tmp/aksje-nok-stage/bootstrap.json
```

Windows PowerShell:

```powershell
$OtherSsh = Read-Host 'Den andre tjenestens user@host fra Render Connect > SSH'
& scp "$Ops\render_operator.py" "${OtherSsh}:/tmp/aksje-nok-stage/render_operator.py"
if ($LASTEXITCODE -ne 0) { throw 'Hjelperoverføring feilet' }
```

Kjør etter A og skriverstans:

```bash
# I den andre tjenestens Shell, fra dens repositoryrot:
export NOK_WORK=/tmp/aksje-nok-stage
umask 077
python scripts/production_restart.py inventory --config "$NOK_WORK/bootstrap.json" --output "$NOK_WORK/inventory.json"
python "$NOK_WORK/render_operator.py" source-identities --work "$NOK_WORK" --output "$NOK_WORK/source-identities.json"
python "$NOK_WORK/render_operator.py" stage-pack --work "$NOK_WORK" --input "$NOK_WORK/inventory.json" --output "$NOK_WORK/scheduler-files.tar.gz"
```

Windows PowerShell:

```powershell
foreach ($Name in @('scheduler-files.tar.gz','scheduler-files.tar.gz.sources.json','inventory.json','source-identities.json')) {
    $Destination = Join-Path $Ops "scheduler-$Name"
    & scp "${OtherSsh}:/tmp/aksje-nok-stage/$Name" $Destination
    if ($LASTEXITCODE -ne 0) { throw "Stagingoverføring feilet: $Name" }
}
& scp "$Ops\scheduler-scheduler-files.tar.gz" "${RenderSsh}:/tmp/aksje-nok-start/scheduler-files.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Stagingopplasting feilet' }
& scp "$Ops\scheduler-scheduler-files.tar.gz.sources.json" "${RenderSsh}:/tmp/aksje-nok-start/scheduler-files.tar.gz.sources.json"
if ($LASTEXITCODE -ne 0) { throw 'Stagingbevis kunne ikke lastes opp' }
```

På web:

```bash
export NOK_WORK=/tmp/aksje-nok-start
python "$NOK_WORK/render_operator.py" stage-unpack --work "$NOK_WORK" --input "$NOK_WORK/scheduler-files.tar.gz" --label scheduler
```

Dette verifiserer overføringen og legger scheduler_files til bootstrap.json.
Pakken inneholder private, ukrypterte arbeidskopier; oppbevar den bare i de
tilgangsbegrensede arbeidsmappene, overfør kun over SSH, og inkluder de verifiserte
filene i sluttarkivet. Ikke publiser/del stagingpakken. For flere tjenester brukes
egne filnavn/etiketter; aldri overskriv en tidligere stagingkopi.

Cron-instansen kan ha flyktig filsystem og ingen tilgjengelig Shell/SSH mellom
jobber. Hvis nødvendige filer bare finnes der og ikke kan hentes, er dekningen
ikke bekreftet: ikke sett coverage_confirmed. En tidligere tapt fil kan ikke
gjenskapes av en databasebackup. Registrer faktiske fravær før godkjenning.

## 3. PostgreSQL-klient og nye restore-databaser

Kjør på web før vedlikeholdsvinduet:

```bash
python - <<'PY'
import os,psycopg2
for name in ('DATABASE_URL','AUTH_DATABASE_URL','POSTGRES_URL','RENDER_DATABASE_URL'):
    if os.getenv(name):
        connection=psycopg2.connect(os.environ[name],connect_timeout=10)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SHOW server_version');print(name,'serverversjon',cursor.fetchone()[0])
        finally:connection.close()
PY
command -v pg_dump || true
command -v pg_restore || true
```

Bruk klient 18 for server <=18. En eldre klient kan ikke dumpe nyere server.
Hvis pg_dump/pg_restore mangler, gir denne avgrensede brukerinstallasjonen
klient og biblioteker i operatørmappen; systempakker og appkode endres ikke:

```bash
bash "$NOK_WORK/install_pg18_userland.sh"
source "$NOK_WORK/pg18-tools/use.sh"
pg_dump --version
pg_restore --version
```

Installeringsskriptet bruker signerte pakkekilder og verifiserer PGDG-nøkkelens
fingeravtrykk. Det er ikke kjørt på din Render-instans av Codex. Ukjent plattform,
blokkerte pakkekilder, manglende biblioteker eller feil versjon skal stoppe før
produksjonens skrivere stanses. Ingen usignert/nedgradert reserveinstallasjon.

For hver faktisk konfigurert kildevariabel opprettes en **ny, tom og separat**
Render PostgreSQL-database i Dashboard, med databasenavn som starter med
`nok_restore_`. Legg dens interne URL inn som en privat miljøvariabel på web:

| Eksisterende kilde | Variabel for NYTT restore-mål |
|---|---|
| DATABASE_URL | NOK_RESTORE_DATABASE_URL |
| AUTH_DATABASE_URL, hvis satt | NOK_RESTORE_AUTH_DATABASE_URL |
| POSTGRES_URL, hvis satt | NOK_RESTORE_POSTGRES_URL |
| RENDER_DATABASE_URL, hvis satt | NOK_RESTORE_RENDER_DATABASE_URL |

Verktøyet krever ett eget tomt mål per oppdaget kildealias, også hvis to aliaser
peker på samme kilde. Det er lov å kontrollere aliasene, men ikke skjule et
oppdaget alias for å omgå arkivkravet. Ikke bruk den allerede gjenopprettede
Windows-databasen som tomt mål. Ingen aktiv DATABASE_URL/AUTH_DATABASE_URL endres.
La eventuell redeploy etter disse miljøendringene fullføre før neste punkt.
Hvis /tmp ble slettet, opprett arbeidsmappen og overfør hjelperne på nytt;
bruk nye inventarfiler. Ikke anta at data overlever en redeploy.

## 4. Godkjenningspunkt A – vedlikehold, sluttarkiv og nye utkast

**Personlig godkjenning kreves nå:** stans av relevante tjenester/skrivere,
sluttarkiv og opprettelse av tre separate DRAFT-kontoer. Dette er ikke godkjenning
til å aktivere kontoer eller til å slette/nullstille gamle data.

```bash
read -r -p 'Skriv GODKJENN VEDLIKEHOLD ARKIV OG DRAFT for personlig godkjenning A: ' nok_maintenance_approval
test "$nok_maintenance_approval" = 'GODKJENN VEDLIKEHOLD ARKIV OG DRAFT'
```

Dashboard: deaktiver automatisk cronstart/suspender cronplanen med tilgjengelig
Render-kontroll. Vent til pågående jobber er ferdige og gamle ventende jobber er
håndtert. Stans også manuelle skanninger, læringsskrivere, rapportskrivere,
vedlikeholdsjobber og øvrige skrivere. En skrudd av Paper-bryter stanser ikke
Autonomi eller læring. En skrudd av scheduler-bryter stanser ikke alle deler av
scheduled_runner. Ikke kjør scheduled_runner som en kontroll før aktivering.

Hold web-instansen og Shell tilgjengelig, men blokker brukertrafikk/skrivende
UI-operasjoner i vedlikeholdsvinduet og stans dens aktive bakgrunnsarbeidere.
Ikke suspender/slett en instans før flyktige filer er sikret. Alle nødvendige
tiltak forutsetter A. Arkivkommandoens --sources-quiesced er din attestasjon;
den fjernstyrer ikke Render-prosesser. Aktiveringen kontrollerer uendrede kilder.

Stage øvrige tjenesters og eksterne lagres faktiske filer nå, og ferdigstill
bootstrap.json med deres `extra_roots`. Eksterne lagre må være gjennomgått, ikke
bare antatt fraværende. Gjenta sluttinventaret på web:

```bash
export NOK_WORK=/tmp/aksje-nok-start
umask 077
python scripts/production_restart.py inventory --config "$NOK_WORK/bootstrap.json" --output "$NOK_WORK/inventory-final.json"
python -m json.tool "$NOK_WORK/inventory-final.json"
python "$NOK_WORK/render_operator.py" configure --work "$NOK_WORK"
```

configure ber om dokumenterte **NOK-kostnader per utført modellhandel** og
kildereferanse for hver konto. Ingen beløp eller nullkostnader er forhåndsvalgt.
Bruk vedtatte modellforutsetninger, ikke antatte meglerbeløp. Strategiinnstillingene
hentes uendret fra account-settings.json. Hjelperen krever bekreftelse av det
eksakte inventarfingeravtrykket før fullstendighetsflagg kan settes.

Overfør kun arkivnøkkelen midlertidig fra Windows til den private mappen på web:

```powershell
& scp "$Ops\archive-key.pem" "${RenderSsh}:/tmp/aksje-nok-start/archive-key.pem"
if ($LASTEXITCODE -ne 0) { throw 'Nøkkeloverføring feilet' }
```

Render Shell:

```bash
chmod 600 "$NOK_WORK/archive-key.pem"
python scripts/production_restart.py archive --config "$NOK_WORK/config.json" --sources-quiesced --output "$NOK_WORK/archive-receipt.json"
export NOK_ARCHIVE_ID=$(python -c 'import json,os;print(json.load(open(os.environ["NOK_WORK"]+"/archive-receipt.json"))["archive_id"])')
python - <<'PY'
import hashlib,json,os
from pathlib import Path
w=Path(os.environ['NOK_WORK']);a=w/'archives'/os.environ['NOK_ARCHIVE_ID']
r=json.loads((a/'receipt.json').read_text())
h=hashlib.sha256()
with (a/'archive.cms').open('rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
assert h.hexdigest()==r['cipher_sha256']
print('Sluttarkiv:',r['archive_id'],'SHA256:',r['cipher_sha256'])
PY
```

## 5. Uavhengig kryptert kopi på Windows og separat lagring

Windows PowerShell, i samme sesjon som punkt 1:

```powershell
& scp "${RenderSsh}:/tmp/aksje-nok-start/archive-receipt.json" "$Ops\archive-receipt.json"
if ($LASTEXITCODE -ne 0) { throw 'Kvittering kunne ikke hentes' }
$Receipt = Get-Content "$Ops\archive-receipt.json" -Raw | ConvertFrom-Json
$ArchiveId = $Receipt.archive_id
New-Item -ItemType Directory "$Ops\archives" | Out-Null
& scp -r "${RenderSsh}:/tmp/aksje-nok-start/archives/$ArchiveId" "$Ops\archives\"
if ($LASTEXITCODE -ne 0) { throw 'Arkivoverføring feilet' }
$Actual = (Get-FileHash "$Ops\archives\$ArchiveId\archive.cms" -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Receipt.cipher_sha256) { throw 'Arkivets kontrollsum stemmer ikke' }
$IndependentRoot = Read-Host 'Ny mappe på separat kryptert og frakoblingsbar sikkerhetskopilagring'
if (Test-Path $IndependentRoot) { throw 'Velg en ny mappe; ingen overskriving' }
New-Item -ItemType Directory $IndependentRoot | Out-Null
Copy-Item "$Ops\archives\$ArchiveId" -Destination $IndependentRoot -Recurse
$Second = (Get-FileHash "$IndependentRoot\$ArchiveId\archive.cms" -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Second -ne $Receipt.cipher_sha256) { throw 'Uavhengig kopi kunne ikke verifiseres' }
# Verifiser faktisk dekryptering på PC-en uten å pakke ut produksjonsdata:
& $OpenSSL cms -decrypt -binary -inform DER -in "$IndependentRoot\$ArchiveId\archive.cms" `
  -recip "$Ops\archive-certificate.pem" -inkey "$Ops\archive-key.pem" -out NUL
if ($LASTEXITCODE -ne 0) { throw 'Lokal lesbarhets-/nøkkelkontroll feilet' }
Write-Host 'Begge kopier har korrekt SHA256, og den uavhengige kopien kan dekrypteres.'
```

Gjør den uavhengige kopien frakoblet/skrivebeskyttet etter kontroll; Render og nye
modellkjøringer skal ikke ha skrivetilgang. Oppbevar en separat sikker nøkkelkopi.
Render-/Windows-arbeidsmapper alene er ikke denne uavhengige kopien.

## 6. Fysisk gjenoppretting av akkurat sluttarkivet

Render Shell, fortsatt med alle skrivere stanset:

```bash
python scripts/production_restart.py restore --config "$NOK_WORK/config.json" --archive-id "$NOK_ARCHIVE_ID" --private-key-file "$NOK_WORK/archive-key.pem" --output "$NOK_WORK/restore-result.json"
python - <<'PY'
import json,os
from pathlib import Path
from services.simulation_archive import verify_restore_destination
w=Path(os.environ['NOK_WORK']);review=json.loads((w/'restore/restore-review.json').read_text())
verify_restore_destination(w/'restore',review)
assert review['status']=='RESTORED_AND_VERIFIED'
print('Restore bestått:',review['archive']['archive_id'],'review_sha256:',review['review_sha256'])
PY
```

Her gjenopprettes både filer og ALLE arkiverte databaser til de nye tomme målene.
Kvitteringen inneholder faktiske radfingeravtrykk fra arkivsnapshotet. Ingen
--clean, DROP eller overskriving av aktive mål brukes. Ikke bruk restore-databasene
eller gjenopprettede filer til andre jobber etter denne kontrollen. Feil betyr stopp.

Last også ned kvitteringen og resultatet til Windows:

```powershell
& scp "${RenderSsh}:/tmp/aksje-nok-start/restore-result.json" "$Ops\restore-result.json"
if ($LASTEXITCODE -ne 0) { throw 'Restore-resultat kunne ikke hentes' }
& scp "${RenderSsh}:/tmp/aksje-nok-start/restore/restore-review.json" "$Ops\restore-review.json"
if ($LASTEXITCODE -ne 0) { throw 'Restore-bevis kunne ikke hentes' }
```

## 7. Nye DRAFT-kontoer – ingen aktivering

Velg en ny periode-ID og T0 med tidssone. T0 må ligge etter arkivkontrollen;
prepare kan ikke brukes til å tilbakedatere åpningen. Velg et vindu med faktisk
tilgjengelige ferske aksje- og valutakurser. 24. oktober er lørdag; helgekurser
skal ikke merkes ferske. Kontroller børsenes faktiske kalender/markedstid.

```bash
python - <<'PY'
from datetime import datetime,timezone
from pathlib import Path
import json,os,re
w=Path(os.environ['NOK_WORK'])
period=input('Ny periode-ID (bokstaver/tall/underscore/bindestrek): ').strip()
assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',period)
start=input('T0 med tidssone, ISO 8601: ').strip()
assert datetime.fromisoformat(start)>datetime.now(timezone.utc)
actor=input('Operatørnavn: ').strip();ref=input('Godkjenningsreferanse: ').strip()
assert actor and ref
with (w/'launch.json').open('x') as f:json.dump(dict(period_id=period,start_at=start,actor=actor,approval_ref=ref),f)
PY
export NOK_PERIOD=$(python -c 'import json,os;print(json.load(open(os.environ["NOK_WORK"]+"/launch.json"))["period_id"])')
export NOK_START=$(python -c 'import json,os;print(json.load(open(os.environ["NOK_WORK"]+"/launch.json"))["start_at"])')
export NOK_ACTOR=$(python -c 'import json,os;print(json.load(open(os.environ["NOK_WORK"]+"/launch.json"))["actor"])')
python scripts/production_restart.py prepare --config "$NOK_WORK/config.json" --archive-id "$NOK_ARCHIVE_ID" --period "$NOK_PERIOD" --start-at "$NOK_START" --actor "$NOK_ACTOR" --private-key-file "$NOK_WORK/archive-key.pem" --output "$NOK_WORK/prepared.json"
```

Denne kommandoen skriver kun et separat nytt DRAFT-bundle. Det inneholder Paper
100 000, Autonomi 500 000 og Superporteføljen 1 000 000 NOK, alle uten aksjer.
Gamle posisjoner, tap og læring er bevart; ingen salg konstrueres. Superfond berøres ikke.
Ved avbrudd: les prepared.json/status før du gjør noe nytt; ikke slett bundle/ruter.

## 8. Ferske leverandørbevis og tørrkjøring, uten ordre

Vent til T0 er nådd og relevante markeder leverer ferske data. Hold alle andre
skrivere stanset. Gamle ferdiglagrede beslutningsinnspill kan kontrolleres som
historiske input, men dokumenterer ikke aktuelle kandidatbeslutninger.

Eksporter **eksakte ferdige input** fra gjennomgåtte lagrede kilder. Hjelperen
kan hente et faktisk JSON-dokument/JSON-pointer fra app_kv_store uten å transformere
innholdet. Den lager også kildefingeravtrykk. Kommandoen ber deg velge faktisk
lagret kilde; ikke skriv en antatt nøkkel hvis den ikke finnes.

```bash
python "$NOK_WORK/render_operator.py" catalog --work "$NOK_WORK" --output "$NOK_WORK/input-catalog.json"
python -m json.tool "$NOK_WORK/input-catalog.json"
for family in paper autonomy super_portfolio; do
  read -r -p "Eksakt gjennomgått kildekey for $family: " source_key
  read -r -p 'JSON-pointer til ferdig input (tom for hele dokumentet): ' source_pointer
  python "$NOK_WORK/render_operator.py" export-json --work "$NOK_WORK" --key "$source_key" --pointer "$source_pointer" --output "$NOK_WORK/$family-input.json"
done
```

Riktig innhold:
- Paper: liste med faktiske AUTO-signaler, confidence og original trade_context,
  inkludert ekte entry_confirmation der det foreligger. Rå candidate_snapshots
  alene er ikke ferdige ordreinndata; ikke legg til et oppdiktet bekreftelsessignal.
- Autonomi: liste over ferdig berikede kandidater, med eksisterende teknisk
  strategibidrag fra samme snapshot. En rå markedskandidat er ikke en slik liste.
- Superporteføljen: komplett markedspipeline med original run_id og candidates.
  `super_portfolio/market_pipeline.json` er en kjent kildetype, men må faktisk
  finnes og gjennomgås; ikke bruk en tilfeldig global pipeline som erstatning.

Hvis de nødvendige ferdige inputene ikke er lagret, skal dekningen merkes
IKKE VERIFISERT. Ikke kjør en ordinær handelsmotor før aktivering for å skaffe
dem; den kan bruke gamle kontoer. Ikke gjett transformasjoner. Det er en faktisk
operatørkontroll av tilgjengelige produksjonsdata, ikke tillatelse til fiktive input.

Lag leverandørinput med faktiske tickere/valutaer fra gjennomgått kandidatgrunnlag
for hver konto. Valuta må ha en dokumentert kilde. Velg det reelle utvalget du vil
kontrollere; ingen standardsymboler/kostnader legges inn av prosedyren:

```bash
python - <<'PY'
import json,os
from pathlib import Path
w=Path(os.environ['NOK_WORK']);c=json.loads((w/'config.json').read_text())
for family in ('paper','autonomy','super_portfolio'):
    instruments=json.loads(input(f'{family}: JSON-objekt med faktiske ticker:valuta: '))
    assert instruments and all(isinstance(k,str) and len(v)==3 for k,v in instruments.items())
    with (w/(family+'-provider-input.json')).open('x') as f:
        json.dump(dict(instruments=instruments,cost_policy=c['accounts'][family]['cost_policy']),f)
PY
for family in paper autonomy super_portfolio; do
  python scripts/production_restart.py provider-check --config "$NOK_WORK/config.json" --input "$NOK_WORK/$family-provider-input.json" --output "$NOK_WORK/$family-provider-result.json"
  python scripts/production_restart.py dry-run-live --config "$NOK_WORK/config.json" --period "$NOK_PERIOD" --family "$family" --input "$NOK_WORK/$family-input.json" --output "$NOK_WORK/$family-dry-run.json"
done
```

Med `set -e` stopper exitkode 2 ved manglende bevis. Gjennomgå bevis, faktiske
beslutninger/avvisninger, valuta, kostnader og prøveregnskap. Tomme lister eller
bare HOLD er ikke bevis på at alle kjøps-/salgsforløp er live-verifisert. En korrekt
avvisning skal beholdes. Gamle tester fra Codex erstatter ikke denne livekontrollen.
Ikke endre proxy-/sikkerhetsregler for å tvinge Yahoo grønt. Ved feil: stopp uten
aktivering. Ved nytt forsøk brukes nye outputnavn; gamle kvitteringer overskrives ikke.

## 9. Eksakte forespørsler og signering på Windows

Render Shell, etter gjennomgått restore og tørrkjøring:

```bash
python "$NOK_WORK/render_operator.py" requests --work "$NOK_WORK"
```

Hent forespørsler og kanoniske bytes til en ny mappe på Windows:

```powershell
$Review = Join-Path $Ops 'approval-review'
New-Item -ItemType Directory $Review | Out-Null
& scp "${RenderSsh}:/tmp/aksje-nok-start/approval-summary.json" "$Review\approval-summary.json"
if ($LASTEXITCODE -ne 0) { throw 'Kunne ikke hente godkjenningsgrunnlag' }
& scp -r "${RenderSsh}:/tmp/aksje-nok-start/canonical" "$Review\"
if ($LASTEXITCODE -ne 0) { throw 'Kunne ikke hente kanoniske forespørsler' }
foreach ($Family in @('paper','autonomy','super_portfolio')) {
    & scp "${RenderSsh}:/tmp/aksje-nok-start/$Family-request.json" "$Review\$Family-request.json"
    if ($LASTEXITCODE -ne 0) { throw "Kunne ikke hente forespørsel: $Family" }
}
$Summary = Get-Content "$Review\approval-summary.json" -Raw | ConvertFrom-Json
$Summary | Format-List
```

Gjennomgå hele *-request.json lokalt: produksjonsmiljø/installasjon, konto,
kapital, periode/starttid, operatør/referanse, opening_sha256, arkiv-ID og
kontrollsummer, restore_review, uendrede strategiinnstillinger og modellkostnader.
Signering nedenfor lager et dokument; den aktiverer ingen konto. Alle signerte
grants skal presenteres sammen med den eksakte sammendragsfilen før B.

```powershell
foreach ($Item in $Summary) {
    $Family = $Item.family
    $Canonical = "$Review\canonical\$Family.bin"
    $Hash = (Get-FileHash $Canonical -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Hash -ne $Item.request_sha256) { throw "Feil request-hash: $Family" }
    # Sammenlign også JSON-innholdet i kanonisk og lesbar forespørsel før signering.
    $Utf8 = [System.Text.UTF8Encoding]::new($false)
    $CanonicalText = [System.IO.File]::ReadAllText($Canonical,$Utf8)
    # Signer nøyaktig de kanoniske bytes; ikke reserialiser med PowerShell.
    & $OpenSSL dgst -sha256 -sign "$Ops\operator-key.pem" -out "$Review\$Family.sig" $Canonical
    if ($LASTEXITCODE -ne 0) { throw "Signering feilet: $Family" }
    $Signature = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes("$Review\$Family.sig"))
    $Grant = '{"payload":' + $CanonicalText + ',"signature":"' + $Signature + '"}'
    $GrantPath = "$Review\$Family-grant.json"
    if (Test-Path $GrantPath) { throw 'Eksisterende signert grant skal ikke overskrives' }
    [System.IO.File]::WriteAllText($GrantPath,$Grant,$Utf8)
    Write-Host "SIGNERT, IKKE AKTIVERT: $Family / $($Item.capital_nok) NOK / $($Item.period_id) / $Hash"
}
```

Det er de kanoniske payloadene i *-grant.json som er den eksakte signerte
godkjenningen. *-request.json er en lesbar kopi. `approval-summary.json` er
gjennomgangsoversikten, ikke en alternativ godkjenning.
Ingen privat signeringsnøkkel overføres. Hent/oppbevar også live- og restore-resultatene
privat ved siden av godkjenningen. Ikke publiser disse filene i GitHub/chat.
Hvis kurs-/valutabevis er blitt for gamle under gjennomgangen, gjenta provider-check
og dry-run-live med nye outputnavn i gyldig markedstid før aktivering. Ikke endre
observasjonstidspunkter. Lesing alene krever ikke nytt arkiv hvis kildene ellers
fortsatt er uendret; endrede kilde-/strategidata krever ny kontroll/godkjenning.

## 10. Godkjenningspunkt B – personlig kontoaktivering

**STOPP HER inntil du personlig har godkjent de faktiske signerte dokumentene.**
Det finnes ennå ingen ekte hash å forhåndsgodkjenne i dette dokumentet. En
generell «fortsett» erstatter ikke kontroll av riktig konto, beløp, periode og hash.
Ikke kjør noen av blokkene videre før B. Hvis noe innhold endres, kreves ny request,
ny signatur og ny gjennomgang; gamle kvitteringer skal bevares.

Etter B overføres bare de tre signerte grants fra Windows:

```powershell
foreach ($Family in @('paper','autonomy','super_portfolio')) {
    & scp "$Review\$Family-grant.json" "${RenderSsh}:/tmp/aksje-nok-start/$Family-grant.json"
    if ($LASTEXITCODE -ne 0) { throw "Grant-overføring feilet: $Family" }
}
```

Render Shell. Denne blokken **aktiverer kontoer**, én om gangen, først etter at
du skriver den eksakte bekreftelsen for aktuell konto. Alle andre skrivere forblir
stanset helt til alle tre er aktivert og åpningen kontrollert.

```bash
python - <<'PY'
import json,os,subprocess,sys
from pathlib import Path
from services.economic_opening import digest
from services.production_restart import verify_grant
w=Path(os.environ['NOK_WORK'])
summary=json.loads((w/'approval-summary.json').read_text())
for item in summary:
    family=item['family'];grant=json.loads((w/(family+'-grant.json')).read_text())
    payload=verify_grant(grant);sha=digest(payload)
    assert sha==item['request_sha256'] and payload['family']==family
    assert payload['period_id']==item['period_id'] and payload['capital_nok']==item['capital_nok']
    expected=f'AKTIVER {family} {item["capital_nok"]:g} NOK {item["period_id"]} {sha}'
    print('Godkjenningen gjelder:',payload['environment'],payload['deployment_id'],payload['start_at'])
    print('Skriv nøyaktig etter personlig gjennomgang:',expected)
    assert input('> ')==expected, 'Ingen aktivering uten eksakt personlig bekreftelse'
    subprocess.run([sys.executable,'scripts/production_restart.py','activate','--config',str(w/'config.json'),
        '--input',str(w/(family+'-grant.json')),'--confirmation',sha,'--private-key-file',str(w/'archive-key.pem'),
        '--output',str(w/(family+'-activation.json'))],check=True)
PY
python "$NOK_WORK/render_operator.py" check-opening --work "$NOK_WORK" --output "$NOK_WORK/opening-verified.json"
```

Ved delvis feil: behold skriverstansen. Ikke nullstill eller aktiver en annen
periode som omgåelse. Samme grant kan gjenleveres ved dokumentert avbrudd, med
nytt outputnavn; CLI-ruten er create-only og erstatter ikke en eksisterende rute.
Ved endret kildegrunnlag må nytt sluttarkiv/restore/godkjenning gjennomføres.

Forventet før første jobb:

| Konto | Kontanter/NAV | Posisjoner | Realisert/urealisert resultat |
|---|---:|---:|---:|
| Paper | 100 000 NOK | 0 | 0/0 NOK |
| Autonomi | 500 000 NOK | 0 | 0/0 NOK |
| Superporteføljen | 1 000 000 NOK | 0 | 0/0 NOK |

## 11. Kontrollert schedulerstart og første faktiske jobbkvittering

Før start kjøres på **både web og scheduler**, med deres egen prod-miljøkonfigurasjon:

```bash
python - <<'PY'
from services.production_restart import selected
from services.storage_service import get_storage_service
from services.production_restart import require_backend
s=get_storage_service();require_backend(s)
for family in ('paper','autonomy','super_portfolio'):
    chosen=selected(family,storage=s)
    assert chosen is not None
    print(family,chosen['pointer']['period_id'],chosen['approval']['capital_nok'],chosen['bundle']['production_controls'][family]['status'])
PY
```

Alle prosesser må vise **samme nye periode**, installasjon og forventet kapital.
Ingen manglende rute er godkjent. Kontrollene kjører ingen handelsmotor.

Sikre operatørkonteksten på Windows **før** noen gjenopptakelse som kan gi redeploy:

```powershell
$Context = Join-Path $Ops 'context-before-start'
New-Item -ItemType Directory $Context | Out-Null
$ContextFiles = @('config.json','launch.json','prepared.json','approval-summary.json','opening-verified.json','render_operator.py')
foreach ($Family in @('paper','autonomy','super_portfolio')) {
    $ContextFiles += "$Family-activation.json","$Family-provider-result.json","$Family-dry-run.json"
}
foreach ($Name in $ContextFiles) {
    & scp "${RenderSsh}:/tmp/aksje-nok-start/$Name" "$Context\$Name"
    if ($LASTEXITCODE -ne 0) { throw "Operatørkontekst kunne ikke sikres: $Name" }
}
```

Disse private filene inneholder ikke tilkoblingspassord eller signeringsnøkler,
men skal fortsatt behandles som private produksjonsopplysninger.

Gjenoppta webtrafikk og ordinære bakgrunns-/schedulerinnstillinger først nå.
Behold strategienes eksisterende parametere og tidsplan. På scheduler skal de
ordinære verdiene inkludere REPORT_SCHEDULER_ENABLED=true og PAPER_TRADING_ENABLED=true.
Hold webens separate report/background scheduler av hvis arkitekturen bruker
cron som autoritativ scheduler. Unngå en samtidig cronstart og manuell engangsstart.
Render-innstillingsendringer kan gi redeploy; gjenopprett da private operatørfiler
fra den kontrollerte PC-kopien hvis /tmp blir borte. Ikke kopier over en eksisterende mappe.

Hvis og bare hvis arbeidsmappen er borte: opprett den på nytt med 0700 i Web Shell,
og last opp config.json, launch.json og render_operator.py fra `$Context` med scp.
Det er nok for de skrivebeskyttede saldo-/jobbkontrollene og eksplisitt STOP;
det er **ikke** nok til en ny aktivering/restore. Gjenta ingen activate-kommando.

Dashboard: start **én** ordinær schedulerjobb med Run Job/Trigger Run før cronplanen
gjenopptas. Bruk eksisterende startkommando `python scheduled_runner.py`.
Ikke kjør eksport-/tørrkjøringsinput som fabrikkert første handelsjobb.
En jobbutgang med kode 0 alene er ikke bevis på at alle tre kontoer fikk en syklus.

Etter faktisk relevant syklus for alle tre, kjør på web:

```bash
python "$NOK_WORK/render_operator.py" check-jobs --work "$NOK_WORK" --output "$NOK_WORK/first-jobs-verified.json"
```

Kontrollen krever STRATEGY_RUN i riktig perioderegnskap for hver konto og verifisert
NAV. Den lagrer faktisk første run_id, tidspunkt, beslutninger og regnskapsrapport.
Et gyldig NO_TRADE/HOLD kan være riktig strategibeslutning. Det skal ikke erstattes
med et tvangskjøp. Hvis en konto ikke er due, vent på dens ordinære planlagte syklus;
ikke endre strategiens plan eller kandidatfiltre for å få en kvittering.

Kontroller deretter manuelt på PC og mobil: riktig periode og startkapital,
kontanter/posisjoner/NAV, graf, realisert/urealisert resultat, gebyrer, historikkskille,
CSV/XLSX/PDF/ZIP og navigation. Åpne gammel historikk og kontroller bevarte tap.
Superfond skal fortsatt vise sin eksisterende native konto og historikk.
Start normal cronplan etter at første kontrollerte jobb er vurdert.

Last ned private config/launch/prepared/approval/live/activation/opening/first-job-
kvitteringer til den beskyttede PC-mappen og sikkerhetskopier dem. Fjern deretter
**bare den midlertidige kopien** av archive-key.pem fra Render, etter bekreftet
lokal nøkkelbackup. Behold offentlige sertifikater i web/scheduler og behold arkivene.
En `/tmp`-sletting er ikke en garanti for kryptografisk sikker sletting; nøkkelen
skal ikke ha vært skrevet til applikasjonslogger, Git eller vanlige runtime-trær.

## 12. Stopp ved avvik, uten tap av økonomisk historikk

Ved avvik etter aktivering: stans ny schedulerstart og aktive skrivere, og stopp
de valgte NOK-kontoene eksplisitt. Dette krever operatørens personlige beslutning;
STOP nullstiller ikke konto eller journal og gir ingen gammel saldo som reserve.

```bash
python - <<'PY'
import json,os,subprocess,sys
from pathlib import Path
from services.economic_opening import digest
w=Path(os.environ['NOK_WORK']);launch=json.loads((w/'launch.json').read_text())
reason=input('Dokumentert begrunnelse for STOP: ').strip();assert reason
assert input('Skriv STOPP ALLE NOK-KONTOER: ')=='STOPP ALLE NOK-KONTOER'
from services.production_restart import selected
for family in ('paper','autonomy','super_portfolio'):
    if selected(family,require_running=False) is None:continue
    action=dict(period_id=launch['period_id'],family=family,action='STOP',deployment_id=os.environ['NOK_DEPLOYMENT_ID'])
    subprocess.run([sys.executable,'scripts/production_restart.py','stop','--config',str(w/'config.json'),
        '--period',launch['period_id'],'--family',family,'--actor',launch['actor'],'--reason',reason,
        '--confirmation',digest(action),'--output',str(w/(family+'-stop.json'))],check=True)
PY
```

Ved gjenoppretting etter oppstart brukes en kontrollert **etter-start-backup** til
nye tomme mål; ikke sluttarkivet før start som om nye handler ikke hadde skjedd.
Ikke bytt tilbake til gammel binær/legacy-saldo med handel aktiv. Behold original
DB, runtime og begge arkivkopier. RESUME krever ny personlig beslutning etter kontroll.

## Faktisk sluttstatus som kan fylles ut etter operasjonen

Registrer: deploy-IDer; inventarhash og kildeoversikt per tjeneste; arkiv-ID og
cipher_sha256; uavhengig kopis plassering/lesbarhet; restore review_sha256;
periode/T0; faktisk modellkostnadspolicy; leverandør-/tørrkjøringsresultater;
de tre request-hashene og signerte grants; personlig B-bekreftelse per konto;
aktiveringskvitteringer; åpningens kontanter/NAV; første jobbkvittering per konto;
PC/mobil-/Superfond-kontroll og schedulerstatus. Manglende felt er ikke BESTÅTT.

Per denne leveransen er kun kode/deploy bekreftet av bruker, og den eldre
Windows-gjenopprettingen opplyst av bruker. Produksjonsoperasjonene over gjenstår
å utføre av operatøren. Ingen ny utviklingsrevisjon eller gjentakelse av gamle tester
er nødvendiggjort eller utført av denne prosedyren.
