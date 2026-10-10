# Samlet jobbliste – 10. oktober 2026

Listen samler innspillene i denne samtalen. GO har godkjent implementering. Avkryssing betyr implementert og lokalt testet, ikke merget eller deployet. Delvis gjennomførte punkter står åpne. Detaljer og driftsmålinger: portfolio-learning-validation-34i.md.

## 1. Superportefølje: forståelig rapport og beslutningsgrunnlag

- [x] Vis Rank ved kjøp → nå og antall plasser forbedret/svekket. Manglende kjøpsrank skal stå som ukjent, aldri rekonstrueres uten dokumentasjon.
- [x] Vis AI-score ved kjøp → nå og beste dokumenterte rank siden kjøp.
- [ ] Vis hvorfor hver aksje beholdes, reduseres eller selges, samt hvorfor en bedre utfordrer eventuelt ikke kan overta.
- [ ] Vis tidspunkt for siste fullstendige vurdering og siste stopkontroll separat. Eventuelle rankpiler skal oppgi sammenligningsperiode.
- [ ] Undersøk og rett bransje-/risikoklassifisering: rapporten viser HAFNI som Industrials og shippingeksponering 0 %. Kontroller også ukjent bransje og øvrige stresstester.
- [ ] Vurder fersk fullstendig kjøps-/utskiftingskontroll før handel; mål behovet for hyppigere analyse enn standardintervallet på 12 timer.
- [ ] Test behold/bytt mot utfordrere med handelskostnader, risiko, diversifisering og gjenkjøpsregler inkludert.

## 2. Stop- og gevinstbeskyttelsesvarsler

- [x] Skill hver aksje i en egen tydelig blokk. Vis kjøpskurs, topp, nåkurs, gevinst og salgsgrense.
- [x] Erstatt «pp margin» med forståelig prosentvis mulig kursfall fra nåkurs til salgsgrensen; bruk riktig nevner.
- [x] Erstatt «sikret gevinstgulv» med «beregnet gevinst ved salgsgrensen». Forklar at faktisk salgskurs kan avvike.
- [x] Forklar forskjellen på aktiveringsgrense for gevinstbeskyttelse, andel av toppgevinsten som beholdes og trailing stop.

## 3. Læring og kombinasjonstesting

- [ ] Registrer beslutningsgrunnlag også for avviste kandidater før finalistutvelgelsen, inkludert hendelser som faktisk var kjent på beslutningstidspunktet.
- [ ] Bygg/valider simulering av hele handler og porteføljer med samme beslutningsregler som produksjonen: kjøp, salg, gevinstbeskyttelse, kostnader, kapital, ledige plasser og gjenkjøpsbegrensninger.
- [ ] Test score, signaler, kjøpsbekreftelse, stop, gevinstbeskyttelse, posisjonsstørrelse, sektorgrenser og karantene. Behold separate referanser for Autonomi og Superporteføljen.
- [ ] Start med bredt søk innen avtalte grenser, undersøk lovende områder videre og registrer alle forsøk. Test valgene på senere perioder og en urørt sluttperiode; håndter overlapp og fremtidslekkasje.
- [ ] La et lite antall forhåndsvalgte finalister konkurrere i skyggedrift mot dagens regler på nye data. Mål nettoavkastning, verdifall, tidlige tap, beholdt gevinst, handelsantall og kontantandel.
- [ ] Kjør omfattende tester i separat jobb med begrenset minnebruk og gjenbruk av markedsdata. Fastsett lagrings-/retensjonsbudsjett før skalering.
- [x] Rett oversterk læringsstatus «DOKUMENTERT MERVERDI». Skill foreløpig gjennomsnittsforskjell fra validert forbedring; vis antall observasjoner, tidshorisont og usikkerhet.
- [ ] Skill foreslått, aktiv og ferdig vurdert skyggetest. Vis 20-dagers målinger og 60-dagers modning separat.
- [ ] Test moderat kandidatgruppe mot nær-terskel som hypotese; rapporten dokumenterer ikke at resultatet overføres til Superporteføljen.
- [ ] Presenter bare dokumenterte forbedringer som konkrete forslag med Godkjenn/Avvis, historikk og rollback. Ingen automatisk produksjonsendring fra testresultat alene.

