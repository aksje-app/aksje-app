# RC16.31p – Candidate Governance, Short Intelligence and Learning Evidence

## Endret

- Kandidater får en eksplisitt datakontrakt og en observerende rescue-kø for sterke delvis belyste kandidater.
- Deterministisk global kortliste kan testes uavhengig av inputrekkefølge og bruker markedsminimum uten markedsmaksimum.
- Ny fail-closed shortkontrakt skiller faktisk shortinteresse fra daglig shortvolum og momentum.
- Verifisering krever kilde, rapporteringsdato, status og rapportert verdi; ellers vises `UKJENT`.
- Shortstatus følger kandidater og eide posisjoner. Porteføljen viser verifisert dekning, kapitalvektet shortandel og høy-short-eksponering.
- Læringsrapporten får reproduserbar resultatkurve, drawdown, porteføljelæring og shortutfallsanalyse.
- Rapport- og replayeksport inkluderer `candidate_data_audit.json`, `short_intelligence.json` og regelmessig læringsrapport.

## Uendret

- Produksjonsterskel 73,0.
- Kjøps-, salgs-, stop-loss-, trailing-, RSI-, risiko-, limit- og porteføljeporter.
- Scheduler-tider 08:00 og 22:00 Europe/Oslo.
- Tilleggskjøp er deaktivert.
- Shadow/læring kan ikke endre produksjonsregler eller handle.

## Begrensninger

- Versjonen innfører kontrakten og rapporteringen, men ikke en ny lisensiert/autorativ leverandør for hvert marked. Reelle shorttall vises derfor bare når oppstrømsdata oppfyller verifikasjonskontrakten.
- Shortklassifikasjon er `OBSERVE_ONLY` og gir 0,0 produksjonspoeng.
- Live Render-verifikasjon må utføres etter deploy.

