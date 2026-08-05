# Akseptanse v19.22.0 Investor Edition RC12

Versjonen kan ikke produksjonsgodkjennes før punktene nedenfor er dokumentert live på Render.

## Ren deploy

- App og Render-logg viser `v19.22.0-rc12`.
- RC12 FULL er deployet samlet over RC11-koden.
- Database, varig disk, rapportarkiv, logger, `.env` og hemmeligheter er bevart utenfor kildepakken.

## Rapportstart og rute

- `Nytt utkast` starter nøyaktig én ny manuell jobb.
- Ny kjørings-ID erstatter eventuell tidligere terminal kjørings-ID.
- Aktiv arbeidsflate forblir Autonomi → Rapporter under oppstart, fremdrift og terminalstatus.
- URL viser Autonomi-kontrollsenteret med `aa_tab=reports`.
- Ingen `StreamlitAPIException` vises.
- Fremdriftspanelet vises bare én gang.
- Refresh starter ikke en ny jobb og flytter ikke brukeren til Oversikt.
- Terminalstatus vises for den nye kjøringen, ikke en eldre avbrutt kjøring.

## Worker- og restartstatus

- Ny status inneholder prosessidentitet og heartbeat.
- Vanlig Streamlit-rerun omtales ikke som serverrestart.
- Faktisk Render-restart gir årsakskode `SERVER_PROCESS_RESTART`.
- Tapt worker i samme prosess gir `WORKER_LOST_SAME_PROCESS`, ikke serverrestart.
- Legacy-status uten identitet merkes eksplisitt som legacy og kan ikke presenteres som ny aktiv kjøring.

## Jobbnavn og schedulerkontrakt

- Utkastet har et eksplisitt navn med markeder og heter ikke `Uten navn`.
- Eldre jobbprofiler med blankt navn normaliseres uten å endre schedule.
- Utdatert Investment Mission-/konfigurasjonskontrakt migreres automatisk.
- Eksisterende schedule, tidssone, markeder og aktiveringsstatus beholdes.
- Schedulerens faste hovedtider er fortsatt 08:00 og 22:00 Europe/Oslo.
- En feil i gammel kontrakt krever ikke at operatøren oppretter jobben på nytt.

## Rapportresultat

- Ny kjøring har ny run-ID og `app_version = v19.22.0-rc12`.
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
