# RC16.34m – Superfond Topp 25 og mobilvisning

## Endret oppførsel

Topp 25 velges fra hele det vurderte utvalget før den eksisterende listen begrenses til 100 noteringer. Grunnkrav til data, trend, risiko og produkt beholdes. Samme ISIN vises bare én gang; en blokkert børsnotering hindrer ikke visning av en kvalifisert notering av samme produkt. Kapital og porteføljeoverlapp kan fortsatt hindre modellkjøp. Kjøpsregler, budsjett, kildespørringer og risikogrenser er ikke endret.

Topp-listen viser navn, fond/ETF, investeringsområde, registreringsland, forvalterland når oppgitt, kategori, avkastningsvaluta, poeng, uke/måned/kvartal, risiko, kostnad, kursdato og status. Registreringsland utledes aldri fra ISIN eller forvalterens adresse. Der eksponeringsdata mangler, merkes investeringsområdet som kildens kategori. Ukjente opplysninger oppgis tydelig.

Poengberegningen er den eksisterende 60/25/15-vektingen av ukes-, måneds- og kvartalsavkastning. Dette er en informasjonsliste basert på kildeavkastning, ikke dokumentert forventet avkastning eller en sammenligning i felles NOK. Instrumentvaluta som reserveverdi merkes som ubekreftet avkastningsvaluta. Historiske NOK-avkastninger blir ikke konstruert fra dagens valutakurs.

Kategoriliste med egne seksjoner etter kategori og valuta følger under Topp 25. Kategori-rang og samlet plassering har separate etiketter. Antall vurderte noteringer, grunnkvalifiserte ISIN, komplette trendserier og verifiserte detaljer er separate mål.

## Lesbarhet og drift

Superfond får avgrensede stilregler som opphever legacy-grensen på teksthøyde, gir kort med normal tekstflyt, lesbare lenker og rådiagnoser og plass over mobilnavigasjonen. Endringen gjelder alle sju Superfond-menyer. Ventende modellordre viser navn og identitet, opprettelsestid og tidligste behandling; en senere observert kursdato er fortsatt påkrevd. Generelle RSS-treff merkes uten å påstå fondsrelevans. Læringsvisningen viser fremdrift mot 60 datoer og senere 20 kontrollobservasjoner uten å love forbedring.

Kapasitetsmålingene leses fra jobbens faktiske `capacity`-objekt. Manglende måling er ikke null. Kjørelås, batchgrenser, CPU-/minnegrenser og datalagringsgrenser beholdes. Kompakte visningsdata lagres sammen med snapshot; UI gjør ikke en full kataloglesning eller eksterne oppslag. PDF, Excel og CSV bruker samme lagrede grunnlag og identitetsopplysninger.

## Kompatibilitet og kontroll

Eldre snapshots viser en eksplisitt advarsel: utvalget er da begrenset til de allerede lagrede 100 kandidatene. Hele utvalget kommer etter neste fullførte batch. Manglende registreringsland kan ikke repareres uten en dokumentert kilde.

Kontroller: eksisterende Superfond- og ressurs-/diagnosetester; nye tester for kvalifiserte produkter etter 100 blokkeringer, ISIN-duplikater, kategorirang, ukjent land/valuta, HTML-escaping, identitet utenfor kandidatlisten, PDF/Excel-konsistens og alle UI-menyer. Release CI kjører Chromium på 375, 430 og 1280 piksler mot den faktiske Superfond-siden med representative lagrede data og legacy-CSS. Skjermbilder lagres som CI-artefakt. Fysisk iPhone/Safari og produksjonsdeploy er ikke verifisert av denne jobben.
