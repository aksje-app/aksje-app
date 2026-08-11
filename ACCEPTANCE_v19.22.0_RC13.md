# Akseptanse v19.22.0 Investor Edition RC13

Versjonen kan ikke produksjonsgodkjennes før punktene nedenfor er dokumentert live på Render.

## Ren deploy

- App og Render-logg viser `v19.22.0-rc13`.
- `requirements.txt` inneholder `streamlit==1.57.0` og `starlette==1.3.1`.
- RC13 FULL er deployet samlet over RC12 Render-hotfix.
- Database, varig disk, rapportarkiv, logger, `.env` og hemmeligheter er bevart.

## Rapportstart og arbeidsflate

- `Nytt utkast` starter nøyaktig én ny manuell jobb.
- Ingen `StreamlitAPIException` omtaler `autonomy_core_workspace_v1880`.
- Handlingskoden endrer ikke arbeidsflateradioens widgetnøkkel etter opprettelse.
- Aktiv arbeidsflate forblir Autonomi → Rapporter under oppstart, refresh, fremdrift og terminalstatus.
- URL viser Autonomi-kontrollsenteret med `aa_tab=reports`.
- Fremdriftspanelet vises bare én gang.
- Refresh starter ikke en ny jobb og flytter ikke brukeren til Oversikt.

## Schedulerstatus

- Planlagte tidspunkt med varig fullføringshistorikk vises som Fullført.
- Planlagte tidspunkt med varig feilhistorikk vises som Feil.
- Et tidspunkt før nåværende serverprosess startet, uten varig historikk, vises som `Ikke vurdert etter omstart`.
- Et slikt tidspunkt telles ikke som «Mistet» og startes ikke automatisk i ettertid.
- Et faktisk observert tidspunkt som ikke startet/fullførte etter grace-perioden, vises fortsatt som «Mistet».
- Eksisterende jobbtider, tidssone, markeder og aktiveringsstatus er uendret.
- Schedulerens faste hovedtider er fortsatt 08:00 og 22:00 Europe/Oslo.

## Rapportresultat

- Ny kjøring har ny run-ID og `app_version = v19.22.0-rc13`.
- JSON og PDF opprettes og kan lastes ned.
- UI, JSON og PDF viser samme markeder, kandidater, score og beslutning.
- Rapporter → Drift kan åpnes etter kjøringen.
- Pushover følger eksisterende regler.

## Regresjon

- Bannerkombinasjonene fungerer fortsatt.
- Ingen ny stor hvit bannerflate eller sammenklemte grafer.
- `final_score`, rangering, produksjonsterskel og handelsregler er uendret.
- Autonomi og Paper Trading er fortsatt separate.
- Produksjonshandel er fail-closed.
