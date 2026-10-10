# Portfolio Evidence & Controlled Learning — RC16.34i

## Implementert og testet

- Nye posisjoner lagrer rank og justert porteføljescore ved kjøp. Disse feltene endres ikke ved senere vurderinger. Eldre posisjoner med manglende kjøpsbevis viser «ukjent». Beste dokumenterte rank lagres fra tilgjengelige vurderinger.
- UI og PDF viser kjøpsrank → dagens rank, kjøpsscore → dagens score, tidspunkt for full vurdering og stopkontroll. PDF viser også tidspunkt for markedsgrunnlaget. Manglende kandidat i ny vurdering viser ukjent rank, ikke en gammel plassering som dagens.
- Beholdningsforklaring følger lagret beslutningsspor og blokkeringskoder: målportefølje, blokkert utfordrer eller utsatt omvekting. Denne forklaringen er ikke et nytt kjøpssignal.
- Bransje og brede sektorer beholdes som separate begreper. HAFNI.OL/HAFN identifiseres som produkttank; shippingstresstesten inkluderer dette også for eldre posisjoner med Industrials som sektor. Primærkilde: https://hafnia.com/about-hafnia/. Brede sektorgrenser og eksisterende konsentrasjonsstraffer videreføres.
- Stoppvarsler deler aksjene i separate blokker og viser kjøp/topp/siste kurs/salgsgrense. Mulig kursfall beregnes med siste kurs som nevner. OET 901 → 882,55 er 2,05 %, ikke 2,09 prosentpoeng. Gevinst/tap ved salgsgrensen beregnes fra kjøpskursen; nivået er ikke en garantert utførelseskurs.
- Læringsrapporten viser absolutt avkastning og meravkastning separat. Null observasjoner betyr «KAN IKKE VURDERES». 20-dagers målinger og fullført 60-dagers horisont skilles. «FORELØPIG POSITIV FORSKJELL» erstatter en udokumentert påstand om merverdi. Foreslått skyggetest vises som ikke startet.
- SP-skanningen samler avgrenset historikk fra grovutvalg og analyserte kandidater før finalistkuttet, med tidspunkt, kjent offisiell hendelsesinformasjon og sjekksum. Finalistdata, konfigurasjon og markedsaktivering fryses. Ringbuffer: maks 240 kjøringer / 8 MB; hver kandidatgruppe maks 1000 rader. Totalantall og faktisk omfang følger eksporten. Dette er ikke et fullstendig universarkiv.
- Offline simulator bruker `super_portfolio.evaluate` med eksplisitt kopiert simuleringstilstand. Den sender ikke ordre, varsler eller skriver produksjonstilstand. Testet med både kjøp, stoppsalg og kostnader, samt blokkering/alternativsøk i produksjonsmotorens regresjonstester.
- Kombinasjonstest begrenses til 200 parameterforsøk og fem finalister. Trening, senere validering og urørt sluttperiode brukes i den rekkefølgen. Standard 90 kalenderdager embargo mellom datasettdelene; juster opp ved lengre/uvanlige horisonter. Sluttperioden velger ikke finalistene. Alle forsøk bevares i resultatfilen.
- Skyggetestplan låser referanse og finalistparametere før nye observasjoner. Historiske observasjoner og etterfølgende planendringer avvises. Resultatene kan fortsatt ikke godkjenne en produksjonsendring automatisk.
- Legacy snapshot-get bruker `read_json_array_item`: PostgreSQL velger ett element server-side i stedet for å overføre og dekode hele den eldre JSON-samlingen.

## Kjør avgrenset test

Eksporter den frosne frame-listen til en lokal JSON-fil. Ikke erstatt manglende historikk med dagens priser eller nyheter. Lag en søkefil, eksempel:

```json
{"minimum_score":[60,65,70],"candidate_persistence_runs":[2,3],"max_position_pct":[10,12,15],"risk_exit_cooldown_days":[1,2,3]}
```

```sh
python tools/run_learning_experiments.py frozen_frames.json search_space.json result.json --budget 100 --finalists 3 --embargo-days 90 --memory-mb 768
```

Jobben kjøres separat fra web/cron. Linux setter et eget virtuelt minnebudsjett; ingen slik grense settes på produksjonsprosessen. Inputgrense 64 MB, søkefil 1 MB. For lite historikk gir feil og ingen vellykket teststatus. Den lille ringbufferen kan ikke alene dekke de lange valideringsperiodene: bevar godkjente eksportfiler eksternt før de roteres. Ingen Render-jobb er opprettet eller aktivert i denne PR-en.

