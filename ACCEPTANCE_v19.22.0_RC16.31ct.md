# RC16.31ct – Five-Day Capital Rotation and Learning Guard

## Produksjonsatferd

- Alle eksisterende autonome posisjoner vurderes fra opprinnelig `opened_at` ved neste komplette autonomisyklus.
- Posisjoner innenfor ±1 % etter fem børsdager selges til kontanter når score ikke forbedres og ingen gyldig beskyttelse finnes.
- Positivt momentum, tydelig scoreforbedring, holdende breakout eller dokumentert hendelse innen tre børsdager beskytter mot mekanisk salg.
- Stop loss, trailing stop og score-exit har alltid høyere prioritet enn hendelsesvern.
- Salg krever ikke en erstatningsaksje. Kontanter er en eksplisitt gyldig beslutning.
- Fem børsdagers gjenkjøpssperre gjelder ordinær portefølje og læringskonto; ny dokumentert hendelse, breakout eller minst tre scorepoengs forbedring kan oppheve den.

## Læring og parametere

- Kontrollsenteret viser evidensfremdrift og livsløpet Hypotese → Simulert → Parallelltestet → Klar for vurdering → Godkjent/Avvist.
- En læringsvakt varsler dersom aktiv kontrollert læring ikke er evaluert på over 24 timer på en børsdag.
- Pushover-godkjenning viser konkret gammel og foreslått verdi. Produksjonsverdier endres først etter eksplisitt godkjenning.
- Godkjente parametere forsegles med Champion-ID og SHA-256-fingeravtrykk. Uventet avvik pauser Autonomi og varsler.
- Forseglingen ligger i persistent konfigurasjon og overskrives ikke av normal Render-deploy.

## Synlighet

- Hver syklus leverer kapitalopprydding med antall vurdert, kvalifisert, beskyttet, solgt til kontanter, erstattet og manglende pris.
- Rapporten viser avkastning per børsdag, aktive vern og konkret handling per posisjon.
- Én samlet Pushover-kvittering oppsummerer porteføljekontrollen i tillegg til konkrete handelskvittringer.

## Verifikasjon

- `tests/test_rc16_31ct_capital_rotation.py`
- `tests/test_rc16_31cs_autonomy_continuity.py`
- Produksjonsfilene skal kompilere uten feil.
- Full testinnsamling har en separat eksisterende Streamlit-feil i `test_v19220_rc1631cr_retired_vehicle_cleanup.py` ved import uten innlogget bruker.
