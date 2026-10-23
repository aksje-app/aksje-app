# Kontrollert ny start – tre simuleringsporteføljer

23. oktober 2026. Eksisterende PR #167, `fix/systemrevisjon-20261022`.
Utgangspunkt: `e274739c81d14948fc39354b9ca6f4b3a8541f6d`.

**Løsningen for sikker arkivering og klargjøring er implementert. Faktisk
produksjonsarkivering og opprettelse av produksjonsutkast er ikke utført:**
produksjonskilder, varig arkivmål og operatørens krypteringsoppsett er ikke
tilgjengelige i dette miljøet. Ingen konto er nullstilt eller aktivert.

## Ny beslutning og startkapital

Historisk rekonstruksjon er ikke lenger en forutsetning for ny start. Alt
tilgjengelig gammelt materiale skal bevares, mens de nye kontoene starter uten
aksjer og uten overføring av gammel kostpris. Manglende gamle handler fylles
ikke inn. Det opprettes ingen fiktive salg for å tømme gamle porteføljer.

| Ny konto | Ny modellkapital NOK | Grunnlag |
|---|---:|---|
| Paper Trading | 100 000 | Opprinnelig standard i `trading_settings.DEFAULT_RULES.start_cash`, `paper_store.DEFAULT_PORTFOLIO.cash` og `paper_trading.performance_stats` |
| Autonomi | 500 000 | Brukerens beslutning om ny simuleringskapital |
| Superporteføljen | 1 000 000 | Brukerens beslutning om ny simuleringskapital |

Beløpene er ny modellkapital, ikke meglersaldoer eller avstemte gamle kontanter.
Paper-valget bygger på repositoryets dokumenterte opprinnelige standard.
Eventuelle produksjonsoverstyringer er ikke kontrollert og skal bevares i arkivet;
de brukes ikke automatisk til å endre den nye kontoens planlagte kapital.

Starttid må oppgis eksplisitt med tidssone og kan ikke være før arkivet.
Grensesnittets plan har ingen implisitt startdato. Ingen dato eller aktivering
velges automatisk når en modelljobb starter.

## Separat arkiv

`services/simulation_archive.py` bruker:

- Full PostgreSQL-dump i custom-format, under en eksportert REPEATABLE READ /
  READ ONLY-snapshot. Ingen hviteliste som bare tar med deler av journalene.
- Alle filer i eksplisitt oppgitte runtime-/rapport-/modellmapper, også binære
  læringsmodeller. Kildeinventaret hashes før og etter kopiering; endringer
  stanser arkiveringen. Symlenker og udeklarerte kildeomfang skal avklares.
- Et obligatorisk kildeomfang som dekker porteføljer, handler, beslutninger og
  signaler, rapporter, NAV/resultater, læring/observasjoner, strategiparametere,
  audit og diagnostikk. Operatøren må bekrefte inventaret og stanse/drainere
  kildeskrivere før snapshot. Verktøyet stopper dem ikke selv.
- Kryptering med OpenSSL CMS og et operatørstyrt offentlig sertifikat. Privat
  dekrypteringsnøkkel legges ikke i arkivet eller applikasjonens modellager.
- Ny unik arkiv-ID, tidsstempel, SHA256 per fil, manifesthash og kryptert filhash. Arkivfil, kvittering og kataloger synkroniseres til disk
  før ferdigmelding.
  Filer opprettes eksklusivt. Ferdige arkivfiler forsegles med filmodus 0400 og
  arkivmappe 0500. Normal modellagring kan ikke overskrive eller erstatte dem.
- Kontrollert tilbake­lesing: dekryptering og kontroll av alle arkivbytes mot
  manifestet. Ingen gjenoppretting til produksjonen finnes i verktøyet.

Arkivroten må ligge utenfor Git og alle aktive runtime-trær. Den må driftes på
varig, separat og tilgangsstyrt lagring. Testenes midlertidige filmapper er ikke
produksjonsarkiv. Filrettigheter beskytter mot vanlige modellskrivere; en
privilegert administrator kan endre rettigheter. Ekstern kopi/retensjon og
beskyttelse av nøkkelen må etableres i drift. Ingen slik driftskonfigurasjon er
bekreftet her. Behold sertifikatet og den tilhørende private nøkkelen for senere
innsyn; de må ikke legges i GitHub eller deles i samtalen.

Full dump kan inneholde andre delte applikasjonstabeller og sensitive opplysninger.
Hele arkivet behandles derfor som privat. Verken rådata, dekrypterte kopier,
operatoroppsett, databaseadresser eller nøkler følger PR-en.

## Tre nye perioder uten gammel beholdning

`services/simulation_restart.py` oppretter tre DRAFT-regnskaper i minnet og
lagrer dem samlet i én atomisk operasjon under:

`simulation_restarts/<periode-ID>/bundle.json`

Hver konto bruker den eksisterende NOK-regnskapsmotoren. Åpningen inneholder
ny kapital, tom posisjonsliste, ingen handler, ny starttid og kontrollert
arkivreferanse. Den uforanderlige klargjøringsbeslutningen og hver åpningsbalanse
bindes med SHA256. Periodens vedtatte kapital beholdes selv om en fremtidig
standard endres. Et identisk gjenforsøk returnerer samme periode; en annen
beslutning kan ikke overskrive eksisterende kontoer eller handler.

