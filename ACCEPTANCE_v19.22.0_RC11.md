# Akseptanse v19.22.0 Investor Edition RC11

Versjonen kan ikke produksjonsgodkjennes før punktene nedenfor er dokumentert live på Render.

## Ren deploy

- App og Render-logg viser `v19.22.0-rc11`.
- RC11 FULL er deployet samlet over RC10-koden.
- Database, varig disk, rapportarkiv, logger, `.env` og hemmeligheter er bevart utenfor kildepakken.

## Rapportnavigasjon

- Første klikk på Rapporter åpner Rapportsenteret.
- `Nytt utkast` starter nøyaktig én manuell jobb.
- Ingen `StreamlitAPIException` omtaler `ai_control_center_group_radio_v1863aj` eller panelradioen.
- Aktiv rute forblir Autonomi → Rapporter under start, fremdrift og terminal status.
- URL viser `aa_nav=autonomy` og `aa_tab=reports`.
- Fullført status vises én gang; fremdriftspanelet dupliseres ikke.
- Refresh etter fullføring beholder Rapporter og starter ikke jobben på nytt.
- Morgen-, kveld-, natt- og catch-up-knapper følger samme sikre rerunflyt.

## Rapportresultat

- Ny kjøring har ny run-ID og `app_version = v19.22.0-rc11`.
- JSON og PDF opprettes og kan lastes ned.
- UI, JSON og PDF viser samme markeder, kandidater, score og beslutning.
- Rapporter → Drift kan åpnes etter kjøringen.
- Pushover sendes etter eksisterende regler.

## Regresjon

- Bannerkombinasjonene fra RC10 fungerer fortsatt.
- Ingen ny stor hvit bannerflate eller sammenklemte grafer.
- Scheduler er fortsatt 08:00 og 22:00 Europe/Oslo.
- `final_score`, rangering, produksjonsterskel og handelsregler er uendret.
- Autonomi og Paper Trading er fortsatt separate.
- Produksjonshandel er fail-closed.
