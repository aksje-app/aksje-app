# v18.5.90 — UI Path Audit & Cleanup Batch H

Dette er en tillits-/verifikasjonspatch etter at flere visuelle oppgaver ikke traff aktiv runtime-UI.

## Bekreftede funn

1. **Pushover test eksisterte i kode, men i feil synlig path**
   - `Verifiser token/user` og `Send testvarsel` lå i `Varsler og dynamisk watchlist > Varselkontroll`.
   - Skjermen brukeren viste var `Auto trading-oppsett > Sikkerhet / varsling`, hvor knappene ikke var rendret.
   - Derfor var tidligere påstand “ferdig” misvisende for den aktive skjermen brukeren testet.

2. **Global oppdatering hadde for mange legacy CSS-/layout-lag**
   - Flere eldre klasser (`v18548`, `v18570`, `v18572`, `v18581`) påvirket samme kontroll.
   - Dette forklarer ghost/overlapp på desktop selv om mobil kunne se riktig ut.

3. **Stop-kontroller lå for nær høyre side / Chat-overlay**
   - Kontrollraden hadde ikke nok safe-area mot høyre.

## Endringer

- Bygget én aktiv global update-render: `data-ui-path=active-global-update-v18590`.
- Ny global-knapp bruker full bredde under statusfelt i stedet for trang sidekolonne.
- Pushover test/API-status er lagt direkte inn under samme `Sikkerhet / varsling`-område som brukeren faktisk ser.
- Stop/control stack får høyre safe-area for å redusere overlapp mot Chat-boblen.
- Versjon oppdatert til `v18.5.90`.

## Ikke endret

- Ingen analysemotorer omskrevet.
- Ingen trading-/forecast-/riskmotorer flyttet.
- Eksisterende Pushover-funksjoner gjenbrukes.

## Manuell verifikasjon som bør gjøres

1. Åpne PC-visning og bekreft at Global oppdatering kun vises én gang og er lesbar.
2. Åpne Auto trading-oppsett > Sikkerhet / varsling og bekreft at:
   - `Verifiser token/user` vises
   - `Send testvarsel` vises
   - maskert TOKEN/USER vises
3. Bekreft at Stop-knappen ikke havner under Chat-boblen.
