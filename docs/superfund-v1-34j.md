# Superfondportefølje V1 – RC16.34j

Første modul er en separat automatisk modellportefølje. Den sender ingen ordre til Nordnet. Egen startkapital er 1 000 000 NOK. Aksjemotorenes kapital, posisjoner og parametre brukes ikke som fondskapital.

## Offentlige data og faktisk dekning

En anonym kontroll 10. oktober 2026 hentet samtlige sider i Nordnets offentlige lister: 918 fondsoppføringer og 2 255 ETF-oppføringer, totalt 3 173 noteringer og 3 156 unike ISIN-er. Dette er kildekatalogens størrelse ved kontrollen, ikke antallet godkjente kjøpskandidater. Katalogen oppdateres fortløpende og kan endres.

- Katalog/NAV: `https://www.nordnet.no/fond/liste` og `https://www.nordnet.no/etf/liste`, sidestørrelse 100, sortering navn stigende. Produktdetaljer fra offentlige produktsider.
- Risiko, kategori, kostnad, avkastningsperioder, utdelingstype og handelsstatus hentes fra katalogen. Handelsfrister, UCITS, beholdninger, sektor-/regionvekter, dokumentlenker og tilgjengelige publiseringer hentes i egne detaljbatcher.
- Valuta: ECBs 90-dagers referansekursarkiv. Siste tilgjengelige kurs på eller før kursdatoen benyttes; mer enn fem dagers valutaforsinkelse blokkerer utenlandske kjøp.
- Nyheter: eksisterende E24 RSS-adapter, relevansfiltrert på fond/marked og utvalgte beholdningsnavn, pluss det produktsidene faktisk publiserer. Ingen komplett forvalter-/nyhetsdekning eller automatisk nyhetsbonus hevdes.

Adapteren bruker offentlig HTML/SSR, ingen innlogging, cookies eller privat megler-API. Skjemaendring, kildefeil og datamangler vises. Ingen feil erstattes av oppdiktede data. En offentlig Nordnet-notering er ikke en bekreftelse på at produktet kan kjøpes på brukerens bestemte kontotype.

## Utvelgelse og modellhandel

Katalogen overvåkes bredt, med alle kategorier synlige. Første handelspolitikk er konservativ: daglig omsatte akkumulerende aksjefond og verifiserte UCITS-ETF-er. Rentefond, utdelende produkter uten kontantstrømsdata, komplekse/inverse/girede produkter, gammel kurs, ukjent risiko/kostnad og uverifiserte eksponeringer blokkeres fra modellkjøp og forsvinner ikke fra katalogen. Komplekse produkter identifiseres konservativt fra produktnavn; dette er ikke en fullstendig juridisk produktklassifisering.

Uke/måned/kvartal inngår i en enkel, forhåndsdefinert trendscore. Rang beregnes innen kategori **og samme publiserte avkastningsvaluta**. Fondsavkastningene i kontrollen var oppgitt i NOK, mens de fleste ETF-avkastningene var oppgitt i EUR. Global sortering av screeningscore er derfor ikke en dokumentert NOK-alfa eller indeksjustert sammenligning. Det må tas med ved vurdering av ETF-kandidater.

1/3/5/10/20-punkts NOK-utvikling bygges fra lagrede, distinkte kursdatoer med fra-/til-dato. Manglende datoer fylles ikke inn; antall observerte punkter er ikke nødvendigvis antall sammenhengende børsdager. Publiserte periodeavkastninger konverteres aldri til syntetisk dagshistorikk. Kvalifisert ukesoppgang på minst 3 % kan gi tidlig varsel, med 48 timers karantene for samme notering.

Modellordre legges først i ventestatus. Vanlige fond må ha dokumentert daglig kjøps-/salgsfrekvens og handelsfrist; utførelse krever en kursdato senere enn beslutningsdato og passert registrert handelsfrist. ETF-modellen bruker også en senere kursdato. Dette gir daglig modellutførelse, ikke simulering av intradagshandel eller en påstand om faktisk tildelt NAV. Kurs, dato, beslutningstid og estimatstatus lagres i handelsloggen.

Reglene inkluderer kontantreserve, maksimalt åtte plasser, 12,5 % per posisjon, kategori-/sektor-/regiongrenser, kjent beholdningsoverlapp og syv dagers karantene etter salg. Algoritmen søker videre forbi blokkerte kandidater og dupliserte ISIN-er. Kapital, gates og konsentrasjonsgrenser kontrolleres igjen ved kjøpsutførelse. Salgsutløser ratcheter oppover: maksimalt 6 % fall fra topp eller 55 % av toppgevinsten beholdt etter +2 % toppgevinst. Senere salgspris kan være lavere enn utløseren.

Handelsfriksjon og valutapåslag estimeres. ETF-er får halv spread i tillegg. Løpende fondskostnader inngår i NAV og trekkes ikke dobbelt; plattformkostnader/refusjoner er ikke avstemt mot faktisk Nordnet-konto. Overlapp bygger på kjente toppbeholdninger og er ikke full beholdningsdekning.

## Visninger, eksport og varsler

Direkte Superfond-knapp i desktop- og mobilnavigasjon, med separat rute som ikke overskrives av gamle panelvalg. Siden har én kolonne og viser portefølje, ventende ordre, kjøpsrang/nårang, kandidater, hele sideinndelte katalogen, kilde-/nyhetsstatus, parametre, endringshistorikk, rollback og diagnoser. UI leser lagrede data; Oppdater legger én deduplisert forespørsel i kø.

