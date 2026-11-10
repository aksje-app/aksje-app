# Sluttkontroll av læringsdata, punkt 1–4

Denne kontrollen følger brukerens beskjed om å ferdigstille datakvalitetsarbeidet før punkt 5. Punkt 5 er ikke startet. En gjennomført kontroll er ikke det samme som at historiske avkastningstall er godkjent.

## Verifisert produksjonsgrunnlag

Etter PR193 og PR194 har alle tre kjøretidsroller brukt `7da8a44042a6668b311bf0415ba4017eeb33611e`. Ordinært vedlikehold fullførte 9. november kl. 23:20:42 UTC uten feil. Ingen ekstra skanning ble startet.

Alle 92 opprinnelige beslutningsstempler er kontrollert mot originaleksporten og sine SHA256-stempler. Alle 92 radene fra eksporten etter karantene er fremdeles uendret, inkludert de 14 radene utenfor karantenen. Alle tre komprimerte originalkopier og kvitteringer er lest tilbake fra produksjonsdatabasen. De inneholder nøyaktig de 78 opprinnelige radene; de aktive ugyldige målefeltene er tomme.

Det nåværende dokumentet har 133 observasjoner: 78 i karantene, 14 eldre referanser og 41 nye observasjoner med V2-metoden. De nye observasjonene er referanse-/kontrollutvalg fra kveldsrapporten, ikke gjennomførte kjøp. Det foreligger ingen nye modne avkastningsresultater fra dem.

Rapport `MI-20261109-220857` passerte sluttkontrollen og lagret en egen uforanderlig signalregistrering med null strenge/moderate anbefalinger. Kildeantall, rapportidentitet, lagringsnøkkel, kontrollsum og separat kvittering stemmer. Kvitteringen har `recorded_after_final_release_gate=true`. Dette bekrefter en ordinær produksjonslagring, men er ikke en observasjon av et nytt kjøpssignal. Registrering av ikke-tomme signalsett og fullt måleutvalg er testet mot isolert PostgreSQL.

## Restpunkt som denne endringen retter

Eldre observasjoner kunne fortsatt få nye målinger med gammel metode, og bruke opp den nye metodens plasser. Uten en V2-observasjon kunne eldre data dessuten fremdeles inngå i aktive analyser og gruppestatistikk. Bare den eksplisitte V2-metoden får nå oppdateringer, bruker aktive kvoter eller inngår i aktiv læringsstatistikk. Ukjente metodeversjoner behandles som ikke godkjente. Originalradene beholdes uten omskriving. Den autoritative databaseskrivingen beskytter dem under samme radlås mot at en utdatert jobb endrer eller fjerner dem. Dette er ikke en påstand om generell tapsfri sammenslåing av samtidige V2-utvalg.

Automatisk bygging av den gamle historiske baselinen er stanset før arkivlesing, prisnedlasting og varsling. Den eksisterende baselinen og tidligere publiserte dokumenter beholdes som originalhistorikk. Opprinnelig «VERIFISERT» beholdes som metadata, mens aktive visninger merker grunnlaget som ikke kvalifisert og skiller de gamle referansetallene fra kvalifiserte horisonter. En utdatert baseline må ikke bli en automatisk snarvei rundt punkt 5.

## Kriterier og gjenstående sperrer

