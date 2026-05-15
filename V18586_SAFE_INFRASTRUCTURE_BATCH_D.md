# v18.5.86 – Safe Infrastructure & Regression Framework Batch D

Formål: stabilisere videre arbeid uten å endre analysemotorene unødvendig.

## Innhold

### D1 – Regresjonssikring
- Ny `safety_audit.py` med statisk smoke/regresjonssjekk.
- Ny `test_v18586_safe_infrastructure_regression.py`.
- Gamle versjonstester er oppdatert til aktiv build `v18.5.86`.
- Full test-suite verifisert: `197 passed`.

### D2 – Protected zones
- Lagt inn `DO_NOT_TOUCH_ZONE` rundt global oppdatering og Paper Trading kapital-/cash-semantikk.
- Hensikt: små patcher og mindre risiko for at UI-blokker forsvinner.

### D3 – State & audit
- Ny lettvekts audit-logg via `add_audit_event()`.
- Logger blant annet global oppdatering, porteføljeverdi-justering og reset.
- Lagrer til `runtime_audit_log.jsonl` når miljøet tillater det.

### D4 – Feature governance
- Ny feature registry med statusene `ACTIVE`, `PARTIAL`, `DUMMY`, `LEGACY`, `DISABLED`.
- Dekker global update, paper capital, sikkerhetsmodus, Pushover, audit og regresjon.

### D5 – UI consistency
- Synlig, sammenleggbar safe-build/statusseksjon nær toppen.
- Viser aktiv build, regresjonssjekk, feature-status og siste audit-hendelser.

### D6 – Trading fail-safe
- Beholder cash/kjøpekraft-blokkering fra Batch A.
- Beholder sikkerhetsmodus-kobling fra Batch A.
- Batch D legger audit rundt kritiske porteføljehandlinger.

### D7 – Data integrity
- Feature registry markerer datakvalitet/fallback-varsler som `PARTIAL`, slik at det ikke fremstår som ferdig overalt.

### D8 – In-app changelog/build-identitet
- Aktiv build vises via `app_version.py` og safe-build panelet.
- Dokumentert i denne filen.

## Ikke endret
- Ingen stor refaktorering av analysemotorer.
- Ingen flytting av forecast/risk/fund engine.
- Ingen endring i scoringlogikk.

## Test
- `python3 -m py_compile app.py safety_audit.py app_version.py sticky_topbar.py`
- `pytest -q`
- Resultat: `197 passed in 6.31s`
