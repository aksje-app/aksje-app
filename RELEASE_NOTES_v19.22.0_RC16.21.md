# v19.22.0-rc16.21 – Unattended Autonomy and Paper Bridge

## Autonomi uten innlogging

- Render Cron er autoritativ for planlagte Autonomi-/rapportjobber.
- En fersk tidsluke kan kjøres selv om cronprosessen startet sekunder eller minutter etter tidspunktet.
- Standard catch-up-vindu er 90 minutter; eldre tidsluker kjøres ikke vilkårlig.
- Eksakt planlagt tidspunkt lagres i jobbhistorikken, og PostgreSQL advisory lock hindrer samtidige schedulerprosesser.
- Planlagt Autonomi kjører før rapportreparasjon, revalidering og annet vedlikehold.
- Cronprosessen har `REPORT_SCHEDULER_ENABLED=true`; webprosessen beholder `false` og starter ikke en konkurrerende planlegger.

## Paper som input til Autonomi

- Paper-skanneren evaluerer tekniske og autonome strategier parallelt på samme immutable markedssnapshot.
- Snapshot, tekniske indikatorer og strategiavgjørelser publiseres i en checksum-verifisert bro.
- Autonomi kan lese dette som `paper_engine_input` per ticker.
- Inputtet er observasjonelt: det kan ikke endre score, rangering, ordre eller terskler.
- Paper beholdes som benchmark til sammenligning og akseptanse er bestått.

## Forbedret Paper-drift

- Varig status for start, slutt, feil og antall handler.
- Global PostgreSQL-lås stopper overlappende cronprosesser og mulige dobbeltordre.
- Låsefeil stopper Paper fail-closed når database er konfigurert.

Ingen handels- eller beslutningskriterier er endret.