| Punkt | Dokumentert resultat | Hva dette ikke godkjenner |
|---|---|---|
| 1. Originaler og gjenoppretting | 92/92 beslutninger og alle 78 originalkopier verifisert. Eksport med kontrollsummer følger sluttkontrollen. DB-kopiene beholdes. | Full historisk rapportdekning er ikke dokumentert. |
| 2. Kilde- og målekontroll | Alle 13 gjenværende målte gamle rader er kontrollert, jf. kildeaudit. De gamle radene er avvist som aktivt læringsgrunnlag. Ny brutto metode er versjonert og testet. | Netto NOK-strategiresultat er **ikke godkjent**. Kostnads-/valutakjede for en historisk simulering og svensk sammenlignbar totalavkastningsindeks er ikke ferdig kvalifisert. |
| 3. Signaldekning | Ny komplett signalregistrering er skilt fra begrenset måleutvalg og verifisert i en ordinær rapport. Ikke-tomme sett er testet i PostgreSQL. Alle historiske rapporter i gjeldende arkiv har fått en kildevurdering. | Eldre signaler er ikke rekonstruert, og manglende historikk er ikke null signaler. Første ikke-tomme produksjonsregistrering er ennå ikke observert. |
| 4. Karantene og kontrollert sletting | 234 ugyldige horisontmålinger og 3 251 dagsmerker på 78 rader er fjernet fra aktiv bruk. Originalkopier, kvitteringer og beslutninger er verifisert bevart. | Permanent sletting av gjenopprettingskopiene er ikke utført eller nødvendig for å isolere dataene. |

Alle 122 planlagte rapporter i gjeldende arkiv er kontrollert med eksakte lagringsnøkler og kun størrelsesmetadata: 22 har fullrapport eller kanonisk kilde i tilkoblet DB; 100 mangler begge der. Dette er ikke bevis på at filene er borte fra produksjonsdisk eller sikkerhetskopier. Tilstedeværelse av en kilde er heller ikke i seg selv kvalitetsgodkjenning. Individuelle rapportidentiteter, ukjente signalantall og utelukkelsesårsaker finnes i maskinmanifestet i gjenopprettingspakken.

**Punkt 1–4 kan ikke samlet merkes fullt økonomisk godkjent.** Kildegjenfinning og netto målegrunnlag er eksplisitte sperrer, ikke usynlige oppgaver flyttet til punkt 5. Ingen resultatpåstand eller parameterendring er tillatt før disse er behandlet. Punkt 5 forblir på vent.

## Kontroll og oppfølging

Gjenopprettingspakken inneholder originaleksporten, tilstanden før denne endringen, komprimerte DB-kopier og kvitteringer, rapportmetadata, kildeinventar, signal-/kjøringsbevis, kontrollprogram og et SHA256-manifest. Den er et nedlastbart supplement; den erstatter ikke en varig ekstern sikkerhetskopi og utløser ingen sletting av DB-kopiene.

Oppgavene som fortsatt krever egne bevis er: (a) kontroll av produksjonsdisk eller sikkerhetskopier for de 100 identifiserte manglende DB-kildene, (b) dokumentert simulert eller faktisk kostnads- og valutabehandling før netto NOK brukes, (c) kvalifisert svensk indeks eller eksplisitt avgrensing av hvilke sammenligninger som kan gjøres, (d) kontroll av første ikke-tomme produksjonsregistrering. Render-tilkoblingen i denne økten tilbyr lesespørringer, logger og utrulling, men ingen SSH-/filsystem- eller backupnedlasting. Ingen manglende kilde er gjenskapt ved antakelser.

Før gjennomgangen bestod 84 fokuserte tester med isolert PostgreSQL. Uavhengig gjennomgang fant to aktive visninger som fremdeles brukte eldre status/telling; begge er rettet med regresjoner som først feilet. Full lokal testkjøring før disse visningsrettingene ga 2 684 beståtte, 230 hoppet over og fire beståtte deltester, med de samme fire dokumenterte grunnfeilene: lokale avhengighetspins (`test_production_roots_and_complete_lock_are_exact_and_installed`), eldre FakeCursor (`test_scheduler_blocks_huge_legacy_monolith_before_payload_fetch`), live universkilde (`test_packaged_universe_is_nonempty_but_not_claimed_as_exchange_master`) og ekstra tidsavhengig valutavarsel (`test_new_breach_sends_pushover_after_configuration_change`). Endelig test- og utrullingsbevis registreres i PR195 og sluttkontrollpakken etter kontroll av eksakt commit. Den pågående salgsregelforskningen av 1 970 aksjer og finansielle porteføljehistorier er ikke endret.
