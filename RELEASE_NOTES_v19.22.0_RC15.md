# Release notes v19.22.0 Investor Edition RC15

## Formål

RC15 retter livefunnene fra kjøringen `MBJ-20260805-145534-061135`: rapportworkeren brukte indirekte Streamlit-session state, markedsdata kunne bli stående uten tidsfrist, kryssmarkeds-/ikke-aksjesymboler ble sendt til Yahoo, skanneprofilen blandet widgetverdi og standardverdi, og enkelte blandede dataframekolonner kunne feile i Arrow-konverteringen.

## Endret

- Manuelle rapportworkere kjører i en eksplisitt bakgrunnskontekst som ikke kan lese eller skrive Streamlit `session_state`.
- `StateService` bruker tom, isolert tilstand i bakgrunnskjøringer og importerer ikke Streamlit fra workertråden.
- En separat worker-heartbeat oppdateres hvert tiende sekund uten å late som om analysefremdriften har endret seg.
- UI viser både siste reelle fremdrift og siste worker-heartbeat og varsler når workeren lever, men et steg ikke beveger seg.
- Yfinance-historikk får eksplisitt timeout, valgfri selskapsinfo har egen timeout, og hele markedets enrichment har en øvre tidsfrist.
- `NO_DATA` retryes ikke umiddelbart; nettverksfeil har et begrenset antall forsøk.
- Ugyldige ikke-aksjesymboler og kryssmarkeds-symboler filtreres før markedsdatakall.
- Pakkede markedsunivers brukes som markedsbevis for rå symboler. IDEX og PEXIP normaliseres til `.OL` når markedet er Norge.
- Skanneprofil-widgeten sender ikke både session-state-verdi og `index`/`value` til samme widget.
- En global, idempotent dataframeguard normaliserer blanke numeriske objektkolonner før Streamlit/Arrow-konvertering.
- Streamlit `1.57.0` og Starlette `1.3.1` beholdes låst.

## Ikke endret

- `final_score`, kandidatvalg etter gyldig datainnhenting, rangering eller beslutningstrakt.
- Produksjons-, kjøps- eller varselterskler.
- Autonomis porteføljeregler eller Paper Trading.
- Faste schedulertider 08:00 og 22:00 Europe/Oslo.
- Pushover-, innloggings- eller Husk meg-regler.
- Produksjonshandel forblir fail-closed.
- Rapportskjema og PDF-layout.

## Live-bekreftelse som gjenstår

RC15 er ikke produksjonsgodkjent før en ny Render-kjøring viser fremdrift forbi MARKET_DATA, ingen `missing ScriptRunContext` fra `manual-chain-*`, begrensede tickerfeil uten blokkering, korrekt heartbeat/fremdrift og en fullført rapport med samsvar mellom UI, JSON, PDF, logger og Pushover.

## Lokal validering

- 707 innsamlede tester bestått i fire isolerte batcher.
- 4 deltester bestått.
- 35 målrettede RC12-RC15-/markedsdata-/worker-tester bestått.
- 0 testfeil.
- Kompileringskontroll, full systemaudit og navigasjonsaudit bestått.
- Testmiljøets monolittiske pytest-prosess avsluttet ikke innen tidsgrensen etter over 91 % på grunn av akkumulert legacy-trådtilstand. Hele den samme innsamlede testlisten ble derfor kjørt nøyaktig én gang i fire isolerte batcher.
