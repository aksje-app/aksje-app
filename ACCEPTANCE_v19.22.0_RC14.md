# Akseptanse v19.22.0 Investor Edition RC14

Versjonen kan ikke produksjonsgodkjennes før punktene nedenfor er dokumentert live på Render.

## Ren deploy

- App og Render-logg viser `v19.22.0-rc14`.
- `requirements.txt` inneholder `streamlit==1.57.0` og `starlette==1.3.1`.
- RC14 FULL er deployet samlet over RC13.
- Database, varig disk, rapportarkiv, logger, `.env` og hemmeligheter er bevart.

## Global navigasjon og rerun

- Lagring og handlinger beholder gjeldende hovedmeny og underfane.
- Vanlig refresh beholder samme side.
- Hard refresh gjenåpner samme rute fra URL eller varig UI-tilstand.
- Ingen `StreamlitAPIException` omtaler en widgetnøkkel som endres etter opprettelse.
- Oversikt, Rapporter, Autonomi, Jobber/Planlegger, Godkjenninger, Portefølje, Paper Trading, Top Picks, Analyse, Long Engine, AI-verktøy, Varsler, Driftssenter, Valuta og System er kontrollert.
- Kun én hovedrenderer kjøres per full app-rerun.

## Rapporter og fragment

- `Nytt utkast` starter nøyaktig én jobb og forblir på Autonomi → Rapporter.
- Fremdriftspanelet vises bare én gang.
- Ved `COMPLETED`, `FAILED` og `CANCELLED` gjentas ikke toppbanner, Kontrollsenter, Autonomi eller Rapportsenter nederst på siden.
- Refresh under 5 %, 50 % og terminalstatus starter ikke en ny jobb.
- Rapportarkivet kan oppdateres med én vanlig sideoppdatering etter terminalstatus.

## Visningstidssone

- Valgt tidssone lagres under System → System/admin → Visning og tid.
- Etter lagring blir brukeren stående på samme side og seksjonen forblir åpen.
- Valget beholdes etter vanlig refresh, hard refresh, utlogging/innlogging, Render-restart og ny deploy.
- Tidssonen lagres i sentral, versjonert konfigurasjon.
- Scheduler forblir separat på 08:00 og 22:00 Europe/Oslo.

## Regresjon

- Alle fire bannerkombinasjoner fungerer uten tom hvit flate eller sammenklemte grafer.
- UI, JSON og PDF viser samme markeder, kandidater, score og beslutning for neste gyldige rapport.
- Scheduler og Pushover fungerer etter eksisterende regler.
- `final_score`, rangering, produksjonsterskel og handelsregler er uendret.
- Autonomi og Paper Trading er fortsatt separate.
- Produksjonshandel er fail-closed.
