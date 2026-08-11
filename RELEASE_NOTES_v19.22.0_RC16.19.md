# v19.22.0-rc16.19

## Verifisert Full Replay

- Nye Autonomi-kjøringer lagrer en uforanderlig replaykontrakt v2 med kandidatgrunnlag, evidens, markedsnapshot, konfigurasjon, portefølje før/etter, beslutningsspor og faktiske handlinger.
- `FULL_REPLAY` krever bestått SHA-256-kontroll, offline reproduksjon gjennom produksjonens beslutningsport, handlingsintegritet og porteføljeavstemming.
- Manglende, endrede eller inkonsistente data nedklassifiseres til `DECISION_REPLAY` med konkrete feilkoder.
- Replaydata lagres gjennom den varige lagringsarkitekturen og eksporteres uten nettverk eller produksjonsskriving.

## Læring og arkiv

- Resultatmålinger støtter 1, 5, 20, 30, 60 og 90 handelsdager.
- Læringsstatus forblir `OBSERVE` til minst 30 målte utfall finnes. Ingen parameter endres automatisk.
- Første vellykkede arkiveksport blir grunnpakke. Senere eksporter pakker bare nye eller endrede rapporter og refererer uendret innhold med rapport-ID og SHA-256.
- Eksportinventaret oppdateres først etter lagret og verifisert ZIP.

Ingen kjøps-, salgs-, risiko-, kontant- eller porteføljeterskler er endret.
