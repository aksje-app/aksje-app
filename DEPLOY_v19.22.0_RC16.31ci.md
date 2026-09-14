# Deploy RC16.31ci

1. Ta sikkerhetskopi av gjeldende Render-versjon.
2. Pakk den rene RC16.31ci-deltaen over programfilene.
3. Sett `EXPECTED_APP_VERSION=v19.22.0-rc16.31ci` for både web og scheduler.
4. Deploy web og scheduler fra samme kildeversjon.
5. Åpne `Marked og signaler → Jeep Commander 2.2`.
6. Kontroller at forhandlernettverket er aktivert og kjør `Søk nå`.
7. Verifiser hver kildes status. En blokkert kilde skal stå som feil, ikke null treff.
8. Verifiser at første vellykkede søk lager stille referanse uten Pushover-flom.
9. Ved neste nye annonse/prisfall: kontroller selgertype, kildeantall og direkte lenke i Pushover.

Tilbakerulling: legg tilbake forrige programfiler og gjenopprett forrige `EXPECTED_APP_VERSION`. Bilmodulens egne data ligger isolert under `temporary/jeep_commander_22`.