For senere skyggedrift: `create_forward_plan(search, reference_config, started_at=...)` etter den historiske perioden og `evaluate_forward_plan(plan, future_frames)` i en separat jobb. Planen må lagres uendret. Resultatet viser nettoavkastning, største verdifall, kostnader, handelsantall, tapte utganger og kontantandel. Dette er simulerte markedspriser, ikke garanti for historiske fills.

## Åpent — ikke påstått ferdig

- Full porteføljesimulator og tilsvarende parameterforsøk for **Autonomi**. Eksisterende `replay_contract.replay_decisions` gjenbruker produksjonens beslutningsport, men beviser ikke en full kontrafaktisk kapital-/handelsbane. Den nye SP-simulatoren brukes ikke som en falsk Autonomi-referanse.
- Lenger datagrunnlag, validering av FX, utbytte, intradagforløp og utførelseskostnader. Arkiver alle relevante kandidater, ikke bare avgrenset grov-/dyputvalg, før det hevdes at hele utvelgelsen er testet.
- Mål tidlige tap og beholdt MFE på alle utgangstyper; vanlige omvektinger har ikke alltid komplett utgangsbevis. Ingen statistisk eller kausal validering er påstått.
- Aktiv, langvarig forward-jobb, automatisk resultatinnlesing i UI og sammenligning moderat mot nær-terskel. Hverken fremtidige data eller faktiske resultater av et nytt eksperiment finnes ennå.
- Produksjonsforslag med Godkjenn/Avvis ut fra nye eksperimenter. Resultatene er sperret for slik promotering inntil beviskrav og uavhengig vurdering er oppfylt. Eksisterende parameterhistorikk/godkjenning/rollback er fortsatt tilgjengelig.
- Måle om full analyse oftere enn 12 timer forbedrer resultatene uten uakseptabel ressursbruk. Eksisterende kjøps-/utskiftingsporter for ferskhet, risiko, kostnader og gjenkjøp beholdes.
- Fysisk mobilverifisering etter deploy av PR #67. Ny PR bygger på denne åpne PR-en. Ingen merge eller deploy er utført.

## Driftsfunn 10. oktober 2026 — kun lesing

Render webtjeneste `aksje-app` kjører nå Standard med 2 GiB minne. Halvtimesmålinger viste en topp rundt 1,00 GiB 9. oktober; dette er ikke en måling av en bestemt OOM-topp. De viste cron-kjøringene fullførte. Det nye snapshot-oppslaget fjerner en konkret unødvendig stor Python-innlasting, men årsak til alle web-restarter er ikke fastslått.

PostgreSQL: database 2 546 497 215 byte; brukerrelasjoner 2 537 963 520 byte. `app_kv` inkludert indekser ca. 2,11 GB, JSONL-relasjon ca. 426 MB. Markedssnapshots og strategibeslutninger er de største innholdsfamiliene. Eldre monolitter: market_snapshots.json ca. 162 MB, strategy_decisions.json ca. 135 MB, strategy_runs.json ca. 131 MB i logisk JSON-størrelse. Logisk JSON-størrelse er ikke fysisk diskbruk og må ikke summeres direkte med komprimerte relasjoner.

Dette viser hvor data ligger nå, ikke hele årsaken til økningen fra 46–48 % til 56,48 %. Historikk, indekser, gamle databasesider og øvrig diskbruk trenger tidsserier for å attribuere økningen. Eksisterende retensjon er fortsatt opt-in for sletting. Ingen historikk er slettet, ingen VACUUM FULL eller betalt oppgradering er utført. Før opprydding: avgrenset eksport/arkiv, verifisert gjenoppretting, beholdnings-/replaykrav og konkret sletteliste.

## Validering

- Release-kontrakter: bestått.
- Release-regresjon: 342 tester bestått.
- Aktiv uversjonert suite: 141 bestått, to PostgreSQL-tester hoppet over lokalt (ingen lokal PostgreSQL URL). CI kjører egne PostgreSQL roundtrips.
- Nye scenarioer: uforanderlig kjøpsbevis, shipping, separate stopblokker, prosentnevner, absolutt/relativ læring, nullgruppe, temporal embargo, begrenset søk, holdout-uavhengighet, kjøp og risikosalg uten produksjons-I/O, låst forwardplan, avgrenset legacy-oppslag.
- PDF-er generert og første side av begge visuelt kontrollert: ingen overlapp i de nye seksjonene.
- CLI kjørt i separat prosess med syntetisk testdatasett: tre forsøk, fullført, produksjon uendret. Dette er programverifisering, ikke et lønnsomhetsresultat.
