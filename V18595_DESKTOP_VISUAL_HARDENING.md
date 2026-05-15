# V18.5.95 Desktop Visual Hardening

Formål: fikse tre konkrete synlighetsproblemer uten å endre tradinglogikk eller analysemotorer.

## Endret

1. **Pushover test / API-status**
   - Flyttet aktivt testpanel opp i `Auto trading-oppsett`, før den store innstillingsformen.
   - Beholder faktisk API-verifisering og testvarsel, men gjør dem synlige tidlig på både PC og mobil.
   - Nye aktive knappenøkler:
     - `main_auto_verify_pushover_v18595_desktop_visible`
     - `main_auto_send_test_pushover_v18595_desktop_visible`
   - Ny aktiv UI-path: `active-pushover-test-v18595`.

2. **Global oppdatering**
   - Lagt inn sen CSS-hardening rett før den aktive global-knappen rendres.
   - Hindrer gamle kompakt-/desktop-regler i å krympe eller klippe knappen.
   - Tvinger normal tekstflyt, full bredde og tydelig knapp på PC og mobil.

3. **Build-/versjonsbadge**
   - Gjort `Professional Trading Workspace` / build-label til en tydelig trust-badge.
   - Lysere tekst, bakgrunn, kant, wrap og maks-bredde slik at den ikke ser disabled ut eller forsvinner i toppfeltet.
   - Lagt til `title` og `aria-label` i `sticky_topbar.py`.

## Ikke endret

- Ingen endring i auto-tradinglogikk.
- Ingen endring i Paper Trading-data.
- Ingen endring i analysemotorer, scoring eller ordre-/salgslogikk.
- `APP_VERSION` er ikke bumpet, i tråd med eksisterende test-/handoff-advarsel.

## Verifisering

Kjørt:

```bash
python -m py_compile app.py workspace_layout.py sticky_topbar.py
pytest -q
```

Resultat:

```text
216 passed
```