`AccountStorage` krever en eksplisitt periode-ID og tillater bare de tre nye
kontoenes nøkler. Ukjent periode eller forsøk på gammel portefølje-/læringsnøkkel
avvises. Det finnes ingen reservebane som henter gamle kontanter eller posisjoner.
Gamle `economic_accounts/*` og historiske porteføljenøkler overskrives ikke.

Klargjøring krever vellykket arkivkontroll. Produksjons- og utviklingsaktivering
av disse restartkontoene er bevisst sperret, også om den eldre generelle
aktiveringsvariabelen settes. Isolerte tester kan aktivere prøve­kontoer med
`APP_ENVIRONMENT=test`; dette er ikke produksjonsaktivering.

De ordinære strategimotorene er ikke automatisk koblet om. En senere kontrollert
omkobling må velge denne kontokonteksten eksplisitt og bruke den dokumenterte
fill-kontrakten. Det er ingen aktiv periodepeker eller automatisk jobb som
starter de nye kontoene i denne endringen.

## Historikk, læring og brukergrensesnitt

Eksisterende utvelgelses-, kjøps-, salgs-, stop-loss-, gevinstsikrings- og
rebalanseringsregler er ikke endret. Læringsmodeller, parametere og akkumulerte
observasjoner blir liggende i sine eksisterende lagre; restartkoden skriver
ikke til dem. Arkivet bevarer i tillegg et uforanderlig kontrollpunkt.

Visning og eksport skiller mellom:

1. Tidligere strategilæring som beholdes.
2. Tidligere økonomiske modellresultater som beholdes og kan være uverifiserte.
3. Nytt dokumentert NOK-nettoresultat fra valgt restartperiode.

Alle tre sider har et lesepanel med planlagt kapital og nedlastbar plan.
Et eksplisitt periode-ID gir innsyn i riktig ny konto. Panelet arkiverer,
nullstiller eller aktiverer ikke kontoer.

De gamle destruktive `reset_portfolio`-funksjonene for Paper og Autonomi er
sperret før de kan skrive eller slette noe. De tilhørende reset-kontrollene og
Papers ujournalførte kapitaloverskriving er fjernet. Historisk kostpris trenger
ikke rekonstrueres for den nye tomme perioden. Superfond får ingen restartkonto.

## Tester og status

Den brede isolerte pakken besto: **2 459 tester og fire deltester**, ingen feil
eller skips (381,42 sekunder). Den omfatter **85 nettleserforløp** på PC-/mobilbredde
og **23 PostgreSQL-integrasjonstester**, inklusive full dump/gjenoppretting.
Alle de opprinnelige 99 regresjonstilfellene er med og besto. Etter siste
avgrensede endring ble **14 restarttester** kjørt på nytt og besto; de overlapper
den brede pakken. Den siste endringen hindrer at en fremtidig kapitalstandard
endrer kontrollen av en gammel periode. Hele den brede pakken er ikke kjørt
på nytt etter denne ene endringen.

I tillegg besto 24 releasekontrakter og fem Node-tester for rapportdeling.
Avhengighetskontrollen verifiserte 70 låste avhengigheter, runtimekontrollen
besto og CLI-hjelpen kunne kjøres. To eksterne Yahoo-tester ble forsøkt på
nytt, men feilet med CONNECT-proxy HTTP 403 for MYCR.ST og MSFT:
**IKKE VERIFISERT**. Disse feilene er ikke skjult i bestått-tallet.

Sluttall finnes i [testresultater.json](testresultater.json). Nye tester dekker
kryptert arkiv, full bytebevaring av læring/rapporter/tap, endrede kilder,
kontrollsumfeil, ufullstendig arkiv, dataseparasjon, alle tre kapitalbeløp,
atomisk klargjøring, gjenforsøk, sperret produksjonsaktivering, pensjonerte
reset-API-er og ny modellhandel uten endring av arkiv eller gammel læring.

PostgreSQL-testen tar en ekte full dump fra en isolert testdatabase, dekrypterer
arkivet, gjenoppretter dumpen i en ny midlertidig database og kontrollerer at
læringsdata og tap er bevart. Alle data i denne testen er syntetiske.
Nye nettleserforløp kontrollerer planvisning og JSON-nedlasting ved 1280 og
375 piksler for alle tre porteføljer. Nettleserfixturen erstatter innlogging
og blokkerer eksterne tjenester.

Før faktisk ny start gjenstår tilgang til kildene, komplett kildeinventar,
varig arkivmål og sertifikat/nøkkel, kontrollert arkivering/tilbakelesing,
eksplisitt starttid og gjennomgang av den senere motoromkoblingen. Ingen
rekonstruksjon av manglende gamle økonomiske hendelser er nødvendig for en
ny, tom konto med de besluttede modellkapitalene.

Ingen faktisk produksjonsarkivering, produksjonsutkast, nullstilling,
aktivering, posisjonsoverføring, merge eller deploy er gjennomført.
