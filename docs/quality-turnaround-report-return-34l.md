# RC16.34l – kvalitetsgrunnlag, snuoperasjoner og rapportretur

## Problem og endring

Tre eller flere tilgjengelige årsresultater med null/negativ median EPS ble tidligere behandlet som manglende EPS. Det kunne gi INSUFFICIENT/MISSING_DATA og lav datakarakter selv med komplett regnskap. Felles Quality v1.4 skiller nå COMPLETE_FOR_MODEL og NONPOSITIVE_HISTORICAL_EARNINGS fra konkrete datamangler. Ikke-positiv EPS gir ingen P/E-scenario, ingen kvalitetsgodkjenning og maksimalt to samlede stjerner. Faktisk manglende grunnlag får overskriften «Ufullstendig grunnlag». Modellen er generell for standard, kapitalintensiv, syklisk og finans; ingen NRC-særregel er innført. FCF-mangel navngis for modeller som trenger FCF.

Nyere forbedring vises separat fra flerårig kvalitet. Provider henter inntil åtte daterte kvartalsperioder i den eksisterende isolerte prosessen, med uendret timeout på 15 sekunder. Halvårsinput støttes når den er uttrykkelig merket som seks måneder. Kun like varigheter og samme periode året før sammenlignes. Revenue, operating income, margin, net income, EPS og FCF beholdes separat; prosentvekst fra negative/null baser beregnes ikke. Mulig snuoperasjon krever positivt og økende driftsresultat, ikke-fallende positiv omsetning og forbedret margin. Dette er et observasjonssignal, ingen bekreftet fundamental kvalitet eller ordre.

Innhentingstid og eventuell publiseringstid må være tilgjengelig ved vurderingstidspunktet. Periodens sluttdato er ikke en antatt publiseringsdato. Nyere kvartalsdata, pris-/volumfelt og offisielle innside-/shorthendelser har egen kilde- og dekningsstatus. En enkelt, avgrenset offisiell Oslo-meldingsforespørsel per time oppdager regnskapsmeldinger og kontrakter; dette er metadata og ikke uttrekk av verifiserte regnskapstall fra vedlegg. Responsdekning erklæres ikke fullstendig. UI starter ingen slike nettverksoppslag. Short-registeridentiteter løses kun ved entydig navn/ISIN-match.

Før finalistkuttet reserveres inntil fire eksisterende analyseplasser, fordelt mellom offisielle hendelser og positive vekst-/momentumobservasjoner. Kun aksjer med brukbare markedsdata kan reserveres. Maksimumsantall, ressursgrenser og handelsporter beholdes. Markedsøk kan fortsatt overse en snuoperasjon ved manglende providerdekning, forsinkede meldinger eller fullt avgrenset analysebudsjett.

## Shadow og kontroll

Planlagte komplette Quality-kjøringer følger et separat, atomisk lagret forward-eksperiment. Det sammenligner en låst snuoperasjonskurv med den kvalitetstilfredsstillende delen av samme analyserte univers. Begge armer starter med 100 modellenheter per valuta og lik vekting. Kontanter brukes når kontrollkurven er tom. Antatt kostnad er 0,10 prosent per side. Ingen valutaomregning eller reelle handler simuleres. Dette er ikke en full backtest av dagens Super Portfolio-strategi.

Posisjoner byttes ikke med etterpåklokskap. Kurser fra samme fullmarkedssøk gjenbrukes for aksjer som faller ut av finalistene, bare med kjent handelsdato og ferskhet. Manglende kurser gir ingen falsk lukking. Etter minst 30 kalenderdager lukkes en kurv ved første komplette observasjon; faktisk eiertid og forsinkelse vises. Kostnadsjustert avkastning, relativ avkastning, observert drawdown, tapsgivende signaler og senere kvalitetsbekreftelse lagres. Drawdown gjelder observerte kurser, ikke intradag. Overlappende kurver er ikke uavhengige statistiske prøver.

Maksimum er 120 kurver. Full kapasitet stopper nye forsøk og krever eksport/gjennomgang; gamle bevis fjernes ikke automatisk. Små sammendrag og siste seks kurver kan inngå i kjøringsdiagnosen. Hele tilstanden kan lastes ned fra «Snuoperasjoner – shadow og kontroll»; det gjøres ikke et ekstra nettverks- eller historikksøk for dette.

Generell klassifiseringskontroll er lesende: knappen kontrollerer inntil 500 lagrede kjøringer med fremdrift, 30 sekunders grense og minne-/rapportvakt. Den viser antall berørte vurderinger per sektor og unike aksjer. Ufullstendig dekning oppgis. Tilsvarende CLI er `python scripts/audit_quality_classification.py --max-runs 500`. Ingen gamle vurderinger eller beslutninger skrives om. Produksjonsdatabasen er ikke auditert i denne arbeidsøkten.

## Rapportdeling og retur

«Del rapport» forbereder PDF-filen før brukerens klikk og bruker filbasert Web Share når tilgjengelig. Avbrutt deling vises som avbrutt; manglende/avvist nettleserstøtte eller hentefeil gir tydelig nedlastingsreserve. Åpne PDF og Skriv ut er separate handlinger. Retur er bundet til det konkrete, validerte immutable kjøringsnavnet, også fra PDF-annotasjonen. Rapportvalg renderes direkte før markedsvelger/legacy-paneler. Andre navigasjonsvalg rydder rapportkontekst, slik at rapportreturen ikke kan låse andre sider.

## Verifisering og grenser

- 434 regresjonstester passerte; 233 aktive repository-tester passerte, seks eksisterende miljøavhengige PostgreSQL-tester hoppet over lokalt. To nye DB-tester for samtidige shadow-observasjoner/låste bevis er lagt til; alle åtte kjøres i CI.
- Fem genererte JavaScript-testløp passerte: filbasert deling, avbrudd, manglende støtte, avvist tillatelse og hentefeil. Deling krever klikk og bruker PDF-fil, ikke bare rapportlenke.
- Nye tester dekker sektorforskjeller, komplette negative/null årsresultater, reelle feltmangler, YoY-perioder, fremtidig tilgang/publisering, sesong/margin, FCF-fortegn, reservasjon før finalistkutt, låste kurver, kostnader, missing-quote, kurs utenfor finalistene, kapasitetsstopp, uforanderlig audit og eksakt PDF-retur.
- Kort/full PDF er rendret og visuelt kontrollert med et syntetisk NRC-lignende eksempel; dette eksemplet dokumenterer kodeoppførsel, ikke NRCs faktiske kvartalstall eller avkastning.
- Fysisk iPhone/Safari-/Pushover-nettleser er ikke kontrollert her. Lokal nettleserinstallasjon var utilgjengelig; JavaScript-logikk er testet uten å påstå fysisk browser-verifisering.
- Offisiell automatisk ekstraksjon/verifisering av primærrapportenes kvartalstall, historiske tidsriktige regnskapsarkiver og dokumentert resultatforbedring gjenstår. Nye forward-resultater trenger tid og data etter deploy. Ingen strategi promoteres automatisk.

Merge og deploy er ikke utført i denne jobben. Deploy utfører brukeren.
