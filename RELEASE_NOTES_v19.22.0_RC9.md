# AI Aksje Analyzer Pro v19.22.0 Investor Edition RC9

## Formål

RC9 er en avgrenset funksjons- og beslutningsaudit. Versjonen retter misvisende markedsnavn, banneravhengigheten og rapporthandlinger som kunne forlate Rapporter-siden. Den gjør også skillet mellom analytisk investeringsvurdering og gjennomføring i Autonomis primære simulerte portefølje eksplisitt.

## Endringer

- Markedsvalg viser nøyaktige land i selve valget:
  - Norge + Sverige + USA
  - Danmark + Finland
  - Norge + Sverige + Danmark + Finland
  - Norge + Sverige + Danmark + Finland + USA + Brasil
- Eldre lagrede navn som «Kjernemarkeder» og «Utvidet Norden» leses fortsatt, men normaliseres til landnavnene.
- Jobb, kjøringsstatus, JSON og PDF får samme eksplisitte landliste.
- PDF-side 1 viser planlagte land, faktisk skannet antall per land, dekningsstatus og eventuelle land som feilet eller ble hoppet over.
- Hovedbanner og Særskilt overvåkning bruker helt separate CSS-klasser og separate renderbaner.
- Særskilt overvåkning har også faste inline høyde- og overflow-vern. Den kan derfor ikke opprette en stor tom flate selv om en ekstern stilregel mangler.
- Bannerlenker bevarer aktiv rute og fane.
- Alle reruns fra Rapportsenteret pin-er Autonomi → Rapporter før rerun. Dette gjelder blant annet Nytt utkast, morgen-, kvelds- og nattanalyse, fremdriftsoppdatering, testkjøring, aktivering, favoritt og sletting.
- Beslutningstrakten skiller:
  - analytisk kjøpsanbefaling
  - gjennomførbar handel nå
  - blokkering i Autonomis primære simulerte portefølje
  - øvrig blokkering i produksjonskjeden
- Kandidatene får separate felt for analytiske porter, gjennomføringsporter, analytisk anbefaling og handelsstatus.
- Historisk kjøpskjede-audit kan kjøres mot rapport-JSON/ZIP uten å generere PDF.

## Beskyttede områder

Følgende er ikke endret:

- final_score
- kandidatvalg og rangering
- produksjonsterskel
- risikogrenser
- porteføljegrense
- handelsregler
- scheduler-tidene 08:00 og 22:00 Europe/Oslo
- innlogging og Husk meg
- Paper Trading-regler

## Audit av de to siste rapportene

- 2 rapporter og 20 kandidatrader analysert.
- Begge rapportene skannet bare Danmark og Finland.
- 0 av 20 kandidater var på eller over produksjonsterskelen.
- 0 analytiske kjøpsanbefalinger etter gjeldende krav.
- Posisjonsgrensen var samtidig aktiv for alle 20 kandidater, men var ikke den avgjørende årsaken fordi de analytiske kravene allerede ikke var bestått.
- Mange evidensfelt stod som NOT_SEARCHED. Dette er synliggjort i auditfilen og må følges opp som egen kildeoppgave.

## Produksjonsstatus

Lokalt validert. Ikke produksjonsgodkjent før live Render-testene i akseptansefilen er bestått.
