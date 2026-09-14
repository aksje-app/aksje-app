# Deploy RC16.31cj

1. Ta sikkerhetskopi av gjeldende Render-programfiler.
2. Pakk ut den rene RC16.31cj-deltaen over eksisterende versjon.
3. Sett `EXPECTED_APP_VERSION=v19.22.0-rc16.31cj` for web og scheduler.
4. Deploy begge fra samme kildeversjon.
5. Åpne `Marked og signaler → Jeep Commander 2.2`.
6. Kontroller år, kilometer, område, forhandlernettverk og eventuelle kostnadsestimater.
7. Lagre eventuelle manuelle annonselenker, én per linje.
8. Kjør `Søk nå` og kontroller treff, paginerte sider og feil per kilde.
9. Første vellykkede søk skal være stille; senere prisendring skal vise gammel og ny pris i Pushover.

Tilbakerulling: gjenopprett forrige programfiler og forrige `EXPECTED_APP_VERSION`. Bilmodulens data er isolert under `temporary/jeep_commander_22`.