## 4. Oppfølging av tidligere rettelser og åpne driftsforhold

- [ ] Følg opp virkningen av alternativsøk etter blokkerte kandidater og innside-/shortoppdagelse før finalister fra PR #65, med beslutningsspor og relevante scenarioer.
- [ ] Avklar faktisk merge-/deploystatus for PR #67 og verifiser porteføljenavigasjon, godkjenning med ett klikk og mobilvisning på telefon. Sist bekreftet: ferdig PR med grønne sjekker, ikke merget/deployet.
- [ ] Følg opp minneoverskridelsen i webtjenesten separat fra cron-minne. De viste cron-kjøringene fullførte og fastslår ikke webtjenestens krasjårsak.
- [ ] Undersøk databasevekst med målinger av tabeller, indekser og øvrig diskbruk. Tidligere årsak til økningen var ikke fastslått; ingen produksjonsopprydding eller oppgradering er inkludert i denne listen som utført.

## Status etter implementering RC16.34i

Rapport/UI, stoppvarsler, Hafnia-klassifisering og minneavgrenset snapshot-oppslag er implementert. SP-simulator, historisk parameterjobb og låst forwardplan finnes som offline verktøy. Autonomi porteføljesimulering, universarkiv med import/dekningsrapport og separat forward-worker er nå implementert. Produksjonsaktivering etter merge/deploy, tilstrekkelig historisk datalengde, lønnsomhetsvalidering og fysisk mobilverifisering gjenstår. Ingen nye eksperimentresultater kan godkjenne produksjonsendring.

## Tidligere arbeid – sist bekreftet

- PR #65: merget; audit/rettelser inkluderte alternativsøk etter blokkering og innside-/shortoppdagelse før finalister. Effekt må følges opp.
- PR #66: merget; delte gevinstbeskyttelsesregler og bedre kjøps-/salgsbevis. Deploystatus er ikke kontrollert her.
- PR #67: implementert og sjekker grønne ved siste kontroll; merge/deploy og fysisk mobilverifisering gjenstår etter sist bekreftede status.

Anbefalt rekkefølge: avklar PR #67 og drift → bransjeklassifisering og beslutningsforklaring → rank/score og varsler → pålitelig simulator og datagrunnlag → bred kombinasjonstesting og skyggedrift.

## Oppdatert gjennomføringsstatus for de tre gjenværende områdene

- [x] Autonomi-porteføljesimulering med ordinære kjøps-/salgsregler, frozen klokke, egen kapital og handelsledger, uten produksjonseffekter. Gebyrer vises separat som kostnadsfølsomhet fordi ordinært Autonomi-regnskap er uten gebyrer.
- [x] Hele konfigurerte inputuniverser arkiveres fremover, med opprinnelige felt, kontrollsummer og kjent datagrunnlag. Historikkimport, feilliste, dekningsrapport, fast budsjett og eksport uten full innlasting i RAM er implementert.
- [x] Separat, restartbar skyggeworker og cron-integrasjon for begge motorer. Referanse og to forhåndsregistrerte terskelhypoteser låses før fremtidige data brukes. UI viser faktisk status.
- [ ] Import og verifikasjon av alle 246 tilgjengelige legacy-kjøringer i produksjon. Automatisk batchimport er klar for deploy.
- [ ] Tilstrekkelig historikk for 90 dagers embargo og urørt sluttperiode. Ikke-lagret fortid rekonstrueres ikke.
- [ ] Aktiv testing på nye produksjonsdata. Workeren starter etter merge/deploy; kode-/prosesstester er fullført, men produksjonsaktivering er ikke utført.
- [ ] Fullmodne nye resultater og uavhengig dokumentert forbedring. Disse krever videre observasjonstid.

