# v19.22.0-rc16.27 – Six-Market Learning Reports

## Hovedendringer

- Alle faste rapportprofiler bruker USA, Norge, Sverige, Finland, Danmark og Brasil.
- Første skannetrinn er 50 symboler per marked, maksimalt 300 totalt.
- Utvidet analyse er avgrenset til 18 kandidater og evidenskontroll til 15 kandidater per rapport.
- NewsAPI har hard grense på 15 faktiske forespørsler per ordinær rapport og 5 per testrapport.
- NewsAPI har hard operativ døgnramme på 50 forespørsler; 10 av Developer-planens 60 beholdes som reserve.
- Delt 12-timers NewsAPI-cache gjør at cachetreff ikke bruker forespørselsbudsjettet.
- Rapporten leser læringshandler fra den kanoniske `autonomy_learning`-kontoen.
- En hard konsistensaudit stopper rapportleveransen dersom kanoniske læringshandler og rapporttall avviker.
- PDF-en viser konkrete læringsbeslutninger med score, risiko, datakvalitet og produksjonsblokkeringer.
- Læringskontoen fortsetter å motta kandidater når produksjonsporteføljen er pauset. Produksjonshandel forblir fail-closed.
- Gjentatt behandling av samme `run_id` kan ikke opprette nye læringshandler.
- Rapporten skiller planlagt og faktisk markedsdekning og merker kildehelseendring som delta.

## Sikkerhet

Ingen av endringene senker produksjonskravene eller tillater ekte meglerhandel. Terskelen 60–65 gjelder bare den separate teoretiske læringskontoen; godkjent standard er 63.

## Verifisering

- RC16.27-aksetestanrop: bestått.
- Python-kompilering: bestått.
- Kanonisk læringsrapport med tre kjøp: PDF generert og tekstkontroll bestått.
- FULL- og DELTA-distribusjon kontrolleres separat ved bygging.

Status: `LOCAL_PASS_LIVE_REQUIRED`.