PDF, CSV og Excel bruker samme komplette snapshot. Pushover gjenbruker eksisterende notifier med normal prioritet og lenke til varig PDF-rapport. Levering skjer etter porteføljepublisering. Utsendelse behandler opptil fem ventende hendelser per forsøk; øvrige hendelser beholdes. Rapporter og varsler prøves igjen ved feil, og eksisterende publisert rapport beholdes. Ekstern varsling kan ikke gis en absolutt «akkurat én gang»-garanti ved nettverksbrudd etter at leverandøren har akseptert meldingen.

## Læring og historikk

- Hovedmodell og to fryste skygger med uketerskel 0,5 % og 2 % vurderes på samme katalogdata, med hver sin kapital og handelslogg.
- En verifisert NOK-notering av Nordnet Global Indeks brukes som kjøp-og-behold-referanse, med samme startkapital/reserve og modellfriksjon. Sammenligningsperioden normaliseres fra første faktisk modellerte referansekjøp.
- Etter 60 parrede kursdatoer fryses valgt utfordrer. Minst 20 senere datoer, ti nye handler i kontrollperioden, meravkastning mot både referanse og hovedmodell og ikke større verdifall kreves før et konkret terskelforslag fremmes. Ingen automatisk parameterendring.
- Godkjenn/Avvis er atomiske og idempotente. Godkjenning lagrer parameter, bruker/kilde, tidspunkt, historikk og beslutningskvittering. Gjentatte trykk lagrer ikke flere endringer. Manuel parameterlagring beholder tidligere kvitteringer. Etter 20 nye parrede datoer kan et avgjort forslag vurderes på nytt, med en ny kontrollperiode.
- Ett komplett observerbart katalogbilde per dag arkiveres uforanderlig og komprimert med SHA-256. Offlineverktøyet `tools/run_superfund_experiments.py --output ...` kontrollerer sjekksummer og fremtidslekkasje og tester inntil 20 forhåndsdefinerte uketerskler i kronologisk 60/20/20-inndeling. Bare valgt strategi bruker sluttperioden. Produksjonsparametre endres aldri av verktøyet.

Full daglig fondshistorikk fra tiden før aktivering er **ikke** hentet. Før tilstrekkelige kursdatoer foreligger vises INSUFFICIENT_HISTORY. Offline fondsjobben startes eksplisitt; to skygger på nye data kjører automatisk. V1 tester ikke alle kombinasjoner av stop, størrelse, kostnad og sektortak. Modne resultater og dokumentert meravkastning krever observasjonstid.

## Ressurser og koordinering

| Område | Grense / oppførsel |
|---|---|
| Fondskjøring | Etter obligatoriske aksjeoppgaver og eksisterende læring; tidligst hvert 30. minutt uten eksplisitt forespørsel |
| Kildetrafikk | Normalt 3 katalogsider + 2 produktdetaljer; 12 sekunders HTTP-timeout og maks 5 MiB per svar |
| Tidsbudsjett | Mykt 40-sekunders budsjett mellom side-/detaljbatcher, ikke en hard totalgrense; pågående I/O/lagring kan ta lengre tid |
| Ledig kapasitet | Utsett ved kjent ledig minne under 384 MiB eller høy normalisert host-load; status lagres synlig |
| Katalog | Maks 60 sider per type og 64 MiB; over grensen stoppes kjøringen med dekningsfeil |
| Produktdetaljer | Maks 512 dokumenter / 16 MiB; eldre ikke-beholdte detaljer roteres, beholdte produkter/referanse beskyttes |
| Daglig serie | Maks 60 faktiske kurspunkter per notering |
| Historikkarkiv | Maks 180 dagsbilder / 64 MiB komprimert, 12 MiB rådata per bilde; stopp synlig når budsjettet nås |
| Snapshot | Maks 4 MiB per vanlig JSON-dokument; begrensede portefølje-/handelslogger |
| Offline-test | Diskbasert frame-lesing, 768 MiB adresseplass og 45 CPU-sekunder; ingen samlet historikk i RAM |

PostgreSQL-sessionlåsen er felles for cron, separat SP-worker, separat Paper-worker, report-scheduler og manuell rapportworker. Nøstede kall i samme tråd gjenbruker eierskapet; andre prosesser/tråder må vente eller utsette. Disconnect frigir låsen. Fundspublisering kontrollerer at låsen fortsatt eies. Lokal utvikling bruker prosess- og fillås.

Dette er en felles eksekveringslås og eksisterende jobbenes varige tilstander, **ikke** en ny generell prioritetskø med preemption. En lang manuell jobb kan utsette cron. Manuell rapport venter opptil ti minutter med heartbeat og kan avbrytes; deretter vises eksplisitt feil. SP-jobb i WAITING_RESOURCE gjenopptas av cron med eksisterende token. Fondsider checkpointes én side av gangen. Modeller, skygger og analyse publiseres atomisk som ett komplett snapshot. Legacy synkrone UI-analyser utenfor disse entrypointene er ikke generelt koordinert av denne låsen.

## Verifikasjon og gjenstående driftssjekk

Lokalt: 24 releasekontrakter, 386 regresjonstester og 185 aktive tester bestått før siste dokument-/presentasjonsjustering. Ny fondsdekning er kontrollert anonymt mot hele kildekatalogen; ECB og representative produktsider er kontrollert. CI kjører i tillegg isolerte PostgreSQL-tester av sessionlås, disconnect, konkurrerende godkjenninger og køduplisering. AppTest bekrefter sidevisning, kø uten fetch og godkjenning som forsvinner ved første klikk.

Visuell nettlesertest på mobil ble ikke fullført lokalt: Chromium-nedlastingen leverte ugyldig arkiv. Fysisk mobil, faktisk Pushover/PDF-lenke, første produksjonskatalogpass, ressursmålinger og påfølgende NAV-utførelse må kontrolleres etter deploy. Ingen produksjonshandel, databaseopprydding eller ny betalt Render-tjeneste er utført her.
