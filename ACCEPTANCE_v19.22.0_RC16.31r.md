# Akseptanse RC16.31r

RC16.31r kan godkjennes for deploy når:

1. APP_VERSION er `v19.22.0-rc16.31r` og PREVIOUS_APP_VERSION er `v19.22.0-rc16.31q`.
2. Parallel strategivurdering kjøres isolert og har en avsluttbar timeout.
3. Timeout blokkerer ikke resten av Autonomi-kjeden og kan ikke autorisere handel.
4. STALLED-status hevder ikke at worker eller rapportlås er frigitt før dette faktisk er sant.
5. Full aktiv testsamling har 0 feil, og historiske kontrakter forblir dokumenterte strict-xfail.
6. FULL, DELTA, deploynote, valideringsrapport, endringsinventar og SHA-256 følger leveransen.
7. Produksjonsklar status gis først etter live Render-verifisering av UI, PDF, JSON, logger, scheduler og Pushover.

