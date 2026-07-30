# AI Aksje Analyzer Pro v19.15.0

## Full systemstabilisering

Denne versjonen samler markedsvalg, evidens, konfidens, porteføljebegrunnelse, JSON og PDF i én etterprøvbar sannhetsmodell. Den er en stabiliseringsversjon og endrer ikke produksjonsterskelen for kjøp, posisjonsgrenser eller risikorammer.

### Rettet

- **Kjernemarkeder** betyr alltid Norge, Sverige og USA i lagrede jobber, investeringsoppdrag, faktisk kjøring, JSON og PDF.
- Gamle jobbprofiler med riktig navn, men foreldet seksmarkedsliste, migreres til en stabil profil-ID.
- Modellkonfidens, evidensjustert modellkonfidens og endelig beslutningskonfidens er tre eksplisitte felt. PDF og JSON bruker samme beslutningskonfidens.
- Gjennomsnittlig evidensdekning beregnes fra evidensprofilen, ikke fra markedsdatakvalitet.
- Kandidatens porteføljebegrunnelse synkroniseres med den kanoniske porteføljebeslutningen.
- Nyheter fra sekundære aggregatorer må nevne selskapet eller tickeren i overskriften. Direkte selskapskilder er unntatt fordi kilden selv etablerer relevansen.
- Insiderfakta får fakta-ID, kildetype, dokument-ID, skjematype, direkte kilde og eksplisitt primær-/sekundærklassifisering.
- Sekundære strukturerte insiderdata kan ikke presenteres som primærverifiserte fakta.
- Rapportintegritet kontrollerer markedsprofil, oppdragsmarkeder, konfidens, evidensdekning, porteføljebegrunnelse, nyhetsrelevans og insiderproveniens før PDF ferdigstilles.
- Selskapsnavn hentes fra felles sikkerhetsmetadata når kandidaten bare har tickeren som navn, slik at relevante saker som omtaler selskapsnavnet ikke avvises.
- Varslingsresultater normaliseres til én `(ok, detalj)`-kontrakt. En feilet Pushover-tuple kan ikke lenger registreres som sendt.
- Mutable `.app_runtime`-filer og en ufullstendig legacy-snutt fjernes fra GitHub-kilden.
- Render-standardene er fail-closed: Paper Trading, scheduler og bakgrunnsjobber aktiveres ikke automatisk ved deploy.

### Baselinefunn

Den faktisk deployede v19.14.6-grenen bestod ikke sin egen komplette testpakke før endring: 557 tester og 4 deltester bestod, mens én distribusjonstest feilet på manglende releasefil. Dette er dokumentert i `SOURCE_BASELINE_AUDIT_v19.15.0.md`.

### Leveransestatus

Versjonen må gjennom en ren Render-deploy og én full ende-til-ende-kjøring før produksjonsgodkjenning. Manuell eller automatisk Paper Buy skal forbli deaktivert inntil akseptansekriteriene er dokumentert bestått.
