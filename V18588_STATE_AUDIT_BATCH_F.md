# v18.5.88 — State & Audit Batch F

## Formål
Trygg stabilisering av paper-trading state, audit og BUY fail-safe uten å omskrive analysemotorene.

## Endret
- Nytt `state_audit.py`-lag for committed paper-state snapshots.
- Sentral `validate_buy_order()` for paper BUY-validering.
- BUY blokkeres før portefølje muteres ved:
  - manglende/ugyldig ticker
  - ugyldig pris
  - beløp <= 0
  - for lite cash
  - duplikatposisjon ved aksjekjøp
  - max åpne posisjoner
  - for lav confidence
  - max kjøp per dag
- Paper BUY/SELL logger før/etter-state via audit.
- Fond/ETF-kjøp bruker samme cash/safety-validering, men tillater akkumulering i eksisterende fond/ETF-posisjon.
- Feature registry utvidet med `state_audit` og `trading_fail_safe`.
- Changelog/build identity oppdatert til `v18.5.88`.

## Ikke endret
- Ingen omskriving av analysemotorer.
- Ingen flytting av hoved-UI.
- Ingen endring av scoring/forecast/risk engines utover eksisterende import/versjonsstøtte.

## Tester
- `python3 -m py_compile app.py trading_engine.py state_audit.py safety_audit.py app_version.py`
- `pytest -q` → 205 passed
