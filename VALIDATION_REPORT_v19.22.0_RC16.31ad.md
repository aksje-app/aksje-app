# Valideringsrapport RC16.31ad

## Grunnlag

RC16.31ad er validert mot den vedlagte RC16.31ac-kjøringen `MBJ-20260824-172557-17CD9C`, tilhørende JSON, diagnosepakke og tre-siders PDF.

## Reproduserte rotårsaker

- 16,67 % samsvar var 10 like SKIP av 60 kandidater. Shadow omgjorde ellers 48 HOLD og 2 REVIEW til BUY ved å bruke strategiscore som beslutning.
- Læringsaksepten krevde en læringsrad også for en kandidat som allerede var dokumentert SKIP i den kanoniske beslutningen.
- Kandidater med negativ P/E eller nullvolum kunne ha råverdi, men ingen meningsfull delscore. Konvertering av denne delscoren ga `float(None)`.

## Resultat

- Målrettede stabiliseringstester: **24 bestått, 0 feilet, 2 dokumenterte historiske xfail**.
- Første fullkjøring: **974 bestått, 1 feilet, 66 dokumenterte historiske xfail, 4 subtester bestått**. Eneste feil var at obligatoriske RC16.31ad-dokumenter ennå ikke var opprettet; ingen kode- eller funksjonsfeil.
- Endelig fullkjøring: **975 bestått, 0 feilet, 66 dokumenterte historiske strict-xfail, 4 subtester bestått**.
- Versjons- og sporbarhetsaudit: **PASS**.
- Fullsystemaudit: **PASS**, 0 feil, 0 advarsler og 0 mutable distribusjonsfiler.
- Navigasjons- og rerun-audit: **PASS**, 324 Python-filer kontrollert og ingen produksjonsparametere endret.
- Replay av vedlagt 60-kandidatkjøring: **60/60 handlinger i samsvar, 100 %, grønn kontroll**, samtidig som Shadow fortsatt er read-only og ikke promoteringsberettiget.
- Replay av læringsaksept: **PASS**, alle ni kontroller bestått og ingen ubehandlede kandidater.
- Hoved-PDF: **3 A4-sider**, gyldig PDF 1.3, visuelt kontrollert side for side uten overlapp, avkuttet innhold eller uleselige tabeller. RC16.31ad-identitet vises i topptekst, metadatafelt og sporbarhetslinje.
- FULL-pakke: **953 filer**, distribusjonsvalidator PASS, ZIP-integritet PASS og ingen `tmp`, runtime-data, diagnosefiler eller genererte rapporter.
- DELTA-pakke: **27 filer**, distribusjonsvalidator PASS, ZIP-integritet PASS og 0 slettinger.
- Ren FULL-utpakking: **975 bestått, 0 feilet, 66 dokumenterte historiske strict-xfail, 4 subtester bestått**.

## Produksjonsgrense

Lokal godkjenning er ikke det samme som live produksjonsgodkjenning. Endelig godkjenning krever én fullført utkastkjøring og én fast rapport på Render uten OOM/restart/502, med samme commit og RC16.31ad-identitet i alle tjenester og artefakter.
