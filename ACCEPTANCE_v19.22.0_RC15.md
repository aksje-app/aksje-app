# Akseptanse v19.22.0 Investor Edition RC15

Versjonen kan ikke produksjonsgodkjennes før punktene nedenfor er dokumentert live på Render.

## Ren deploy

- App og Render-logg viser `v19.22.0-rc15`.
- `requirements.txt` inneholder `streamlit==1.57.0` og `starlette==1.3.1`.
- RC15 FULL er deployet samlet over RC14.
- Database, varig disk, rapportarkiv, logger, `.env` og hemmeligheter er bevart.

## Bakgrunnsworker

- En ny rapportjobb starter med ny kjørings-ID og tydelig jobbnavn.
- Render-loggen inneholder ingen `missing ScriptRunContext` fra `manual-chain-*`.
- Workeren kaller ikke `st.*` eller Streamlit `session_state`.
- UI viser siste reelle fremdrift og separat worker-heartbeat.
- Vanlig refresh avbryter ikke jobben og oppretter ikke en ny jobb.
- En worker som lever uten fremdrift i minst ett minutt vises som stanset steg, ikke som falsk serverrestart.

## Markedsdata

- Kjøringen kommer forbi `MARKET_DATA` for USA og fortsetter gjennom alle valgte markeder.
- Hvert yfinance-historikkall har tidsfrist.
- Selskapsinfo kan times ut uten å stoppe kandidaten eller markedet.
- Markedets enrichment avsluttes kontrollert ved maksimal tidsfrist.
- Ugyldige symboler logges som filtrert eller hoppet over og blokkerer ikke resten av markedet.
- IDEX og PEXIP bruker `.OL` når markedet er Norge.
- `US10Y`, `SPEMIX` og kryssmarkeds-symboler brukes ikke som amerikanske aksjekandidater.

## UI og tabeller

- Ingen widgetadvarsel sier at skanneprofilen både fikk standardverdi og session-state-verdi.
- Ingen `PyArrowInvalid` oppstår for `Weight` eller andre blandede numeric/blank-kolonner.
- Rapporter-fanen beholdes gjennom start, refresh, fremdrift og terminalstatus.
- Hele siden rendres bare én gang.

## Regresjon

- UI, JSON og PDF viser samme markeder, kandidater, score og beslutning.
- Scheduler og Pushover fungerer etter eksisterende regler.
- `final_score`, rangering, produksjonsterskel og handelsregler er uendret.
- Autonomi og Paper Trading er separate.
- Produksjonshandel er fail-closed.