Detaljer, begrensninger og aktivering står i `portfolio-learning-validation-34i.md`. De brede tidligere punktene om komplett historisk datasett, alle signalhypoteser og dokumentert merverdi forblir åpne der deloppgaver gjenstår.

## Superfondportefølje V1 – RC16.34j

- [x] Offentlig Nordnet-katalog, sidevis oppdatering og bred kategori-/ETF-dekning. Kontroll ga 918 fond + 2 255 ETF-noteringer; kjøpskvalifisering er separat.
- [x] NAV-/kursdato, risiko, kostnad, handelsfrister, beholdninger, sektor/region, dokumentlenker og ECB-valuta. 1/3/5/10/20 observerte NOK-kurspunkter med faktiske fra-/til-datoer.
- [x] Separat automatisk modellkapital, ventende kjøp/salg på senere kurs, posisjons-/eksponeringsgrenser, gevinstbeskyttelse og gjenkjøpskarantene.
- [x] Direkte Superfond-knapp på desktop/mobil; portefølje, kandidater, hele sideinndelte katalogen, diagnoser, PDF/CSV/Excel fra innlogget app og Pushover-leveringskø med direkte app-lenke.
- [x] E24 og tilgjengelige produktpubliseringer med kilde-/dekningsstatus.
- [x] To fryste skygger og global indeksreferanse, fremtidig validering, konkrete Godkjenn/Avvis-forslag, atomiske kvitteringer, historikk og rollback.
- [x] Checkpoint, felles PostgreSQL-kjørelås for cron/SP/Paper/manuelle rapporter, synlig kapasitetsutsettelse og avgrenset katalog-, detalj- og historikklagring.
- [x] Uforanderlig daglig arkiv og separat ressursbegrenset historisk testverktøy; ingen syntetisk fortid og ingen automatisk parameterendring.
- [ ] Første komplette katalogpass og modellutførelse i produksjon, faktisk varsling/PDF-lenke og fysiske mobiltester etter deploy.
- [ ] Modne fondsresultater og tilstrekkelig dagshistorikk; full historikk fra før oppstart, komplette forvalterfeeds, alle parameterkombinasjoner og faktisk plattformkostnad er ikke ferdig i V1.
- [ ] Generell prioritetskø/preemption og koordinering av alle legacy synkrone analyser; V1 dekker de navngitte worker-/cron-entrypointene med felles eksekveringslås.
- [ ] Reelle Nordnet-handler vurderes som egen fase om 6–12 måneder.

Detaljer og testbegrensninger: `superfund-v1-34j.md`. PR #68 er merget (00bd9fb), inkludert det tidligere PR #67-arbeidet. Det betyr ikke at fysisk mobilkontroll eller deploy av denne fondsversjonen er gjennomført.

## RC16.34k – fremdrift og Superfond-kontroll

- [x] Felles fremdrifts-/aktivitetsvisning for søk, synkrone tester, rapporter og navngitte bakgrunnsjobber; kjent/ukjent total skilles.
- [x] Superfond sidefremdrift og separate ressursårsaker; host-load blokkerer ikke alene.
- [x] Stoppvarsel etter gjentatte utsettelser og kapasitetstilgang etter varslet stopp.
- [x] Forklart tomt rapportfelt, eksplisitt rapportbygg og diagnose-ZIP før første snapshot.
- [x] ZIP med læring, shadow, regler, handler, datagrunnlag, kontrollfunn og eksakt filmanifest/utelatelser.
- [x] Læringsfase, sammenligningsgrunnlag, kjøps-/salgsbegrunnelser og lesbare mobildiagnoser.
- [ ] Bekreftet katalogfremdrift, cgroup-måledekning, Pushover og fysisk mobil etter deploy.

Detaljer og grenser: `work-progress-superfund-34k.md`.

## RC16.34l – kvalitetsgrunnlag, snuoperasjoner og rapportretur (GO mottatt)

