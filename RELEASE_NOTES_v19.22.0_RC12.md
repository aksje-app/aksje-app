# Release notes v19.22.0 Investor Edition RC12

## Formål

RC12 retter jobb- og rutelivssyklusen som fortsatt feilet etter RC11. RC11 fjernet `StreamlitAPIException`, men en ny manuell rapport kunne hoppe til Autonomi Oversikt, vise en eldre avbrutt kjøring og feilaktig omtale en manglende workertråd som serverrestart. Lagrede scheduleroppdrag kunne dessuten være bundet til en eldre sentral konfigurasjonsversjon.

## Endret

- Rapportstart oppretter en kjøringsbundet arbeidsflaterutelås for Autonomi → Rapporter.
- Rutelåsen brukes før arbeidsflateradioen opprettes, beholdes mens den aktuelle kjøringen er aktiv og frigis etter terminalstatus er vist én gang.
- En eldre rutelås kan ikke overstyre en nyere aktiv kjøring.
- Manuelle jobber lagrer OS-prosessidentitet, PID, workertråd og heartbeat.
- Faktisk prosessrestart, legacy-status uten workeridentitet og tapt workertråd i samme prosess får separate årsakskoder.
- En vanlig Streamlit-rerun omtales ikke lenger som serverrestart.
- Blank jobb eller `Uten navn` normaliseres til et eksplisitt navn med markeder.
- Manglende eller utdatert Investment Mission-kontrakt regenereres kontrollert mot gjeldende sentral konfigurasjon.
- Jobbens eksisterende tidsplaner, tidssone, markedsvalg og øvrige innstillinger beholdes under kontraktsmigreringen.
- Scheduler kan dermed kjøre eldre lagrede jobbprofiler uten at operatøren må opprette dem manuelt på nytt.

## Ikke endret

- `final_score`, kandidatvalg, rangering og beslutningstrakt.
- Produksjonsterskel og varselterskeladferd.
- Autonomis porteføljeregler og Paper Trading.
- Faste schedulertider 08:00 og 22:00 Europe/Oslo.
- Pushover-, innloggings- eller Husk meg-regler.
- Produksjonshandel forblir fail-closed.
- Rapportinnhold og PDF-renderer.

## Live-bekreftelse som gjenstår

RC12 er ikke produksjonsgodkjent før Render viser at ett nytt utkast starter én ny kjøring, blir på Rapporter, ikke viser en gammel terminaljobb som aktiv, fullfører med ny JSON/PDF og at schedulerjobber med eldre konfigurasjonskontrakt migreres uten å endre tidspunktene.
