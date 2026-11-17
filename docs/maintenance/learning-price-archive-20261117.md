# Kontrollert arkivering av historisk prisgrunnlag

Denne rutinen gjelder bare de 1 344 prisfilene i `services/learning_price_archive_20261117.json`. Begge motorenes resultater, fremdrift, observasjoner, forward-kontoer, finansielle journaler og karanteneoriginaler beholdes. Nye læringer eller andre data blir ikke automatisk slettbare.

## Gjenopprettingsgrunnlag

Fullkopien `2026-11-17T16_06Z.dir.tar.gz` er 888 151 608 byte, SHA-256 `bcde2be937aa8317a9f26234de01df872acd2bfe3e42567a95de41ed6d495309`. Brukeren har lagret den på PC-en og beregnet samme kontrollsum. Kopien er lastet ned uavhengig og gjenopprettet med PostgreSQL 18.6: alle 12 tabeller og 1 283 088 rader er kontrollert mot eksporten med sorterte SHA-256 per COPY-rad, med duplikater bevart. Fullkopien må beholdes; den selektive ZIP-en er ikke nødvendig for denne rutinen.

Autorisasjonsfilen inneholder bare nøkler og kontrollsummer. Ingen priser, tilkoblingsstrenger, signerte nedlastingslenker eller private nøkler er lagt i Git. Produksjonsleseren kontrollerer filens fastsatte SHA-256 før den brukes.

## Hva en arkivpulje gjør

Funksjonen er avslått som standard. Når `LEARNING_PRICE_ARCHIVE_20261117_ENABLED=true` er satt på scheduler-tjenesten, forsøker ordinær cron ett begrenset pass etter dagens vedlikehold. Maksimalt 128 nøkler behandles per pass; SQL har 30 sekunders statement-timeout og to sekunders låsetimeout. Det kreves en egen arkivlås.

Samme transaksjon låser fremdriftskontrollene, kildeprisene og begge resultatene. En pris må fortsatt ha opprinnelig byteantall og SHA-256. Tickerens nøkkel må finnes i både innsamlings- og optimaliseringens ferdigliste. Begge resultater må ha den eksakte autoriserte hashen, gjeldende metode og `COMPLETE_RESEARCH`. Et endret eller manglende grunnlag beholdes og registreres som sperret.

Den store prisverdien erstattes med en liten arkivreferanse under samme nøkkel. Referansen angir originalhash, størrelse, arkivfil, arkivhash, metode og autorisasjon. Fremdriftskvitteringen `maintenance/learning_price_archive_20261117.json` skrives i samme transaksjon. Feil ruller tilbake både erstatninger og fremdrift. En korrupt eller overstor kvittering stopper prosessen; den tolkes ikke som en ny tillatelse.

Et fullført pass er engangsbehandling av den eksakte autorisasjonen. Senere gjenopprettede filer blir ikke automatisk arkivert på nytt. Kvitteringens totaltall er historiske hendelser, ikke en løpende telling av kalde filer etter en eventuell gjenoppretting.

## Lesere og gjenoppretting

Vanlig historisk optimalisering fortsetter for ubehandlede aksjer. En ny beregning som trenger en arkivert prisfil får `WAITING_ARCHIVE`. Aksjen markeres ikke som avvist eller som utilstrekkelig historikk, og gamle resultater overskrives ikke. Innsamlingsjobben stopper før ny nedlasting og kan ikke overskrive en arkivreferanse med en ny historikk.

PC-mappen er et manuelt arkiv. Render kan ikke lese direkte fra den. Ved behov gjenopprettes den opprinnelige fullkopien i en separat, isolert PostgreSQL 18-database, aldri over produksjonsdatabasen. Bruk det eksisterende `pg_restore --no-owner --no-privileges`-forløpet og kontroller først fullkopiens SHA-256. Den separate databasen er bare lesekilde.

`tools/restore_learning_prices.py` flytter deretter bare eksplisitt angitte prisnøkler, opptil 128 om gangen. Tilkoblingsstrengene settes privat i `LEARNING_ARCHIVE_SOURCE_DATABASE_URL` (lokal, isolert gjenoppretting) og `DATABASE_URL` (tiltenkt mål). De skal ikke sendes i chatten eller skrives i kommandoargumenter.

```bash
python tools/restore_learning_prices.py --key "strategy_history/prices/<sha256>.json"
python tools/restore_learning_prices.py --key "strategy_history/prices/<sha256>.json" --apply
```

Første kommando er dry-run. Andre kommando erstatter bare en gyldig referanse med bytes som har den eksakte originalhashen og størrelsen. Allerede gjenopprettede, identiske bytes behandles idempotent. Endret kilde, feil prisnøkkel eller et annet eksisterende prisgrunnlag avvises. Delvis gjenoppretting er trygg å gjenoppta. Når input er tilbake, fortsetter ordinær cron automatisk den ventende beregningen.

## Utrulling og kontroll

1. Behold standarden avslått mens web og scheduler utrulles med samme nye kode.
2. Kontroller at begge tjenestene bruker commit med leservernet, før bare scheduler-flagget aktiveres. Ikke aktiver bred historikksletting eller start en ekstra rapport.
3. Observer ordinær cron og den lille arkivkvitteringen. Registrer faktisk antall arkiverte og sperrede nøkler. Ikke les hele journalen eller latest_run.json for denne kontrollen.
4. Ved feil deaktiveres bare dette flagget. Referansene forblir forstått av leserne; nødvendige originaler gjenopprettes via den kontrollerte lesekilden.

Før utrulling er hele det ekte utvalget prøvd i en separat testdatabase: 4 034 kildeposter lastet fra det kontrollerte arkivet, 1 344 priser arkivert i 11 puljer, alle resultater uendret og alle kildeposter byte-identiske etter full gjenoppretting. Dette er testbevis, ikke en påstand om at produksjonen allerede er endret.

## Kapasitet og begrensninger

Utvalget er omtrent 262 MB JSON og 74 MB lagrede DB-verdier før erstatning. `estimated_saved_value_bytes` måler forskjellen i lagrede verdier ved den enkelte oppdateringen. Det er ikke en måling av Render-disk som har krympet; vanlig VACUUM gjør gammel plass gjenbrukbar. Nye dataskrivinger kan fortsatt øke total DB-størrelse.

Dette første utvalget stanser ikke all vekst. De største strategikjørings- og beslutningslagrene trenger egen referansekontroll før arkivering. Videre arkivutvalg krever verifisert kildekopi og en ny, konkret autorisasjon. Arkivering innebærer ingen godkjenning av avkastning, kildedekning, kostnads-/valutagrunnlag eller parameterendring.