- [x] Rett fellesmodellen slik at tilgjengelige null-/negative årsresultater ikke klassifiseres som MISSING_DATA. Skill faktisk datamangel, utilstrekkelig sammenlignbar historikk og ikke-positiv normalisert inntjening; ikke beregn vanlig P/E-scenario fra ikke-positiv EPS.
- [x] Skill datadekning fra kvalitetsgrad i UI/PDF. INSUFFICIENT skal forklares med konkrete mangler, ikke automatisk få overskriften «Svak». Vis historisk kvalitet, dokumentert forbedring og kursmomentum som separate vurderinger.
- [ ] Kontroller lagrede vurderinger på tvers av standard-, kapitalintensiv-, syklisk- og finansmodellen. Oppgi antall berørte aksjer og konkrete årsaker; NRC brukes som eksempel, ikke som særregel.
- [ ] Kontroller innhenting av nyere kvartals-/halvårsrapporter fra offentlige selskapskilder. Vis årsperioder, nyere rapportperiode, kilde og innhentingsstatus hver for seg; gammel årsreferanse er ikke alene bevis på manglende kvartalsdata.
- [x] Vurder snuoperasjoner med nyere dokumenterte marginer, inntjening og kontantstrøm, uten å likestille forbedringstegn med et kjøpssignal eller automatisk løsne risikokrav.
- [x] Regresjonstester: negativ median med komplett historikk, reelt manglende EPS/ROCE, nullinntjening, snuoperasjon med nyere forbedring og sektorforskjeller. Kontroller at rapport og utvelgelse bruker samme forklaring.

- [x] Generell, lesende klassifiseringskontroll av inntil 500 lagrede kjøringer, med fremdrift, tids-/minnegrense, antall og årsaker per modell og aksje. Verktøyet er klart; produksjonsdatabasen er ikke kontrollert her.
- [x] Nyere sammenlignbare kvartals-/halvårsdata støttes; Yahoo-kvartaler hentes isolert og kilde/tilgjengelighet vises. Nyere regnskapsmeldinger og kontrakter oppdages fra avgrenset offentlig Oslo-metadata. Tall fra primærrapportenes PDF-er blir ikke automatisk tolket eller erklært verifisert.
- [x] Inntil fire analyseplasser reserveres for oppdagelse før finalistkuttet. Ingen risikokrav eller produksjonsordre endres.
- [x] Avgrenset forward-shadow med låste kurver, lik kapital per valuta, eksplisitte kostnader, avkastning, målt drawdown og falske positive. Komplett kontrollgrunnlag kan lastes ned separat.
- [x] Egen rapportdeling med tydelig reserve, og retur til samme kjørings rapportvalg før markedsvelgeren.
- [ ] Produksjonsaudit av lagrede vurderinger, verifisert primærkildeinnhenting av nyere regnskapstall, og reelle nye shadow-resultater etter deploy.
- [ ] Fysisk iPhone/Safari-delingskontroll og navigasjon etter deploy. Deploy utfører brukeren.

Kode og testgrunnlag: `quality-turnaround-report-return-34l.md`. Merge/deploy er ikke utført i denne jobben.

## RC16.34m – Superfond Topp 25 og mobiltekst (GO mottatt)

- Topp 25 fra hele det vurderte utvalget; deduplisering på ISIN før visningsgrensen.
- Navn, type, investeringsområde, registreringsland, forvalterland og avkastningsvaluta med tydelig kilde/mangel.
- Gruppevisning etter kategori og valuta, separate kategori- og topp-ranger.
- Lesbare kort, lenker, datoer og rådiagnoser i alle Superfond-menyer.
- Navn og behandlingstid på ventende modellordre; faktisk kapasitet fra jobbdiagnosen.
- Forklaring på poeng, valutabegrensning, konsentrasjon, RSS-relevans og læringsfremdrift.
- Samme identitet og Topp 25 i rapporter; uendrede modellkjøpsregler og ressursbudsjetter.
- Automatiserte regresjons- og nettleserkontroller; dokumentasjon i `superfond-top25-mobile-34m.md`.

Ny PR opprettes etter lokal verifisering. Merge og deploy krever senere instruksjon; deploy utføres av brukeren.
